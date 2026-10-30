import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent

LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "low").strip()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "90"))
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "3"))

MAX_RESUMES = int(os.getenv("MAX_RESUMES", "20"))
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_MB", "10")) * 1024 * 1024

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8400").split(",") if o.strip()]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
LOG_DIR = BACKEND_DIR / os.getenv("LOG_DIR", "logs").strip()
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "30"))


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    base_url: str
    api_key: str
    models: tuple[str, ...]
    fallback_model: str
    reasoning_effort: str
    timeout: int
    concurrency: int
    # context window the server runs with, 0 = unknown; used to warn about cut-off prompts
    context_length: int = 0
    # ask for a JSON object response so the model cannot return malformed JSON
    json_mode: bool = False


def _host_url(host: str) -> str:
    if not host:
        return ""
    if "://" not in host:
        host = f"http://{host}"
    url = host.rstrip("/").replace("://0.0.0.0", "://127.0.0.1")
    return url if url.endswith("/v1") else f"{url}/v1"


def _load_providers() -> tuple[dict[str, Provider], list[str]]:
    names = [n.strip().upper() for n in os.getenv("LLM_PROVIDERS", "").split(",") if n.strip()]
    if not names:
        names = ["LLM"]
    providers, skipped = {}, []
    for name in names:
        def get(key: str, default: str = "") -> str:
            return os.getenv(f"{name}_{key}", default).strip()

        base_url, api_key = get("BASE_URL") or _host_url(get("HOST")), get("API_KEY")
        if not base_url or "xxxx" in api_key:
            skipped.append(name)
            continue
        provider_id = "default" if name == "LLM" else name.lower()
        model = get("MODEL")
        providers[provider_id] = Provider(
            id=provider_id,
            label=get("LABEL", "AI model" if name == "LLM" else name.title()),
            base_url=base_url,
            api_key=api_key,
            models=tuple(m.strip() for m in get("MODELS", model).split(",") if m.strip()),
            fallback_model=get("FALLBACK_MODEL"),
            reasoning_effort=get("REASONING_EFFORT", LLM_REASONING_EFFORT),
            timeout=int(get("TIMEOUT", str(LLM_TIMEOUT))),
            concurrency=int(get("CONCURRENCY", str(LLM_CONCURRENCY))),
            context_length=int(get("CONTEXT_LENGTH", "0")),
            json_mode=get("JSON_MODE", "false").lower() in ("1", "true", "yes"),
        )
    return providers, skipped


PROVIDERS, SKIPPED_PROVIDERS = _load_providers()
DEFAULT_PROVIDER = os.getenv("LLM_DEFAULT_PROVIDER", "").strip().lower() or next(iter(PROVIDERS), "")
DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL", "").strip()


def llm_configured() -> bool:
    return bool(PROVIDERS)
