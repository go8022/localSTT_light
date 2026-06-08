import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
try:
    import soundcard as sc
except ImportError:
    sc = None

from .config import APP_DIR, CHANNELS, MODEL_REQUIRED_FILES, SAMPLE_RATE, resolve_model_path


class DeviceMixin:
    def check_model_files(self):
        model_path = self.get_selected_model_path()

        self.log("Checking model folder...")
        self.log(f"MODEL_PATH = {model_path}")
        self.log(f"APP_DIR = {APP_DIR}")
        self.log(f"Selected model: {self.selected_model_name}")

        missing = []

        for filename in MODEL_REQUIRED_FILES:
            path = model_path / filename
            if not path.exists():
                missing.append(filename)

        if missing:
            self.log("\nMissing model files:")
            for item in missing:
                self.log(f"- {item}")

            self.log("\n모델 폴더에 위 파일들이 필요합니다.")
            self.log("model.bin 하나만 있으면 실행되지 않을 수 있습니다.\n")
        else:
            self.log("Model files look OK.\n")
            if self.stt_language == "Korean" and self.selected_model_name.endswith(".en"):
                self.log(
                    "Selected model is English-only. "
                    "Choose faster-whisper-tiny or faster-whisper-small for Korean STT.\n"
                )
            else:
                self.log(f"Light version STT language: {self.stt_language}.\n")

    def get_selected_model_path(self):
        self.model_path = resolve_model_path([self.selected_model_name])
        return Path(self.model_path)

    def list_audio_devices(self):
        """List all available audio devices and populate the dropdown."""
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            primary_device_list = []
            secondary_device_list = []
            default_input = self.get_preferred_default_input(devices, hostapis)
            
            for i, device in enumerate(devices):
                hostapi_name = hostapis[device['hostapi']]['name']
                default_rate = int(device['default_samplerate'])
                priority = self.device_priority(hostapi_name)
                raw_name = device['name']

                if device['max_input_channels'] > 0:
                    prefix = "[DEFAULT] " if i == default_input else ""
                    device_name = (
                        f"{prefix}{i}: [{hostapi_name}] {device['name']} "
                        f"({device['max_input_channels']}ch, {default_rate}Hz)"
                    )
                    entry = {
                        "name": device_name,
                        "device_id": i,
                        "priority": priority,
                        "kind": "input",
                        "hostapi": hostapi_name,
                        "channels": min(CHANNELS, int(device['max_input_channels'])),
                    }
                    if self.is_system_capture_name(raw_name):
                        primary_device_list.append(entry)
                    if self.is_microphone_name(raw_name):
                        secondary_device_list.append(entry)

            if sc is not None:
                speakers = sc.all_speakers()
                for speaker in speakers:
                    primary_device_list.append({
                        "name": f"[SOUNDCARD LOOPBACK] {speaker.name}",
                        "device_id": speaker.id,
                        "priority": -1,
                        "kind": "soundcard_loopback",
                        "hostapi": "soundcard",
                        "channels": 2,
                    })
                self.log(f"Soundcard loopback available: {len(speakers)} output devices detected.\n")
            else:
                self.log("Soundcard loopback unavailable. Install soundcard to capture system output directly.\n")

            primary_device_list.sort(key=lambda item: (item["priority"], item["device_id"], item["name"]))
            secondary_device_list.sort(key=lambda item: (item["priority"], item["device_id"], item["name"]))
            
            self.device_combo['values'] = [entry["name"] for entry in primary_device_list]
            self.secondary_device_combo['values'] = ["None"] + [entry["name"] for entry in secondary_device_list]
            self.primary_device_list = primary_device_list
            self.secondary_device_list = secondary_device_list
            self.recommended_primary_index = None
            self.recommended_secondary_index = None
            self.device_combo.configure(style=self.default_combo_style)
            self.secondary_device_combo.configure(style=self.default_combo_style)
            self.primary_recommend_label.config(text="", bg=self.root.cget("bg"))
            self.secondary_recommend_label.config(text="", bg=self.root.cget("bg"))
            
            self.apply_saved_source_selection()
            
            self.log(
                f"Found {len(primary_device_list)} system sound candidates and "
                f"{len(secondary_device_list)} microphone candidates.\n"
            )
        except Exception as e:
            self.log(f"Error listing devices: {e}\n")

    def refresh_and_recommend_devices(self):
        if self.recording:
            self.log("Stop recording before refreshing sources.\n")
            return

        if self.source_testing:
            self.log("Source recommendation is already running.\n")
            return

        self.list_audio_devices()
        self.source_testing = True
        self.ui_queue.put(("refresh_button", True))
        self.queue_clear_levels()
        self.queue_status("Testing audio sources...")
        threading.Thread(target=self.recommend_audio_sources, daemon=True).start()

    def recommend_audio_sources(self):
        if not self.primary_device_list:
            self.source_testing = False
            self.ui_queue.put(("refresh_button", False))
            return

        try:
            self.queue_log("Refresh / Recommend: testing current live signal from candidate devices.\n")
            self.queue_log("Play Teams/web audio now, and speak briefly for microphone detection.\n")

            primary_candidates = list(range(len(self.primary_device_list)))
            mic_candidates = list(range(len(self.secondary_device_list)))

            primary_result = self.find_best_live_source(primary_candidates, "primary")
            secondary_result = self.find_best_live_source(mic_candidates, "secondary")

            primary_index = primary_result["index"] if primary_result else None
            secondary_index = secondary_result["index"] if secondary_result else None

            if primary_index is None:
                primary_index = self.find_first_device_index([
                    ["windows wasapi", "cable output"],
                    ["windows wasapi", "stereo mix"],
                    ["windows directsound", "cable output"],
                ], self.primary_device_list)
                self.queue_log("No live Teams/web/system sound was detected. Primary fell back to the best routing candidate.\n")
            else:
                self.queue_log(
                    "Primary live signal detected: "
                    f"{self.primary_device_list[primary_index]['name']} "
                    f"(peak={primary_result['peak']:.4f}, rms={primary_result['rms']:.4f})\n"
                )

            if primary_index is None:
                primary_index = 0

            if secondary_index is None:
                self.queue_log("No live microphone signal was detected. Secondary set to None. Check mic connection/input permissions.\n")
            elif self.is_same_audio_source(
                self.primary_device_list[primary_index],
                self.secondary_device_list[secondary_index],
            ):
                self.queue_log("Microphone candidate matched primary source. Secondary set to None.\n")
                secondary_index = None
            else:
                self.queue_log(
                    "Secondary microphone signal detected: "
                    f"{self.secondary_device_list[secondary_index]['name']} "
                    f"(peak={secondary_result['peak']:.4f}, rms={secondary_result['rms']:.4f})\n"
                )

            self.ui_queue.put(("recommended_device_selection", primary_index, secondary_index))
            self.queue_log("Recommended audio sources selected after live signal test.\n")
            self.queue_log(f"Primary: {self.primary_device_list[primary_index]['name']}", "recommended_source")
            if secondary_index is not None:
                self.queue_log(f"Secondary: {self.secondary_device_list[secondary_index]['name']}\n", "recommended_source")
            else:
                self.queue_log("Secondary: None\n")
            self.queue_status("Audio source recommendation done")
        except Exception as e:
            self.queue_log(f"Source recommendation failed: {e}\n")
            self.queue_status("Source recommendation failed")
        finally:
            self.source_testing = False
            self.ui_queue.put(("refresh_button", False))

    def is_system_capture_name(self, name):
        lowered = name.lower()
        system_keywords = [
            "stereo mix",
            "스테레오 믹스",
            "cable output",
            "vb-audio",
            "what u hear",
            "wave out",
        ]
        mic_keywords = ["microphone", "마이크", "headset mic", "헤드셋 마이크"]
        return any(keyword in lowered for keyword in system_keywords) and not any(keyword in lowered for keyword in mic_keywords)

    def is_microphone_name(self, name):
        lowered = name.lower()
        mic_keywords = [
            "microphone",
            "mic",
            "마이크",
            "headset mic",
            "헤드셋 마이크",
            "array",
        ]
        system_keywords = ["stereo mix", "스테레오 믹스", "cable output", "vb-audio"]
        return any(keyword in lowered for keyword in mic_keywords) and not any(keyword in lowered for keyword in system_keywords)

    def is_same_audio_source(self, primary_entry, secondary_entry):
        if primary_entry is None or secondary_entry is None:
            return False
        return (
            primary_entry.get("kind") == secondary_entry.get("kind")
            and primary_entry.get("hostapi") == secondary_entry.get("hostapi")
            and primary_entry.get("device_id") == secondary_entry.get("device_id")
        )

    def find_device_index(self, keywords, device_list=None):
        device_list = device_list or self.primary_device_list
        normalized_keywords = [keyword.lower() for keyword in keywords]
        for index, entry in enumerate(device_list):
            lowered = entry["name"].lower()
            if all(keyword in lowered for keyword in normalized_keywords):
                return index
        return None

    def get_system_audio_candidates(self):
        keyword_sets = [
            ["windows wasapi", "cable output"],
            ["windows wasapi", "stereo mix"],
            ["windows directsound", "cable output"],
            ["windows directsound", "stereo mix"],
            ["mme", "cable output"],
            ["mme", "stereo mix"],
        ]
        return self.collect_candidate_indices(keyword_sets, self.primary_device_list)

    def get_microphone_candidates(self):
        keyword_sets = [
            ["windows wasapi", "microphone"],
            ["windows wasapi", "마이크"],
            ["windows directsound", "microphone"],
            ["windows directsound", "마이크"],
            ["mme", "microphone"],
            ["mme", "마이크"],
        ]
        return self.collect_candidate_indices(keyword_sets, self.secondary_device_list)

    def collect_candidate_indices(self, keyword_sets, device_list):
        seen = set()
        candidates = []
        for keywords in keyword_sets:
            index = self.find_device_index(keywords, device_list)
            if index is not None and index not in seen:
                seen.add(index)
                candidates.append(index)
        return candidates

    def find_best_live_source(self, candidate_indices, meter_source):
        best = None
        for index in candidate_indices:
            device_list = self.primary_device_list if meter_source == "primary" else self.secondary_device_list
            entry = device_list[index]
            name = entry["name"]
            self.queue_log(f"Testing {meter_source}: {name}")
            self.ui_queue.put(("device_selection", index if meter_source == "primary" else None, index if meter_source == "secondary" else None))
            result = self.measure_device_signal(entry, meter_source=meter_source)
            if result["ok"]:
                self.queue_log(f"  signal peak={result['peak']:.4f}, rms={result['rms']:.4f}\n")
                if best is None or result["rms"] > best["rms"]:
                    best = {"index": index, **result}
            else:
                self.queue_log(f"  no usable signal ({result['message']})\n")
        return best

    def measure_device_signal(self, entry, meter_source, seconds=2.2):
        if entry.get("kind") == "soundcard_loopback":
            return self.measure_soundcard_signal(entry, meter_source, seconds)

        rate = self.get_device_default_rate(entry)
        chunks = []

        def callback(indata, frames, callback_time, status):
            if status:
                return
            data = indata.copy()
            chunks.append(data)
            self.update_audio_level(meter_source, data)

        try:
            with sd.InputStream(
                device=entry["device_id"],
                samplerate=rate,
                channels=entry.get("channels", CHANNELS),
                dtype="float32",
                blocksize=1024,
                callback=callback,
                extra_settings=self.get_stream_extra_settings(entry)
            ):
                time.sleep(seconds)
        except Exception as e:
            return {"ok": False, "peak": 0.0, "rms": 0.0, "message": str(e)}

        if not chunks:
            return {"ok": False, "peak": 0.0, "rms": 0.0, "message": "no samples captured"}

        audio = np.concatenate(chunks, axis=0)
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
        ok = peak >= 0.003 or rms >= 0.0008
        message = "live signal detected" if ok else "signal below threshold"
        return {"ok": ok, "peak": peak, "rms": rms, "message": message}

    def measure_soundcard_signal(self, entry, meter_source, seconds=2.2):
        if sc is None:
            return {"ok": False, "peak": 0.0, "rms": 0.0, "message": "soundcard package is not installed"}

        rate = 48000
        try:
            mic = sc.get_microphone(entry["device_id"], include_loopback=True)
            with mic.recorder(samplerate=rate, channels=entry.get("channels", 2)) as recorder:
                audio = recorder.record(numframes=int(rate * seconds))
        except Exception as e:
            return {"ok": False, "peak": 0.0, "rms": 0.0, "message": str(e)}

        if audio is None or len(audio) == 0:
            return {"ok": False, "peak": 0.0, "rms": 0.0, "message": "no samples captured"}

        self.update_audio_level(meter_source, audio)
        peak = float(np.max(np.abs(audio)))
        rms = float(np.sqrt(np.mean(audio ** 2)))
        ok = peak >= 0.003 or rms >= 0.0008
        message = "live signal detected" if ok else "signal below threshold"
        return {"ok": ok, "peak": peak, "rms": rms, "message": message}

    def find_first_device_index(self, keyword_sets, device_list=None):
        device_list = device_list or self.primary_device_list
        for keywords in keyword_sets:
            index = self.find_device_index(keywords, device_list)
            if index is not None:
                return index
        return None

    def device_priority(self, hostapi_name):
        if hostapi_name == "Windows WASAPI":
            return 0
        if hostapi_name == "Windows DirectSound":
            return 1
        if hostapi_name == "MME":
            return 2
        return 3

    def get_preferred_default_input(self, devices, hostapis):
        for hostapi in hostapis:
            if hostapi['name'] == "Windows WASAPI":
                dev_id = hostapi.get('default_input_device', -1)
                if dev_id is not None and dev_id >= 0 and devices[dev_id]['max_input_channels'] > 0:
                    return dev_id
        return sd.default.device[0]

    def get_device_default_rate(self, device_id):
        if isinstance(device_id, dict):
            if device_id.get("kind") == "soundcard_loopback":
                return 48000
            device_id = device_id["device_id"]
        if device_id is None:
            device_id = sd.default.device[0]
        return int(sd.query_devices(device_id)['default_samplerate'])

    def get_stream_extra_settings(self, entry):
        return None

    def get_recording_sample_rate(self, primary_device, secondary_device):
        candidates = [
            48000,
            44100,
            SAMPLE_RATE,
        ]

        if getattr(self, "primary_source_enabled", True):
            candidates.insert(0, self.get_device_default_rate(primary_device))

        if secondary_device is not None:
            candidates.insert(0, self.get_device_default_rate(secondary_device))

        for rate in dict.fromkeys(candidates):
            try:
                if getattr(self, "primary_source_enabled", True) and not (
                    isinstance(primary_device, dict) and primary_device.get("kind") == "soundcard_loopback"
                ):
                    sd.check_input_settings(
                        device=primary_device["device_id"] if isinstance(primary_device, dict) else primary_device,
                        samplerate=rate,
                        channels=primary_device.get("channels", CHANNELS) if isinstance(primary_device, dict) else CHANNELS,
                        dtype="float32"
                    )
                if secondary_device is not None:
                    sd.check_input_settings(
                        device=secondary_device["device_id"] if isinstance(secondary_device, dict) else secondary_device,
                        samplerate=rate,
                        channels=secondary_device.get("channels", CHANNELS) if isinstance(secondary_device, dict) else CHANNELS,
                        dtype="float32"
                    )
                return rate
            except Exception:
                pass

        if secondary_device is not None:
            return self.get_device_default_rate(secondary_device)
        return self.get_device_default_rate(primary_device)

    def apply_saved_source_selection(self):
        primary_name = self.settings.get("primary_source_name", "")
        secondary_name = self.settings.get("secondary_source_name", "None")

        primary_index = self.find_saved_source_index(primary_name, self.primary_device_list)
        if primary_index is None and self.primary_device_list:
            primary_index = 0

        if primary_index is not None:
            self.device_combo.current(primary_index)
            self.selected_device = self.primary_device_list[primary_index]

        secondary_index = self.find_saved_source_index(secondary_name, self.secondary_device_list)
        if secondary_index is not None:
            self.secondary_device_combo.current(secondary_index + 1)
            self.selected_secondary_device = self.secondary_device_list[secondary_index]
        else:
            self.secondary_device_combo.current(0)
            self.selected_secondary_device = None

        self.save_user_settings()

    def find_saved_source_index(self, saved_name, device_list):
        if not saved_name or saved_name == "None":
            return None

        for index, entry in enumerate(device_list):
            if entry["name"] == saved_name:
                return index

        saved_tail = saved_name.split("] ", 1)[-1]
        for index, entry in enumerate(device_list):
            if entry["name"].split("] ", 1)[-1] == saved_tail:
                return index

        return None

