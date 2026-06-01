from .config import REALTIME_MAX_LINE_CHARS


PARAGRAPH_ENDINGS = (".", "?", "!", "。", "？", "！", ".”", "?”", "!”")
TRANSLATION_MAX_PARAGRAPH_CHARS = 320
SRT_MIN_PARAGRAPH_SECONDS = 10
SRT_MAX_PARAGRAPH_SECONDS = 15


class TranslationMixin:
    def format_time_srt(self, seconds):
        """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def format_time_display(self, seconds):
        """Convert seconds to a readable elapsed time format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def build_realtime_lines(self, segments, chunk_start_seconds):
        lines = []
        current_text = ""
        current_start = None
        current_end = None

        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue

            start_time = chunk_start_seconds + segment.start
            end_time = chunk_start_seconds + segment.end
            candidate = f"{current_text} {text}".strip()

            if current_text and len(candidate) > REALTIME_MAX_LINE_CHARS:
                lines.append((current_start, current_end, current_text))
                current_text = text
                current_start = start_time
            else:
                current_text = candidate
                if current_start is None:
                    current_start = start_time

            current_end = end_time

        if current_text:
            lines.append((current_start, current_end, current_text))

        return lines

    def translate_to_korean(self, text):
        return ""

    def append_translation_text(self, buffer, start_time, end_time, text):
        stripped = text.strip()
        if not stripped:
            return

        if not buffer:
            buffer.append({
                "start": start_time,
                "end": end_time,
                "texts": [stripped],
            })
            return

        buffer[0]["end"] = end_time
        buffer[0]["texts"].append(stripped)

    def pop_completed_translation_paragraphs(self, buffer, force=False, min_duration=None, max_duration=None):
        if not buffer:
            return []

        current = buffer[0]
        paragraph = " ".join(current["texts"]).strip()
        if not paragraph:
            buffer.clear()
            return []

        duration = current["end"] - current["start"]
        reached_min_duration = min_duration is None or duration >= min_duration
        reached_max_duration = max_duration is not None and duration >= max_duration
        complete = (
            force
            or len(paragraph) >= TRANSLATION_MAX_PARAGRAPH_CHARS
            or reached_max_duration
            or (paragraph.endswith(PARAGRAPH_ENDINGS) and reached_min_duration)
        )

        if not complete:
            return []

        buffer.clear()
        return [(current["start"], current["end"], paragraph)]

    def translate_paragraph(self, start_time, end_time, text, srt_time=False):
        return None

    def format_paragraph_time_range(self, start_time, end_time, srt_time=False):
        if srt_time:
            start_label = self.format_time_srt(start_time)
            end_label = self.format_time_srt(end_time)
        else:
            start_label = self.format_time_display(start_time)
            end_label = self.format_time_display(end_time)

        return f"[{start_label} --> {end_label}]"

    def format_transcript_paragraph(self, start_time, end_time, text, srt_time=False):
        return f"{self.format_paragraph_time_range(start_time, end_time, srt_time)} {text}"

    def show_translation_notice(self, message):
        return

    def queue_transcript_with_translation(self, start_time, end_time, text, srt_time=False):
        if srt_time:
            start_label = self.format_time_srt(start_time)
            end_label = self.format_time_srt(end_time)
        else:
            start_label = self.format_time_display(start_time)
            end_label = self.format_time_display(end_time)

        self.queue_transcript(f"[{start_label} - {end_label}] {text}")

