import datetime
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import numpy as np
import sounddevice as sd
import soundfile as sf
try:
    import soundcard as sc
except ImportError:
    sc = None

from .config import APP_DIR, CHANNELS


class AudioMixin:
    def toggle_recording(self):
        if self.recording:
            self.stop_and_transcribe()
        else:
            self.start_recording()

    def audio_callback(self, indata, frames, time, status):
        if status:
            print(status)

        if self.recording:
            self.audio_queue.put(self.to_mono(indata))

    def secondary_audio_callback(self, indata, frames, time, status):
        if status:
            print(status)

        if self.recording:
            self.secondary_audio_queue.put(self.to_mono(indata))

    def to_mono(self, audio_data):
        data = audio_data.copy()
        if data.ndim > 1 and data.shape[1] > 1:
            data = np.mean(data, axis=1, keepdims=True)
        return data.astype("float32", copy=False)

    def get_selected_devices(self):
        self.primary_source_enabled = self.primary_source_var.get()
        self.secondary_source_enabled = self.secondary_source_var.get()

        current_selection = self.device_combo.current()
        if self.primary_source_enabled and current_selection >= 0 and current_selection < len(self.primary_device_list):
            primary_device = self.primary_device_list[current_selection]
            primary_name = self.primary_device_list[current_selection]["name"]
        elif self.primary_source_enabled:
            primary_device = None
            primary_name = "Default input"
        else:
            primary_device = None
            primary_name = None

        secondary_selection = self.secondary_device_combo.current()
        if self.secondary_source_enabled and secondary_selection > 0 and secondary_selection <= len(self.secondary_device_list):
            secondary_device = self.secondary_device_list[secondary_selection - 1]
            secondary_name = self.secondary_device_list[secondary_selection - 1]["name"]
            if primary_device and secondary_device["device_id"] == primary_device["device_id"]:
                secondary_device = None
                secondary_name = None
        else:
            secondary_device = None
            secondary_name = None

        return primary_device, primary_name, secondary_device, secondary_name

    def start_recording(self):
        if self.recording:
            self.log("Already recording.\n")
            return

        if self.source_testing:
            self.log("Wait until Refresh / Recommend finishes testing sources.\n")
            return

        if self.final_processing:
            self.log("Final STT/save is still running. Wait until it finishes before starting a new recording.\n")
            return

        if self.model is None:
            self.load_model()

        if self.model is None:
            return

        primary_device, primary_name, secondary_device, secondary_name = self.get_selected_devices()
        self.selected_device = primary_device
        self.selected_secondary_device = secondary_device
        if primary_name:
            self.log(f"Using device: {primary_name}\n")
        else:
            self.log("Primary source: Off\n")
        if secondary_name:
            self.log(f"Using secondary source: {secondary_name}\n")
        else:
            self.log("Secondary source: Off/None\n")

        if not primary_name and not secondary_name:
            self.log("At least one source must be enabled before recording.\n")
            self.set_status("No source enabled")
            return

        self.recording_sample_rate = self.get_recording_sample_rate(
            self.selected_device,
            self.selected_secondary_device
        )
        self.log(f"Recording sample rate: {self.recording_sample_rate} Hz\n")

        self.audio_frames = []
        self.audio_queue = queue.Queue()
        self.secondary_audio_queue = queue.Queue()
        self.level_last_update = {"primary": 0, "secondary": 0}
        self.level_last_signal = {"primary": None, "secondary": None}
        self.silent_warning_shown_sources = set()
        self.last_silent_check = 0
        self.queue_clear_levels()
        self.transcribed_frames = 0
        self.recording = True
        self.recording_start_time = datetime.datetime.now()
        self.recording_limit_seconds = 60 * 60
        self.recording_warning_seconds = 50 * 60
        self.recording_warning_shown = False
        self.recording_extension_available = False
        self.streaming_transcription = self.streaming_var.get()
        self.settings["streaming_transcription"] = self.streaming_transcription
        self.save_user_settings()
        self.queue_progress(0, "Recording")
        self.extend_button.config(state=tk.DISABLED)
        self.time_label.config(fg="black")
        self.set_recording_button_state(True)

        try:
            if self.primary_source_enabled:
                if isinstance(self.selected_device, dict) and self.selected_device.get("kind") == "soundcard_loopback":
                    threading.Thread(target=self.collect_soundcard_loopback, daemon=True).start()
                else:
                    self.stream = sd.InputStream(
                        device=self.selected_device["device_id"] if isinstance(self.selected_device, dict) else self.selected_device,
                        samplerate=self.recording_sample_rate,
                        channels=self.selected_device.get("channels", CHANNELS) if isinstance(self.selected_device, dict) else CHANNELS,
                        dtype="float32",
                        blocksize=1024,
                        callback=self.audio_callback,
                        extra_settings=self.get_stream_extra_settings(self.selected_device)
                    )
                    self.stream.start()

            if self.secondary_source_enabled and self.selected_secondary_device is not None:
                self.secondary_stream = sd.InputStream(
                    device=self.selected_secondary_device["device_id"] if isinstance(self.selected_secondary_device, dict) else self.selected_secondary_device,
                    samplerate=self.recording_sample_rate,
                    channels=self.selected_secondary_device.get("channels", CHANNELS) if isinstance(self.selected_secondary_device, dict) else CHANNELS,
                    dtype="float32",
                    blocksize=1024,
                    callback=self.secondary_audio_callback,
                    extra_settings=self.get_stream_extra_settings(self.selected_secondary_device)
                )
                self.secondary_stream.start()

            self.set_status("Recording...")
            self.log("Recording started.\n")
            if self.primary_source_enabled and self.selected_secondary_device is not None:
                self.log("Primary and secondary sources will be mixed into one recording.\n")
            
            if self.streaming_transcription:
                self.log("Real-time transcription enabled.\n")

            threading.Thread(target=self.collect_audio, daemon=True).start()
            threading.Thread(target=self.update_recording_time, daemon=True).start()
            
            if self.streaming_transcription:
                threading.Thread(target=self.stream_transcribe, daemon=True).start()

        except Exception as e:
            self.recording = False
            self.set_recording_button_state(False)
            try:
                if self.stream:
                    self.stream.stop()
                    self.stream.close()
                if self.secondary_stream:
                    self.secondary_stream.stop()
                    self.secondary_stream.close()
            except Exception:
                pass
            finally:
                self.stream = None
                self.secondary_stream = None
            self.set_status("Recording failed")
            messagebox.showerror("Recording Error", str(e))
            self.log(f"ERROR: {e}\n")
            self.log("Tip: Try the [Windows WASAPI] version of the same devices, or use VB-Cable/Stereo Mix as the secondary source.\n")

    def collect_soundcard_loopback(self):
        if sc is None:
            self.queue_log("soundcard package is not installed; cannot capture system loopback.\n")
            return

        try:
            mic = sc.get_microphone(self.selected_device["device_id"], include_loopback=True)
            chunk_frames = int(self.recording_sample_rate * 0.1)
            with mic.recorder(
                samplerate=self.recording_sample_rate,
                channels=self.selected_device.get("channels", 2)
            ) as recorder:
                while self.recording:
                    data = recorder.record(numframes=chunk_frames)
                    if data is None or len(data) == 0:
                        continue
                    self.audio_queue.put(self.to_mono(data))
        except Exception as e:
            self.queue_log(f"System loopback capture error: {e}\n")

    def collect_audio(self):
        while self.recording:
            primary_data = None
            secondary_data = None

            if self.primary_source_enabled:
                try:
                    primary_data = self.audio_queue.get(timeout=0.05)
                except queue.Empty:
                    pass

            if self.secondary_source_enabled and self.selected_secondary_device is not None:
                try:
                    secondary_data = self.secondary_audio_queue.get(timeout=0.05)
                except queue.Empty:
                    pass

            mixed_data = self.mix_audio_sources(primary_data, secondary_data)
            if mixed_data is None:
                continue

            self.audio_frames.append(mixed_data)
            if primary_data is not None:
                self.update_audio_level("primary", primary_data)
            if secondary_data is not None:
                self.update_audio_level("secondary", secondary_data)

    def mix_audio_sources(self, primary_data, secondary_data):
        if primary_data is None and secondary_data is None:
            return None
        if primary_data is None:
            return secondary_data
        if secondary_data is None:
            return primary_data

        min_len = min(len(primary_data), len(secondary_data))
        if min_len == 0:
            return primary_data

        secondary_data = secondary_data[:min_len]
        mixed = primary_data.copy()
        mixed[:min_len] = (primary_data[:min_len] + secondary_data) * 0.5
        return np.clip(mixed, -1.0, 1.0)

    def stop_and_transcribe(self):
        if not self.recording:
            self.log("Not recording.\n")
            return

        self.recording = False
        self.set_recording_button_state(False)
        self.extend_button.config(state=tk.DISABLED)

        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
            if self.secondary_stream:
                self.secondary_stream.stop()
                self.secondary_stream.close()
        except Exception:
            pass
        finally:
            self.stream = None
            self.secondary_stream = None

        if not self.audio_frames:
            self.log("No audio captured.\n")
            self.queue_clear_levels()
            return

        audio = np.concatenate(self.audio_frames, axis=0)
        captured_seconds = len(audio) / self.recording_sample_rate if self.recording_sample_rate else 0
        peak_level = float(np.max(np.abs(audio))) if len(audio) else 0.0
        rms_level = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_path, audio_format = self.save_recording_audio(audio, timestamp)

        self.log(f"\nRecording saved: {audio_path}")
        self.log(f"Captured audio: {captured_seconds:.1f}s, samples={len(audio)}, peak={peak_level:.4f}, rms={rms_level:.4f}")
        try:
            size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            info = sf.info(audio_path)
            self.log(
                f"Saved {audio_format} info: duration={info.duration:.1f}s, "
                f"samplerate={info.samplerate}Hz, channels={info.channels}, size={size_mb:.2f}MB"
            )
        except Exception as e:
            self.log(f"Saved audio info unavailable: {e}")
        if peak_level < 0.001:
            self.log("Warning: captured audio appears nearly silent. Check selected source and Windows routing.")
        self.log("Performing final transcription...\n")
        self.time_label.config(text="Time: 00:00")
        self.time_label.config(fg="black")
        self.queue_clear_levels()
        self.queue_progress(15, "Audio saved")
        self.final_processing = True

        threading.Thread(
            target=self.final_transcribe,
            args=(audio_path,),
            daemon=True
        ).start()

    def save_recording_audio(self, audio, timestamp):
        mp3_path = os.path.join(APP_DIR, f"recording_{timestamp}.mp3")
        try:
            sf.write(mp3_path, audio, self.recording_sample_rate, format="MP3")
            return mp3_path, "MP3"
        except Exception as e:
            wav_path = os.path.join(APP_DIR, f"recording_{timestamp}.wav")
            sf.write(wav_path, audio, self.recording_sample_rate)
            self.log(f"MP3 save failed; saved WAV instead: {e}")
            return wav_path, "WAV"

