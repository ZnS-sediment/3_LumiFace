"""Local, private runtime configuration. No implicit model downloads in API calls."""
import os
from pathlib import Path

# Inference is local; disable an optional dependency's import-time version request.
os.environ.setdefault('NO_ALBUMENTATIONS_UPDATE', '1')

ROOT = Path(__file__).resolve().parents[3]
DATA = Path(os.environ.get('LUMIFACE_DATA', str(ROOT / 'runtime'))).resolve()
MODEL_ROOT = Path(os.environ.get('LUMIFACE_MODELS', str(ROOT / 'runtime' / 'insightface'))).resolve()
MODEL_NAME = 'buffalo_l'
MAX_UPLOAD = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_ARCHIVE = 100 * 1024 * 1024
MAX_DATASET_IMAGES = 500
DEFAULT_THRESHOLD = 0.45  # Demonstration default, not an empirically calibrated threshold.
ALGORITHM_VERSION = 'lumiface-1.0'


def prepare_storage() -> None:
    os.environ.setdefault('MPLCONFIGDIR', str(DATA / 'cache' / 'matplotlib'))
    for folder in (DATA, DATA / 'samples', DATA / 'datasets', DATA / 'cache', MODEL_ROOT):
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.chmod(0o700)
