from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
EXPORT_DIR = Path(os.getenv("EXPORT_DIR", BASE_DIR / "exports"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "outputs"))
LOG_DIR = Path(os.getenv("LOG_DIR", BASE_DIR / "logs"))

STATIC_UI_PATH = Path(os.getenv("STATIC_UI_PATH", BASE_DIR / "static_ui.html"))
TRANSLATIONS_PATH = Path(os.getenv("TRANSLATIONS_PATH", BASE_DIR / "translations.json"))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "app.db"))

for d in [DATA_DIR, UPLOAD_DIR, EXPORT_DIR, OUTPUT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)
