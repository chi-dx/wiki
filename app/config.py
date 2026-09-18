from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    wiki_mode: str = "demo"
    external_mode: str = "demo"
    model_mode: str = "extractive"
    external_default: bool = True
    sync_interval: int = 300
    request_timeout: float = 25
    upstream_timeout: float = 8
    max_concurrent_asks: int = 4
    wiki_url: str = ""
    wiki_api_key: str = ""
    external_url: str = ""
    external_api_key: str = ""
    model_url: str = ""
    model_api_key: str = ""
    model_name: str = ""
    compile_mode: str = "extractive"
    compile_timeout: float = 90
    knowledge_backend: str = "local"
    compiler_url: str = "http://127.0.0.1:8010"
    compiler_query_timeout: float = 180
    compiler_sync_timeout: float = 900

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        settings = cls(
            data_dir=Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve(),
            wiki_mode=os.getenv("WIKI_MODE", "demo"),
            external_mode=os.getenv("EXTERNAL_MODE", "demo"),
            model_mode=os.getenv("MODEL_MODE", "extractive"),
            compile_mode=os.getenv("COMPILE_MODE", "extractive"),
            knowledge_backend=os.getenv("KNOWLEDGE_BACKEND", "local"),
            compiler_url=os.getenv("COMPILER_URL", "http://127.0.0.1:8010").rstrip('/'),
            compiler_query_timeout=max(1, float(os.getenv("COMPILER_QUERY_TIMEOUT_SECONDS", "180"))),
            compiler_sync_timeout=max(1, float(os.getenv("COMPILER_SYNC_TIMEOUT_SECONDS", "900"))),
            compile_timeout=max(1, float(os.getenv("COMPILE_TIMEOUT_SECONDS", "90"))),
            external_default=os.getenv("EXTERNAL_DEFAULT", "true").lower() == "true",
            sync_interval=max(10, int(os.getenv("SYNC_INTERVAL_SECONDS", "300"))),
            request_timeout=max(1, float(os.getenv("REQUEST_TIMEOUT_SECONDS", "25"))),
            upstream_timeout=max(1, float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "8"))),
            max_concurrent_asks=max(1, int(os.getenv("MAX_CONCURRENT_ASKS", "4"))),
            **{key: os.getenv(key.upper(), "") for key in (
                "wiki_url", "wiki_api_key", "external_url", "external_api_key",
                "model_url", "model_name")},
            model_api_key=os.getenv("MODEL_API_KEY") or os.getenv("DEEPSEEK_API_KEY", ""),
        )
        for field, allowed in (("wiki_mode", {"demo", "http"}),
                               ("external_mode", {"demo", "http", "off"}),
                               ("model_mode", {"extractive", "openai"}),
                               ("compile_mode", {"extractive", "llm"}),
                               ("knowledge_backend", {"local", "compiler"})):
            if getattr(settings, field) not in allowed:
                raise ValueError(f"Invalid {field}")
        for mode, url in ((settings.wiki_mode, settings.wiki_url),
                          (settings.external_mode, settings.external_url)):
            if mode == "http" and not url.startswith(("https://", "http://")):
                raise ValueError("HTTP provider requires a valid URL")
        if (settings.model_mode == "openai" or settings.compile_mode == "llm") and (
            not settings.model_url.startswith(("https://", "http://")) or not settings.model_name
        ):
            raise ValueError("MODEL_URL and MODEL_NAME are required")
        return settings
