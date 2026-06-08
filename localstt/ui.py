import datetime
import os
import queue
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, scrolledtext, ttk

import numpy as np

from .config import APP_DIR, STT_LANGUAGE_CHOICES, list_available_model_names


RECOMMENDED_SOURCE_COLOR = "#0b7d2b"


class UIMixin:
    def build_ui(self):
        style = ttk.Style()
        self.default_combo_style = "TCombobox"
        self.recommended_combo_style = "Recommended.TCombobox"
        style.configure(self.recommended_combo_style, foreground=RECOMMENDED_SOURCE_COLOR)
        style.map(self.recommended_combo_style, foreground=[("readonly", RECOMMENDED_SOURCE_COLOR)])

        self.window_alpha_var = tk.DoubleVar(value=self.window_alpha)
        self.always_on_top_var = tk.BooleanVar(value=self.always_on_top)
        self.compact_auto_opacity_var = tk.BooleanVar(value=self.compact_auto_opacity)
        self.compact_alpha_var = tk.DoubleVar(value=self.compact_alpha)
        self.silent_source_warning_var = tk.BooleanVar(value=self.silent_source_warning)
        self.font_size_var = tk.IntVar(value=self.text_font_size)
        self.font_color_var = tk.StringVar(value=self.text_fg)
        self.stt_language_var = tk.StringVar(value=self.stt_language)
        self.model_var = tk.StringVar(value=self.selected_model_name)
        self.primary_source_var = tk.BooleanVar(value=self.primary_source_enabled)
        self.secondary_source_var = tk.BooleanVar(value=self.secondary_source_enabled)

        self.preferences_window = tk.Toplevel(self.root)
        self.preferences_window.title("Preferences")
        self.preferences_window.geometry("900x360")
        self.preferences_window.withdraw()
        self.preferences_window.protocol("WM_DELETE_WINDOW", self.hide_preferences)

        pref_body = tk.Frame(self.preferences_window)
        pref_body.pack(fill="both", expand=True, padx=10, pady=10)

        appearance_frame = tk.LabelFrame(pref_body, text="Appearance / STT")
        appearance_frame.pack(fill="x", pady=(0, 8))

        tk.Label(appearance_frame, text="Opacity").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        tk.Scale(
            appearance_frame,
            variable=self.window_alpha_var,
            from_=0.35,
            to=1.0,
            resolution=0.05,
            orient=tk.HORIZONTAL,
            command=lambda value: self.apply_preferences(),
            length=180,
        ).grid(row=0, column=1, sticky="w", padx=5, pady=4)

        tk.Label(appearance_frame, text="Font size").grid(row=0, column=2, sticky="w", padx=5, pady=4)
        tk.Spinbox(
            appearance_frame,
            from_=8,
            to=24,
            width=5,
            textvariable=self.font_size_var,
            command=self.apply_preferences,
        ).grid(row=0, column=3, sticky="w", padx=5, pady=4)

        tk.Button(appearance_frame, text="Font Color", command=self.choose_font_color, width=12).grid(row=0, column=4, sticky="w", padx=5, pady=4)

        tk.Checkbutton(
            appearance_frame,
            text="Always on top",
            variable=self.always_on_top_var,
            command=self.apply_preferences,
        ).grid(row=0, column=5, columnspan=2, sticky="w", padx=5, pady=4)

        tk.Label(appearance_frame, text="STT Language").grid(row=1, column=5, sticky="w", padx=5, pady=4)
        self.language_combo = ttk.Combobox(
            appearance_frame,
            textvariable=self.stt_language_var,
            values=STT_LANGUAGE_CHOICES,
            state="readonly",
            width=10,
        )
        self.language_combo.grid(row=1, column=6, sticky="w", padx=5, pady=4)
        self.language_combo.bind("<<ComboboxSelected>>", self.on_language_selection_changed)

        tk.Label(appearance_frame, text="Model").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        self.model_combo = ttk.Combobox(
            appearance_frame,
            textvariable=self.model_var,
            values=list_available_model_names(),
            state="readonly",
            width=28,
        )
        self.model_combo.grid(row=1, column=1, columnspan=2, sticky="w", padx=5, pady=4)
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_selection_changed)

        meeting_frame = tk.LabelFrame(pref_body, text="Meeting Mode")
        meeting_frame.pack(fill="x", pady=(0, 8))

        tk.Checkbutton(
            meeting_frame,
            text="Compact auto opacity",
            variable=self.compact_auto_opacity_var,
            command=self.apply_preferences,
        ).grid(row=0, column=0, sticky="w", padx=5, pady=4)
        tk.Label(meeting_frame, text="Compact opacity").grid(row=0, column=1, sticky="w", padx=5, pady=4)
        tk.Scale(
            meeting_frame,
            variable=self.compact_alpha_var,
            from_=0.35,
            to=1.0,
            resolution=0.05,
            orient=tk.HORIZONTAL,
            command=lambda value: self.apply_preferences(),
            length=140,
        ).grid(row=0, column=2, sticky="w", padx=5, pady=4)
        tk.Checkbutton(
            meeting_frame,
            text="Silent source warning",
            variable=self.silent_source_warning_var,
            command=self.apply_preferences,
        ).grid(row=0, column=3, sticky="w", padx=5, pady=4)
        tk.Button(meeting_frame, text="Apply Meeting Mode", command=self.apply_meeting_mode, width=18).grid(row=0, column=4, sticky="w", padx=5, pady=4)
        tk.Button(meeting_frame, text="Open Output Folder", command=self.open_output_folder, width=18).grid(row=0, column=5, sticky="w", padx=5, pady=4)

        # Source selection and level meters
        device_frame = tk.LabelFrame(pref_body, text="Sound Source")
        device_frame.pack(fill="x")
        device_frame.columnconfigure(1, weight=1)
        device_frame.columnconfigure(3, weight=1)

        self.device_var = tk.StringVar()
        self.secondary_device_var = tk.StringVar()

        tk.Label(device_frame, text="Primary Source:", font=("Arial", 9)).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.device_var, width=54, state="readonly")
        self.device_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        self.device_combo.bind("<<ComboboxSelected>>", lambda event: self.on_source_selection_changed("primary"))
        self.primary_recommend_label = tk.Label(
            device_frame,
            text="",
            fg="white",
            bg=self.root.cget("bg"),
            font=("Arial", 8, "bold"),
            width=12,
            anchor="center",
        )
        self.primary_recommend_label.grid(row=0, column=2, sticky="w", padx=(0, 5), pady=2)
        self.primary_level_canvas = tk.Canvas(device_frame, width=260, height=18, bg="white", relief="sunken", bd=1)
        self.primary_level_canvas.grid(row=0, column=3, sticky="ew", padx=5, pady=2)
        self.refresh_button = tk.Button(device_frame, text="Refresh / Recommend", command=self.refresh_and_recommend_devices, width=20)
        self.refresh_button.grid(row=0, column=4, sticky="e", padx=5, pady=2)

        tk.Label(device_frame, text="Secondary:", font=("Arial", 9)).grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.secondary_device_combo = ttk.Combobox(device_frame, textvariable=self.secondary_device_var, width=54, state="readonly")
        self.secondary_device_combo.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        self.secondary_device_combo.bind("<<ComboboxSelected>>", lambda event: self.on_source_selection_changed("secondary"))
        self.secondary_recommend_label = tk.Label(
            device_frame,
            text="",
            fg="white",
            bg=self.root.cget("bg"),
            font=("Arial", 8, "bold"),
            width=12,
            anchor="center",
        )
        self.secondary_recommend_label.grid(row=1, column=2, sticky="w", padx=(0, 5), pady=2)
        self.secondary_level_canvas = tk.Canvas(device_frame, width=260, height=18, bg="white", relief="sunken", bd=1)
        self.secondary_level_canvas.grid(row=1, column=3, sticky="ew", padx=5, pady=2)

        # Top button frame
        self.compact_mode = False
        top = tk.Frame(self.root)
        self.top_frame = top
        top.pack(fill="x", padx=10, pady=10)

        tk.Button(top, text="Load Model", command=self.load_model, width=15).pack(side="left", padx=5)
        self.start_button = tk.Button(top, text="Start Recording", command=self.toggle_recording, width=18)
        self.start_button.pack(side="left", padx=5)
        self.audio_file_button = tk.Button(top, text="Audio File STT", command=self.transcribe_file_dialog, width=15)
        self.audio_file_button.pack(side="left", padx=5)
        tk.Button(top, text="Preferences", command=self.open_preferences, width=12).pack(side="left", padx=5)
        tk.Button(top, text="Clear", command=self.clear_text, width=10).pack(side="left", padx=5)
        tk.Checkbutton(top, text="Src1", variable=self.primary_source_var, command=self.on_source_enabled_changed).pack(side="left", padx=(12, 2))
        tk.Checkbutton(top, text="Src2", variable=self.secondary_source_var, command=self.on_source_enabled_changed).pack(side="left", padx=2)
        self.extend_button = tk.Button(top, text="+15 min", command=self.extend_recording_limit, width=8, state=tk.DISABLED)
        self.extend_button.pack(side="left", padx=(8, 2))
        tk.Button(top, text="Help", command=self.open_help, width=8).pack(side="right", padx=(18, 5))

        # Status and progress frame
        status_frame = tk.Frame(self.root)
        self.status_frame = status_frame
        status_frame.pack(fill="x", padx=10, pady=5)
        
        self.status = tk.Label(status_frame, text="Status: Ready", anchor="w", font=("Arial", 10, "bold"))
        self.status.pack(fill="x", side="left", expand=True)

        self.progress_label = tk.Label(status_frame, text="Process: Idle", anchor="e", font=("Arial", 8), width=16)
        self.progress_label.pack(side="left", padx=(8, 3))
        self.progress_bar = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, mode="determinate", maximum=100, value=0, length=90)
        self.progress_bar.pack(side="left", padx=(0, 3))
        self.progress_percent_label = tk.Label(status_frame, text="0%", anchor="w", font=("Arial", 8), width=4)
        self.progress_percent_label.pack(side="left", padx=(0, 8))

        tk.Label(status_frame, text="Src1", anchor="e", font=("Arial", 8)).pack(side="left", padx=(8, 2))
        self.status_primary_level_canvas = tk.Canvas(status_frame, width=90, height=14, bg="white", relief="sunken", bd=1)
        self.status_primary_level_canvas.pack(side="left", padx=(0, 6))

        tk.Label(status_frame, text="Src2", anchor="e", font=("Arial", 8)).pack(side="left", padx=(0, 2))
        self.status_secondary_level_canvas = tk.Canvas(status_frame, width=90, height=14, bg="white", relief="sunken", bd=1)
        self.status_secondary_level_canvas.pack(side="left", padx=(0, 8))
        
        # Recording time label
        self.time_label = tk.Label(status_frame, text="Time: 00:00", anchor="e", font=("Arial", 9))
        self.time_label.pack(side="right", padx=5)

        self.compact_frame = tk.Frame(self.root)
        self.compact_record_button = tk.Button(
            self.compact_frame,
            text="Start",
            command=self.toggle_recording,
            width=8,
            height=1,
            font=("Arial", 8),
            padx=2,
            pady=0,
            bd=1,
            highlightthickness=0,
        )
        self.compact_record_button.pack(side="left", padx=(0, 6))
        self.compact_time_label = tk.Label(self.compact_frame, text="Time: 00:00", anchor="w", font=("Arial", 8))
        self.compact_time_label.pack(side="left", fill="x", expand=True)
        self.compact_extend_button = tk.Button(
            self.compact_frame,
            text="+15 min",
            command=self.extend_recording_limit,
            width=8,
            height=1,
            font=("Arial", 8),
            padx=2,
            pady=0,
            bd=1,
            highlightthickness=0,
            state=tk.DISABLED,
        )
        self.compact_extend_button.pack(side="left", padx=(8, 4))
        self.compact_progress_label = tk.Label(self.compact_frame, text="Idle", anchor="e", font=("Arial", 7), width=10)
        self.compact_progress_label.pack(side="left", padx=(4, 3))
        self.compact_progress_bar = ttk.Progressbar(self.compact_frame, orient=tk.HORIZONTAL, mode="determinate", maximum=100, value=0, length=70)
        self.compact_progress_bar.pack(side="left", padx=(0, 3))
        self.compact_progress_percent_label = tk.Label(self.compact_frame, text="0%", anchor="w", font=("Arial", 7), width=4)
        self.compact_progress_percent_label.pack(side="left")
        
        # Main text and notice areas
        main_pane = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        self.main_pane = main_pane
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)

        text_container = tk.Frame(main_pane)
        notice_frame = tk.Frame(main_pane)
        self.text_container = text_container
        self.notice_frame = notice_frame
        main_pane.add(text_container, weight=5)
        main_pane.add(notice_frame, weight=1)

        text_pane = ttk.PanedWindow(text_container, orient=tk.HORIZONTAL)
        text_pane.pack(fill="both", expand=True)

        transcript_frame = tk.Frame(text_pane)
        text_pane.add(transcript_frame, weight=1)

        transcript_header = tk.Frame(transcript_frame)
        transcript_header.pack(fill="x")
        tk.Label(transcript_header, text="Transcribe", anchor="w", font=("Arial", 9, "bold")).pack(side="left")
        self.streaming_var = tk.BooleanVar(value=self.settings.get("streaming_transcription", True))
        tk.Checkbutton(transcript_header, text="Real-time", variable=self.streaming_var, font=("Arial", 9)).pack(side="right")
        self.text = scrolledtext.ScrolledText(transcript_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.text.pack(fill="both", expand=True)

        self.translation_var = tk.BooleanVar(value=False)

        tk.Label(notice_frame, text="System Notice", anchor="w", font=("Arial", 9, "bold")).pack(fill="x")
        self.notice_text = scrolledtext.ScrolledText(notice_frame, wrap=tk.WORD, font=("Consolas", 9), height=8)
        self.notice_text.pack(fill="both", expand=True)
        self.notice_text.tag_configure("recommended_source", foreground=RECOMMENDED_SOURCE_COLOR)
        self.apply_preferences()
        self.root.bind("<Configure>", self.on_window_configure)

    def log(self, message, tag=None):
        if tag:
            self.notice_text.insert(tk.END, message + "\n", tag)
        else:
            self.notice_text.insert(tk.END, message + "\n")
        self.notice_text.see(tk.END)

    def queue_log(self, message, tag=None):
        self.ui_queue.put(("log", message, tag))

    def log_transcript(self, message):
        self.text.insert(tk.END, message + "\n")
        self.text.see(tk.END)

    def queue_transcript(self, message):
        self.ui_queue.put(("transcript", message))

    def log_translation(self, message):
        return

    def queue_translation(self, message):
        self.ui_queue.put(("translation", message))

    def set_status(self, message):
        self.status.config(text=f"Status: {message}")
        self.root.update_idletasks()

    def set_recording_button_state(self, is_recording):
        if is_recording:
            self.start_button.config(
                text="Stop & STT",
                relief=tk.SUNKEN,
                bg="#c62828",
                fg="white",
                activebackground="#b71c1c",
                activeforeground="white"
            )
            self.compact_record_button.config(
                text="Stop",
                relief=tk.SUNKEN,
                bg="#c62828",
                fg="white",
                activebackground="#b71c1c",
                activeforeground="white",
            )
        else:
            self.start_button.config(
                text="Start Recording",
                relief=tk.RAISED,
                bg=self.root.cget("bg"),
                fg="black",
                activebackground=self.root.cget("bg"),
                activeforeground="black"
            )
            self.compact_record_button.config(
                text="Start",
                relief=tk.RAISED,
                bg=self.root.cget("bg"),
                fg="black",
                activebackground=self.root.cget("bg"),
                activeforeground="black",
            )

    def set_audio_file_button_state(self, is_processing):
        if is_processing:
            self.audio_file_button.config(
                text="Processing...",
                relief=tk.SUNKEN,
                state=tk.DISABLED,
                bg="#1565c0",
                fg="white",
                activebackground="#0d47a1",
                activeforeground="white"
            )
        else:
            self.audio_file_button.config(
                text="Audio File STT",
                relief=tk.RAISED,
                state=tk.NORMAL,
                bg=self.root.cget("bg"),
                fg="black",
                activebackground=self.root.cget("bg"),
                activeforeground="black"
            )

    def queue_status(self, message):
        self.ui_queue.put(("status", message))

    def queue_time(self, message):
        self.ui_queue.put(("time", message))

    def queue_recording_button(self, is_recording):
        self.ui_queue.put(("recording_button", is_recording))

    def queue_audio_level(self, source, level):
        self.ui_queue.put(("audio_level", source, level))

    def queue_clear_levels(self):
        self.ui_queue.put(("clear_levels",))

    def queue_messagebox_error(self, title, message):
        self.ui_queue.put(("error", title, message))

    def process_ui_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                action = item[0]

                if action == "log":
                    self.log(item[1], item[2] if len(item) > 2 else None)
                elif action == "transcript":
                    self.log_transcript(item[1])
                elif action == "translation":
                    pass
                elif action == "status":
                    self.set_status(item[1])
                elif action == "recording_button":
                    self.set_recording_button_state(item[1])
                elif action == "audio_file_button":
                    self.set_audio_file_button_state(item[1])
                elif action == "refresh_button":
                    self.set_refresh_button_state(item[1])
                elif action == "device_selection":
                    self.apply_device_selection(item[1], item[2], recommended=False)
                elif action == "recommended_device_selection":
                    self.apply_device_selection(item[1], item[2], recommended=True)
                elif action == "time":
                    self.time_label.config(text=item[1])
                    self.compact_time_label.config(text=item[1])
                elif action == "audio_level":
                    self.level_last_update[item[1]] = time.time()
                    if item[2] >= 2:
                        self.level_last_signal[item[1]] = time.time()
                    self.draw_audio_level(item[1], item[2])
                elif action == "clear_levels":
                    self.draw_audio_level("primary", 0)
                    self.draw_audio_level("secondary", 0)
                elif action == "error":
                    messagebox.showerror(item[1], item[2])
                elif action == "progress":
                    self.set_progress(item[1], item[2] if len(item) > 2 else None)
                elif action == "extension_prompt":
                    self.prompt_recording_extension()
                elif action == "auto_stop":
                    if self.recording:
                        self.stop_and_transcribe()
        except queue.Empty:
            pass

        if self.recording or self.source_testing:
            now = time.time()
            for source in ("primary", "secondary"):
                if now - self.level_last_update[source] > 0.7:
                    self.draw_audio_level(source, 0)
            self.check_silent_source_warnings(now)

        self.root.after(50, self.process_ui_queue)

    def set_refresh_button_state(self, is_testing):
        if is_testing:
            self.refresh_button.config(
                text="Testing sources...",
                relief=tk.SUNKEN,
                bg="#1565c0",
                fg="white",
                activebackground="#0d47a1",
                activeforeground="white"
            )
        else:
            self.refresh_button.config(
                text="Refresh / Recommend",
                relief=tk.RAISED,
                bg=self.root.cget("bg"),
                fg="black",
                activebackground=self.root.cget("bg"),
                activeforeground="black"
            )

    def apply_device_selection(self, primary_index, secondary_index, recommended=False):
        if primary_index is not None:
            self.device_combo.current(primary_index)
            self.selected_device = self.primary_device_list[primary_index]

        if secondary_index is not None:
            self.secondary_device_combo.current(secondary_index + 1)
            self.selected_secondary_device = self.secondary_device_list[secondary_index]
        else:
            self.secondary_device_combo.current(0)
            self.selected_secondary_device = None

        if recommended:
            self.mark_recommended_source_style(primary_index, secondary_index)
            self.save_user_settings()

    def mark_recommended_source_style(self, primary_index, secondary_index):
        self.recommended_primary_index = primary_index
        self.recommended_secondary_index = secondary_index

        self.device_combo.configure(style=self.recommended_combo_style)
        self.primary_recommend_label.config(text="Recommended", bg=RECOMMENDED_SOURCE_COLOR)
        if secondary_index is not None:
            self.secondary_device_combo.configure(style=self.recommended_combo_style)
            self.secondary_recommend_label.config(text="Recommended", bg=RECOMMENDED_SOURCE_COLOR)
        else:
            self.secondary_device_combo.configure(style=self.default_combo_style)
            self.secondary_recommend_label.config(text="", bg=self.root.cget("bg"))

    def clear_recommended_source_style(self, source):
        if source == "primary" and self.device_combo.current() != self.recommended_primary_index:
            self.device_combo.configure(style=self.default_combo_style)
            self.primary_recommend_label.config(text="", bg=self.root.cget("bg"))
        elif source == "secondary":
            current_secondary_index = self.secondary_device_combo.current() - 1
            if current_secondary_index != self.recommended_secondary_index:
                self.secondary_device_combo.configure(style=self.default_combo_style)
                self.secondary_recommend_label.config(text="", bg=self.root.cget("bg"))

    def on_source_selection_changed(self, source):
        self.clear_recommended_source_style(source)
        self.save_user_settings()

    def on_source_enabled_changed(self):
        self.primary_source_enabled = self.primary_source_var.get()
        self.secondary_source_enabled = self.secondary_source_var.get()
        self.save_user_settings()

    def on_model_selection_changed(self, event=None):
        selected = self.model_var.get()
        if selected != self.selected_model_name:
            self.selected_model_name = selected
            self.model = None
            self.realtime_model = None
            self.save_user_settings()
            self.check_model_files()
            self.log(f"Model changed to: {selected}\n")
            self.warn_if_language_model_mismatch()

    def on_language_selection_changed(self, event=None):
        selected = self.stt_language_var.get()
        if selected != self.stt_language:
            self.stt_language = selected
            self.save_user_settings()
            self.log(f"STT language changed to: {selected}\n")
            self.warn_if_language_model_mismatch()

    def warn_if_language_model_mismatch(self):
        if self.stt_language == "Korean" and self.selected_model_name.endswith(".en"):
            self.log(
                "Korean/English STT needs a multilingual model such as "
                "faster-whisper-tiny or faster-whisper-small. "
                "The selected .en model is English-only.\n"
            )

    def update_recording_time(self):
        """Update elapsed recording time."""
        while self.recording:
            try:
                elapsed = (datetime.datetime.now() - self.recording_start_time).total_seconds()
                remaining = max(0, int(self.recording_limit_seconds - elapsed))
                minutes, seconds = divmod(int(elapsed), 60)
                rem_minutes, rem_seconds = divmod(remaining, 60)
                self.queue_time(f"Time: {minutes:02d}:{seconds:02d} | Left: {rem_minutes:02d}:{rem_seconds:02d}")
                if elapsed >= self.recording_warning_seconds and not self.recording_warning_shown:
                    self.recording_warning_shown = True
                    self.recording_extension_available = True
                    self.ui_queue.put(("extension_prompt",))
                if elapsed >= self.recording_limit_seconds:
                    self.ui_queue.put(("auto_stop",))
                    break
                time.sleep(0.1)
            except:
                pass

    def update_audio_level(self, source, audio_data):
        """Update audio level visualization."""
        try:
            # Calculate RMS (Root Mean Square) for audio level
            rms = np.sqrt(np.mean(audio_data ** 2))
            # Normalize to 0-100 for display
            level = min(100, int(rms * 500))  # 500 is an arbitrary scaling factor
            self.queue_audio_level(source, level)
        except:
            pass

    def draw_audio_level(self, source, level):
        """Draw audio level visualization on the Tkinter thread."""
        canvases = (
            [self.primary_level_canvas, self.status_primary_level_canvas]
            if source == "primary"
            else [self.secondary_level_canvas, self.status_secondary_level_canvas]
        )

        for canvas in canvases:
            self.draw_single_audio_level(canvas, source, level)

    def draw_single_audio_level(self, canvas, source, level):
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)

        canvas.delete("all")
        if level > 0:
            fill_width = int(width * (level / 100))
            color = "green" if source == "primary" else "steelblue"
            canvas.create_rectangle(0, 0, fill_width, height, fill=color, outline=color)
        canvas.create_text(width // 2, height // 2, text=f"{level}%", font=("Arial", 7))

    def clear_text(self):
        self.text.delete("1.0", tk.END)

    def open_preferences(self):
        self.preferences_window.deiconify()
        self.preferences_window.lift()
        self.preferences_window.focus_force()

    def open_help(self):
        help_window = tk.Toplevel(self.root)
        help_window.title("LocalSTT Light Help")
        help_window.geometry("680x560")

        help_text = scrolledtext.ScrolledText(help_window, wrap=tk.WORD, font=("Consolas", 10))
        help_text.pack(fill="both", expand=True, padx=10, pady=10)
        help_text.insert(tk.END, self.get_help_text())
        help_text.configure(state=tk.DISABLED)

        tk.Button(help_window, text="Close", command=help_window.destroy, width=12).pack(pady=(0, 10))
        help_window.transient(self.root)
        help_window.lift()
        help_window.focus_force()

    def get_help_text(self):
        return """LocalSTT Light - Quick Help

Purpose
LocalSTT Light records English or Korean/English mixed audio and creates an SRT transcript file.
It does not include Korean translation.

Basic Workflow
1. Click Refresh / Recommend in Preferences to detect audio sources.
2. Select a system/web audio source as Primary Source if needed.
3. Select a microphone as Secondary if needed.
4. Keep Src1 and/or Src2 checked on the main window.
5. Click Start Recording.
6. Click Stop & STT when finished.
7. Wait until the Process bar reaches 100%.

Audio Sources
Src1 usually means system, web, meeting, or loopback audio.
Src2 usually means microphone audio.
You can turn either source off with the Src1 and Src2 checkboxes.
At least one source must be enabled before recording.

Real-time
The Real-time checkbox is enabled by default.
Real-time text is shown while recording, but the final SRT is generated again
after recording stops for better quality.

Audio File STT
Click Audio File STT to transcribe an existing audio file.
The output is saved as an SRT file only.

Models
Open Preferences to select a model from the models folder.
The default model is faster-whisper-tiny.en.
For Korean/English STT, select a multilingual model folder such as faster-whisper-tiny
or faster-whisper-small. If you add another model folder, restart or reopen the
app so it can be detected.

Recording Limit
Recording is limited to 1 hour by default.
About 10 minutes before the limit, the app asks whether to add 15 minutes.
You can also use the +15 min button when extension is available.

Meeting Mode
Preferences includes meeting-friendly options:
- Always on top keeps the app above other windows.
- Compact auto opacity changes transparency automatically in compact mode.
- Silent source warning alerts you if an enabled source appears silent.
- Apply Meeting Mode turns on the recommended meeting settings at once.

Compact Mode
If the window height is reduced below 60% of the monitor height, the app switches
to compact mode. In compact mode, only the transcript area and a small control bar
remain visible. Increasing the window height restores the full UI.

Output Files
Files are saved in the output folder beside the app or EXE.
Recorded audio and SRT use the same base filename, for example:
recording_20260530_153000.mp3
recording_20260530_153000.srt
Use Open Output Folder in Preferences to open the save location.

Tips
If system audio is not captured, try Refresh / Recommend again while audio is playing.
For web or meeting audio capture, Windows loopback, Stereo Mix, or VB-Cable may be needed.
If the level meter stays at 0%, check Windows input permissions and selected devices.
"""

    def hide_preferences(self):
        self.preferences_window.withdraw()

    def choose_font_color(self):
        color = colorchooser.askcolor(color=self.font_color_var.get(), parent=self.preferences_window)[1]
        if color:
            self.font_color_var.set(color)
            self.apply_preferences()

    def apply_meeting_mode(self):
        self.always_on_top_var.set(True)
        self.compact_auto_opacity_var.set(True)
        self.compact_alpha_var.set(0.75)
        self.silent_source_warning_var.set(True)
        self.streaming_var.set(True)
        self.apply_preferences()
        self.log("Meeting Mode applied: always on top, compact auto opacity, silent source warning, real-time ON.\n")

    def open_output_folder(self):
        try:
            os.makedirs(APP_DIR, exist_ok=True)
            os.startfile(APP_DIR)
        except Exception as e:
            messagebox.showerror("Open Output Folder", str(e), parent=self.preferences_window)

    def apply_preferences(self):
        self.window_alpha = self.window_alpha_var.get()
        self.always_on_top = self.always_on_top_var.get()
        self.compact_auto_opacity = self.compact_auto_opacity_var.get()
        self.compact_alpha = self.compact_alpha_var.get()
        self.silent_source_warning = self.silent_source_warning_var.get()
        self.text_font_size = self.font_size_var.get()
        self.text_fg = self.font_color_var.get()
        self.stt_language = self.stt_language_var.get()

        try:
            alpha = self.compact_alpha if self.compact_mode and self.compact_auto_opacity else self.window_alpha
            self.root.attributes("-alpha", alpha)
            self.root.attributes("-topmost", self.always_on_top)
        except tk.TclError:
            pass

        transcript_font = (self.text_font_family, self.text_font_size)
        notice_font = (self.text_font_family, max(8, self.text_font_size - 1))
        self.text.configure(font=transcript_font, fg=self.text_fg)
        self.notice_text.configure(font=notice_font)
        self.save_user_settings()

    def check_silent_source_warnings(self, now):
        if not self.silent_source_warning or now - self.last_silent_check < 1.0:
            return

        self.last_silent_check = now
        if not self.recording or not self.recording_start_time:
            return

        elapsed = (datetime.datetime.now() - self.recording_start_time).total_seconds()
        if elapsed < self.silent_warning_seconds:
            return

        sources = []
        if self.primary_source_enabled:
            sources.append(("primary", "Src1"))
        if self.secondary_source_enabled and self.selected_secondary_device is not None:
            sources.append(("secondary", "Src2"))

        for source, label in sources:
            if source in self.silent_warning_shown_sources:
                continue
            last_signal = self.level_last_signal.get(source)
            if last_signal is None or now - last_signal >= self.silent_warning_seconds:
                self.silent_warning_shown_sources.add(source)
                self.log(f"Warning: {label} appears silent. Check source selection, routing, and Windows input permissions.\n")
                self.set_status(f"{label} silent")

    def set_progress(self, value, message=None):
        progress = max(0, min(100, int(value)))
        self.progress_bar["value"] = progress
        self.compact_progress_bar["value"] = progress
        self.progress_percent_label.config(text=f"{progress}%")
        self.compact_progress_percent_label.config(text=f"{progress}%")
        if message:
            self.progress_label.config(text=f"Process: {message}")
            self.compact_progress_label.config(text=message[:10])

    def queue_progress(self, value, message=None):
        self.ui_queue.put(("progress", value, message))

    def prompt_recording_extension(self):
        self.time_label.config(fg="#c62828")
        self.compact_time_label.config(fg="#c62828")
        self.extend_button.config(state=tk.NORMAL)
        self.compact_extend_button.config(state=tk.NORMAL)
        answer = messagebox.askyesno(
            "Recording time limit",
            "Recording will reach the 1 hour limit in about 10 minutes.\nAdd 15 more minutes?",
            parent=self.root,
        )
        if answer:
            self.extend_recording_limit()

    def extend_recording_limit(self):
        if not self.recording and not self.recording_extension_available:
            return
        self.recording_limit_seconds += self.recording_extension_seconds
        self.recording_warning_seconds += self.recording_extension_seconds
        self.recording_extension_available = False
        self.extend_button.config(state=tk.DISABLED)
        self.compact_extend_button.config(state=tk.DISABLED)
        self.time_label.config(fg="black")
        self.compact_time_label.config(fg="black")
        self.log("Recording limit extended by 15 minutes.\n")

    def on_window_configure(self, event):
        if event.widget is not self.root:
            return

        compact_height = self.root.winfo_screenheight() * 0.6
        should_compact = event.height <= compact_height
        if should_compact != self.compact_mode:
            self.set_compact_mode(should_compact)

    def set_compact_mode(self, enabled):
        self.compact_mode = enabled
        if enabled:
            self.top_frame.pack_forget()
            self.status_frame.pack_forget()
            self.main_pane.pack_configure(padx=6, pady=(2, 6))
            self.compact_frame.pack(fill="x", padx=6, pady=0, before=self.main_pane)
            if str(self.notice_frame) in self.main_pane.panes():
                self.main_pane.forget(self.notice_frame)
        else:
            self.compact_frame.pack_forget()
            self.main_pane.pack_configure(padx=10, pady=10)
            if not self.top_frame.winfo_manager():
                self.top_frame.pack(fill="x", padx=10, pady=10, before=self.main_pane)
            if not self.status_frame.winfo_manager():
                self.status_frame.pack(fill="x", padx=10, pady=5, before=self.main_pane)
            if str(self.notice_frame) not in self.main_pane.panes():
                self.main_pane.add(self.notice_frame, weight=1)
        self.apply_preferences()

