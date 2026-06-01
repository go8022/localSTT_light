import os
import sys
from pathlib import Path


def get_app_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[1]


def get_bundle_dir():
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir)

    return Path(__file__).resolve().parents[1]


PROJECT_DIR = Path(__file__).resolve().parents[1]
APP_BASE_DIR = get_app_base_dir()
BUNDLE_DIR = get_bundle_dir()
MODEL_NAMES = [
    "faster-whisper-tiny.en",
]
DEFAULT_MODEL_NAMES = MODEL_NAMES
DEFAULT_MODEL_NAME = MODEL_NAMES[0]
MODEL_REQUIRED_FILES = [
    "model.bin",
    "config.json",
    "tokenizer.json",
    "vocabulary.txt",
]


def get_model_search_dirs():
    return [
        APP_BASE_DIR / "models",
        BUNDLE_DIR / "models",
        PROJECT_DIR / "models",
        Path(r"C:\Tools\models"),
    ]


def resolve_model_path(model_names=None):
    model_names = model_names or DEFAULT_MODEL_NAMES
    candidates = [os.environ.get("LOCALSTT_MODEL_PATH")]
    for model_name in model_names:
        candidates.extend([
            APP_BASE_DIR / "models" / model_name,
            APP_BASE_DIR / model_name,
            BUNDLE_DIR / "models" / model_name,
            PROJECT_DIR / "models" / model_name,
            Path(r"C:\Tools\models") / model_name,
        ])

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))

    return str(APP_BASE_DIR / "models" / model_names[0])


def list_available_model_names():
    names = []
    seen = set()

    for model_dir in get_model_search_dirs():
        if not model_dir.exists() or not model_dir.is_dir():
            continue
        for child in model_dir.iterdir():
            if not child.is_dir() or child.name in seen:
                continue
            if all((child / filename).exists() for filename in MODEL_REQUIRED_FILES):
                seen.add(child.name)
                names.append(child.name)

    if DEFAULT_MODEL_NAME not in seen:
        names.insert(0, DEFAULT_MODEL_NAME)

    return names


def resolve_output_dir():
    env_dir = os.environ.get("LOCALSTT_OUTPUT_DIR")
    if env_dir:
        return str(Path(env_dir))

    return str(APP_BASE_DIR / "output")


MODEL_PATH = resolve_model_path(MODEL_NAMES)
APP_DIR = resolve_output_dir()
SETTINGS_PATH = APP_BASE_DIR / "localstt_settings.json"

SAMPLE_RATE = 16000
CHANNELS = 1
REALTIME_CHUNK_DURATION = 4
REALTIME_SAMPLE_RATE = 16000
REALTIME_MAX_LINE_CHARS = 150
REALTIME_PROMPT_CHARS = 220

os.makedirs(APP_DIR, exist_ok=True)
