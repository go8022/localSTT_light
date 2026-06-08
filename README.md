# LocalSTT Light

This workspace is a light build based on the existing LocalSTT app.

## Scope

- Translation removed.
- English STT with `faster-whisper-tiny.en`.
- Korean STT when a multilingual model such as `faster-whisper-tiny` or `faster-whisper-small` is selected.
- Keeps the existing two-source recording flow:
  - Primary source for web/system sound.
  - Secondary source for microphone.
- Keeps Refresh / Recommend and source level meters.

## Output

Output files are saved under:

```text
output
```

Transcript files are saved as SRT-style text:

```text
00:00:00,000 --> 00:00:03,200
Recognized transcript text.
```

## Model Path

The app searches for model folders such as `faster-whisper-tiny.en`,
`faster-whisper-tiny`, and `faster-whisper-small` in:

```text
LOCALSTT_MODEL_PATH
.\models\faster-whisper-tiny.en
.\faster-whisper-tiny.en
C:\Tools\models\faster-whisper-tiny.en
```

For Korean STT, add a multilingual model folder such as:

```text
.\models\faster-whisper-tiny
.\models\faster-whisper-small
C:\Tools\models\faster-whisper-small
```

## Run

```powershell
cd C:\tools\LocalSTT\LocalSTT_light
..\venv\Scripts\python.exe main.py
```

## Build

```powershell
cd C:\tools\LocalSTT\LocalSTT_light
.\build_exe.ps1
```
