"""Pengaturan engine: env var > ~/.clipper.toml > default. Murni, tanpa impor berat."""
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    ai_provider: str = "keyword"
    gemini_api_key: str | None = None
    ollama_host: str | None = None
    subtitle_style: str = "lato"
    reframe: bool = True


def load_settings(env=os.environ, path="~/.clipper.toml") -> Settings:
    data: dict = {}
    p = Path(str(path)).expanduser()
    if p.is_file():
        try:
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            data = {}
    s = Settings()
    for f in ("ai_provider", "gemini_api_key", "ollama_host", "subtitle_style", "reframe"):
        if f in data:
            setattr(s, f, data[f])
    key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    if key:
        s.gemini_api_key = key
    if env.get("CLIPPER_AI"):
        s.ai_provider = env["CLIPPER_AI"]
    if env.get("OLLAMA_HOST"):
        s.ollama_host = env["OLLAMA_HOST"]
    if env.get("CLIPPER_SUBTITLE_STYLE"):
        s.subtitle_style = env["CLIPPER_SUBTITLE_STYLE"]
    if env.get("CLIPPER_REFRAME"):
        s.reframe = env["CLIPPER_REFRAME"].lower() not in ("0", "false", "no", "off")
    return s
