import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# Generated files (article cache, page snapshots, reports). The daily job points this at local disk.
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output"))


def load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    db_path: Path
    max_articles: int
    openrouter_api_key: str
    openrouter_model: str

    @classmethod
    def from_env(cls):
        load_env()
        def path(key, default):
            value = Path(os.getenv(key, default))
            return value if value.is_absolute() else ROOT / value
        settings = cls(os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8000")),
                       path("DATA_DIR", "dataset/chin"), path("DB_PATH", "output/judgments.sqlite3"),
                       int(os.getenv("MAX_ARTICLES", "20")),
                       os.getenv("OPENROUTER_API_KEY", ""), os.getenv("OPENROUTER_MODEL", ""))
        if settings.max_articles < 0 or not 0 < settings.port < 65536:
            raise ValueError("Invalid MAX_ARTICLES or PORT")
        return settings
