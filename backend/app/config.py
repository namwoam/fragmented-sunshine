import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    cors_origins: tuple[str, ...]
    gemini_api_key: str | None
    gemini_model: str
    asr_model: str


def get_settings() -> Settings:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    data_dir = Path(os.getenv("FRAGMENTED_SUNSHINE_DATA_DIR", "data")).resolve()
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    return Settings(
        data_dir=data_dir,
        database_path=data_dir / "fragmented_sunshine.db",
        cors_origins=tuple(origin.strip() for origin in origins if origin.strip()),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        asr_model=os.getenv("ASR_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")),
    )
