import json
import queue

from .audio import AudioMixin
from .config import DEFAULT_MODEL_NAME, SAMPLE_RATE, SETTINGS_PATH, STT_LANGUAGE_CHOICES, resolve_model_path
from .devices import DeviceMixin
from .transcription import TranscriptionMixin
from .translation import TranslationMixin
from .ui import UIMixin


class LocalSTTApp(UIMixin, DeviceMixin, TranslationMixin, AudioMixin, TranscriptionMixin):
    def __init__(self, root):
        self.root = root
        self.root.title("Local STT - Faster Whisper")
        self.root.geometry("900x700")

        self.model = None
        self.realtime_model = None
        self.final_processing = False
        self.recording = False
        self.source_testing = False
        self.audio_frames = []
        self.audio_queue = queue.Queue()
        self.secondary_audio_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.stream = None
        self.secondary_stream = None
        self.recording_start_time = None
        self.selected_device = None
        self.selected_secondary_device = None
        self.recording_sample_rate = SAMPLE_RATE
        self.streaming_transcription = False
        self.transcribed_frames = 0
        self.level_last_update = {"primary": 0, "secondary": 0}
        self.primary_device_list = []
        self.secondary_device_list = []
        self.recommended_primary_index = None
        self.recommended_secondary_index = None
        self.settings = self.load_user_settings()
        self.selected_model_name = self.settings.get("selected_model_name", DEFAULT_MODEL_NAME)
        self.model_path = resolve_model_path([self.selected_model_name])
        self.window_alpha = self.settings.get("window_alpha", 1.0)
        self.always_on_top = self.settings.get("always_on_top", False)
        self.compact_auto_opacity = self.settings.get("compact_auto_opacity", True)
        self.compact_alpha = self.settings.get("compact_alpha", 0.75)
        self.silent_source_warning = self.settings.get("silent_source_warning", True)
        self.text_font_family = "Consolas"
        self.text_font_size = self.settings.get("text_font_size", 10)
        self.text_fg = self.settings.get("text_fg", "black")
        saved_language = self.settings.get("stt_language", "English")
        self.stt_language = saved_language if saved_language in STT_LANGUAGE_CHOICES else "English"
        self.primary_source_enabled = self.settings.get("primary_source_enabled", True)
        self.secondary_source_enabled = self.settings.get("secondary_source_enabled", True)
        self.recording_limit_seconds = 60 * 60
        self.recording_warning_seconds = 50 * 60
        self.recording_extension_seconds = 15 * 60
        self.recording_warning_shown = False
        self.recording_extension_available = False
        self.silent_warning_seconds = 15
        self.level_last_signal = {"primary": None, "secondary": None}
        self.silent_warning_shown_sources = set()
        self.last_silent_check = 0
        
        self.build_ui()
        self.root.after(50, self.process_ui_queue)
        self.root.after(100, self.run_startup_checks)

    def run_startup_checks(self):
        self.check_model_files()
        self.list_audio_devices()

    def load_user_settings(self):
        try:
            if SETTINGS_PATH.exists():
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def save_user_settings(self):
        self.settings.update({
            "window_alpha": self.window_alpha,
            "always_on_top": self.always_on_top,
            "compact_auto_opacity": self.compact_auto_opacity,
            "compact_alpha": self.compact_alpha,
            "silent_source_warning": self.silent_source_warning,
            "text_font_size": self.text_font_size,
            "text_fg": self.text_fg,
            "stt_language": self.stt_language,
            "selected_model_name": self.selected_model_name,
            "streaming_transcription": getattr(self, "streaming_var", None).get() if hasattr(self, "streaming_var") else True,
            "primary_source_enabled": getattr(self, "primary_source_var", None).get() if hasattr(self, "primary_source_var") else self.primary_source_enabled,
            "secondary_source_enabled": getattr(self, "secondary_source_var", None).get() if hasattr(self, "secondary_source_var") else self.secondary_source_enabled,
        })
        if hasattr(self, "device_combo") and self.device_combo.current() >= 0:
            self.settings["primary_source_name"] = self.device_var.get()
        if hasattr(self, "secondary_device_combo") and self.secondary_device_combo.current() >= 0:
            self.settings["secondary_source_name"] = self.secondary_device_var.get() or "None"
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            if hasattr(self, "log"):
                self.log(f"Settings save failed: {e}\n")

