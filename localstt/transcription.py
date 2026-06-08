import datetime
import os
import threading
import time
from tkinter import filedialog, messagebox

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel

from .config import (
    APP_DIR,
    REALTIME_CHUNK_DURATION,
    REALTIME_PROMPT_CHARS,
    REALTIME_SAMPLE_RATE,
    STT_LANGUAGE_CODES,
)
from .translation import SRT_MAX_PARAGRAPH_SECONDS, SRT_MIN_PARAGRAPH_SECONDS


class TranscriptionMixin:
    def get_transcription_language(self):
        value = getattr(self, "stt_language", "English")
        if hasattr(self, "stt_language_var"):
            value = self.stt_language_var.get()

        return STT_LANGUAGE_CODES.get(value, "en")

    def load_model(self):
        try:
            self.model_path = str(self.get_selected_model_path())
            self.set_status("Loading model...")
            self.log(f"Loading {self.stt_language} STT model: {self.selected_model_name}")
            self.log(f"Model path: {self.model_path}")

            self.model = WhisperModel(
                self.model_path,
                device="cpu",
                compute_type="int8"
            )

            self.realtime_model = self.model

            self.set_status("Model loaded")
            self.log("Model loaded successfully.\n")

        except Exception as e:
            self.set_status("Model load failed")
            messagebox.showerror("Model Load Error", str(e))
            self.log(f"ERROR: {e}\n")

    def stream_transcribe(self):
        """Continuously transcribe audio chunks as they're being recorded."""
        try:
            chunk_duration = REALTIME_CHUNK_DURATION
            frames_per_chunk = int(self.recording_sample_rate * chunk_duration)
            last_transcribed_index = 0
            consecutive_errors = 0
            realtime_context = ""
            realtime_paragraph_buffer = []
            realtime_transcript_header_shown = False
            realtime_translation_header_shown = False
            self.queue_log(
                "Real-time STT speed mode: "
                f"{chunk_duration}s chunks, beam_size=1, memory audio.\n"
            )
            
            while self.recording:
                try:
                    current_frames = self.audio_frames[:]
                    new_frames = current_frames[last_transcribed_index:]
                    new_sample_count = sum(len(frame) for frame in new_frames)
                    chunk_start_seconds = sum(len(frame) for frame in current_frames[:last_transcribed_index]) / self.recording_sample_rate
                    
                    # Wait until enough new audio samples have arrived.
                    if new_sample_count >= frames_per_chunk:
                        audio_chunk = np.concatenate(new_frames, axis=0) if new_frames else None
                        
                        if audio_chunk is not None and len(audio_chunk) > self.recording_sample_rate * 1:  # At least 1 second
                            realtime_audio = self.prepare_realtime_audio(audio_chunk)
                            
                            try:
                                realtime_model = self.realtime_model or self.model
                                segments, _ = realtime_model.transcribe(
                                    realtime_audio,
                                    language=self.get_transcription_language(),
                                    beam_size=1,
                                    best_of=1,
                                    vad_filter=True,
                                    without_timestamps=False,
                                    condition_on_previous_text=False,
                                    initial_prompt=realtime_context or None
                                )
                                
                                segment_list = list(segments)
                                if segment_list:
                                    realtime_lines = self.build_realtime_lines(segment_list, chunk_start_seconds)
                                    for start_time, end_time, text in realtime_lines:
                                        self.append_translation_text(realtime_paragraph_buffer, start_time, end_time, text)

                                    for start_time, end_time, paragraph in self.pop_completed_translation_paragraphs(realtime_paragraph_buffer):
                                        if not realtime_transcript_header_shown:
                                            self.queue_transcript("\n[Real-time Results]")
                                            realtime_transcript_header_shown = True
                                        self.queue_transcript(self.format_transcript_paragraph(start_time, end_time, paragraph) + "\n")

                                    chunk_text = " ".join(segment.text.strip() for segment in segment_list if segment.text.strip())
                                    if chunk_text:
                                        realtime_context = (realtime_context + " " + chunk_text).strip()[-REALTIME_PROMPT_CHARS:]
                                    consecutive_errors = 0
                            except Exception as e:
                                consecutive_errors += 1
                                if consecutive_errors <= 1:  # Log only first error
                                    self.queue_log(f"Transcription notice: {str(e)[:50]}\n")

                            last_transcribed_index = len(current_frames)
                    
                    time.sleep(0.25)
                    
                except Exception as e:
                    self.queue_log(f"Stream transcribe error: {str(e)[:100]}\n")
                    time.sleep(1)
                    
        except Exception as e:
            self.queue_log(f"Fatal stream transcription error: {e}\n")
        finally:
            if "realtime_paragraph_buffer" in locals():
                for start_time, end_time, paragraph in self.pop_completed_translation_paragraphs(realtime_paragraph_buffer, force=True):
                    if paragraph and not realtime_transcript_header_shown:
                        self.queue_transcript("\n[Real-time Results]")
                        realtime_transcript_header_shown = True
                    self.queue_transcript(self.format_transcript_paragraph(start_time, end_time, paragraph) + "\n")

    def prepare_realtime_audio(self, audio_chunk):
        audio = np.asarray(audio_chunk, dtype=np.float32)
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        if self.recording_sample_rate == REALTIME_SAMPLE_RATE:
            return audio

        duration = len(audio) / self.recording_sample_rate
        target_len = max(1, int(duration * REALTIME_SAMPLE_RATE))
        source_x = np.linspace(0.0, duration, num=len(audio), endpoint=False)
        target_x = np.linspace(0.0, duration, num=target_len, endpoint=False)
        return np.interp(target_x, source_x, audio).astype(np.float32)

    def final_transcribe(self, file_path):
        """Final full transcription after recording stops."""
        try:
            self.queue_progress(20, "Final STT")
            self.queue_status("Final transcription...")
            self.queue_transcript("=" * 50)
            self.queue_transcript("FINAL TRANSCRIPTION")
            self.queue_transcript("=" * 50 + "\n")

            segments, info = self.model.transcribe(
                file_path,
                language=self.get_transcription_language(),
                beam_size=5,
                vad_filter=True,
                without_timestamps=False
            )
            
            self.queue_progress(45, "Collecting segments")
            segments_list = list(segments)
            
            srt_lines = []
            paragraph_buffer = []
            transcript_paragraph_lines = []
            segment_count = 0
            paragraph_count = 0
            
            for seg in segments_list:
                segment_count += 1
                text_content = seg.text.strip()

                self.append_translation_text(paragraph_buffer, seg.start, seg.end, text_content)
                for paragraph_start, paragraph_end, paragraph in self.pop_completed_translation_paragraphs(
                    paragraph_buffer,
                    min_duration=SRT_MIN_PARAGRAPH_SECONDS,
                    max_duration=SRT_MAX_PARAGRAPH_SECONDS,
                ):
                    paragraph_count += 1
                    paragraph_start_srt = self.format_time_srt(paragraph_start)
                    paragraph_end_srt = self.format_time_srt(paragraph_end)
                    srt_lines.append(str(paragraph_count))
                    srt_lines.append(f"{paragraph_start_srt} --> {paragraph_end_srt}")
                    srt_lines.append(paragraph)
                    srt_lines.append("")

                    paragraph_line = self.format_transcript_paragraph(paragraph_start, paragraph_end, paragraph, srt_time=True)
                    transcript_paragraph_lines.append(paragraph_line)
                    self.queue_transcript(paragraph_line + "\n")
                
                if segments_list:
                    progress = 45 + int(45 * segment_count / len(segments_list))
                    self.queue_progress(progress, f"Writing SRT {segment_count}/{len(segments_list)}")
                self.queue_status(f"Final transcription... ({segment_count} segments)")

            for paragraph_start, paragraph_end, paragraph in self.pop_completed_translation_paragraphs(paragraph_buffer, force=True):
                paragraph_count += 1
                paragraph_start_srt = self.format_time_srt(paragraph_start)
                paragraph_end_srt = self.format_time_srt(paragraph_end)
                srt_lines.append(str(paragraph_count))
                srt_lines.append(f"{paragraph_start_srt} --> {paragraph_end_srt}")
                srt_lines.append(paragraph)
                srt_lines.append("")

                paragraph_line = self.format_transcript_paragraph(paragraph_start, paragraph_end, paragraph, srt_time=True)
                transcript_paragraph_lines.append(paragraph_line)
                self.queue_transcript(paragraph_line + "\n")

            self.queue_progress(95, "Saving SRT")
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            srt_path = os.path.join(APP_DIR, f"{base_name}.srt")
            
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_lines))

            self.queue_transcript("=" * 50)
            self.queue_log(f"SRT File saved: {srt_path}\n")
            self.queue_progress(100, "Done")
            self.queue_status(f"Done ({segment_count} segments)")

        except Exception as e:
            self.queue_progress(0, "Failed")
            self.queue_status("Transcription failed")
            self.queue_messagebox_error("Transcription Error", str(e))
            self.queue_log(f"ERROR: {e}\n")
        finally:
            self.final_processing = False

    def transcribe_file_dialog(self):
        if self.final_processing:
            self.log("Another final STT/save process is still running.\n")
            return

        if self.model is None:
            self.load_model()

        if self.model is None:
            return

        self.set_audio_file_button_state(True)
        file_path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[
                ("Audio files", "*.wav *.mp3 *.m4a *.flac *.aac *.ogg"),
                ("All files", "*.*")
            ]
        )

        if file_path:
            self.log(f"Audio file selected: {file_path}")
            self.log("Starting audio file transcription. Output will be SRT only.\n")
            self.queue_status("Audio file transcription queued...")
            self.queue_progress(5, "Audio file queued")
            threading.Thread(
                target=self.transcribe_file,
                args=(file_path,),
                daemon=True
            ).start()
        else:
            self.set_audio_file_button_state(False)

    def transcribe_file(self, file_path):
        try:
            self.final_processing = True
            self.queue_progress(10, "Loading audio")
            self.queue_status("Loading audio file for STT...")
            self.queue_log(f"File: {file_path}\n")
            self.log_audio_file_info(file_path, "Loaded audio file")
            self.queue_transcript("=" * 50)
            self.queue_transcript("AUDIO FILE TRANSCRIPTION")
            self.queue_transcript("=" * 50 + "\n")

            self.queue_status("Transcribing selected audio file...")
            self.queue_progress(20, "Audio STT")
            segments, info = self.model.transcribe(
                file_path,
                language=self.get_transcription_language(),
                beam_size=5,
                vad_filter=True,
                without_timestamps=False
            )

            self.queue_status("Collecting transcription segments...")
            self.queue_progress(45, "Collecting segments")
            segments_list = list(segments)
            self.queue_log(f"Audio file STT segments detected: {len(segments_list)}\n")

            srt_lines = []
            paragraph_buffer = []
            segment_count = 0
            paragraph_count = 0
            for segment in segments_list:
                segment_count += 1
                text_content = segment.text.strip()

                self.append_translation_text(paragraph_buffer, segment.start, segment.end, text_content)
                for paragraph_start, paragraph_end, paragraph in self.pop_completed_translation_paragraphs(
                    paragraph_buffer,
                    min_duration=SRT_MIN_PARAGRAPH_SECONDS,
                    max_duration=SRT_MAX_PARAGRAPH_SECONDS,
                ):
                    paragraph_count += 1
                    paragraph_start_srt = self.format_time_srt(paragraph_start)
                    paragraph_end_srt = self.format_time_srt(paragraph_end)
                    srt_lines.append(str(paragraph_count))
                    srt_lines.append(f"{paragraph_start_srt} --> {paragraph_end_srt}")
                    srt_lines.append(paragraph)
                    srt_lines.append("")

                    paragraph_line = self.format_transcript_paragraph(paragraph_start, paragraph_end, paragraph, srt_time=True)
                    self.queue_transcript(paragraph_line + "\n")
                if segments_list:
                    progress = 45 + int(45 * segment_count / len(segments_list))
                    self.queue_progress(progress, f"Writing SRT {segment_count}/{len(segments_list)}")
                self.queue_status(f"Transcribing... ({segment_count} segments)")

            for paragraph_start, paragraph_end, paragraph in self.pop_completed_translation_paragraphs(paragraph_buffer, force=True):
                paragraph_count += 1
                paragraph_start_srt = self.format_time_srt(paragraph_start)
                paragraph_end_srt = self.format_time_srt(paragraph_end)
                srt_lines.append(str(paragraph_count))
                srt_lines.append(f"{paragraph_start_srt} --> {paragraph_end_srt}")
                srt_lines.append(paragraph)
                srt_lines.append("")

                paragraph_line = self.format_transcript_paragraph(paragraph_start, paragraph_end, paragraph, srt_time=True)
                self.queue_transcript(paragraph_line + "\n")

            if segment_count == 0:
                self.queue_transcript("No speech segment was detected in this audio file.\n")
                self.queue_log("No speech segment detected. Check file volume/language/source audio.\n")

            self.queue_progress(95, "Saving SRT")
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            srt_path = os.path.join(APP_DIR, f"{base_name}.srt")

            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_lines))

            self.queue_transcript("=" * 50)
            self.queue_log(f"SRT File saved: {srt_path}\n")
            self.queue_progress(100, "Done")
            self.queue_status(f"Done ({segment_count} segments)")

        except Exception as e:
            self.queue_progress(0, "Failed")
            self.queue_status("Transcription failed")
            self.queue_messagebox_error("Transcription Error", str(e))
            self.queue_log(f"ERROR: {e}\n")
        finally:
            self.final_processing = False
            self.ui_queue.put(("audio_file_button", False))

    def log_audio_file_info(self, file_path, label):
        try:
            info = sf.info(file_path)
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            self.queue_log(
                f"{label}: duration={info.duration:.1f}s, "
                f"samplerate={info.samplerate}Hz, channels={info.channels}, "
                f"format={info.format}, size={size_mb:.2f}MB\n"
            )
        except Exception as e:
            self.queue_log(f"{label}: unable to read audio metadata ({e})\n")

