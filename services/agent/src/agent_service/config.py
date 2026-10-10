from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .profiles.zh.terminal_strips import (
    DEFAULT_TERMINAL_STRIP_MAPPING,
    validate_terminal_strip_mapping,
)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Expected an integer, got {value!r}.") from exc


def _as_float(value: str | None, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Expected a number, got {value!r}.") from exc


def _as_optional_bool(value: str | None) -> bool | None:
    if value is None or not value.strip():
        return None
    return _as_bool(value, False)


def _first_env(*names: str) -> str | None:
    return next((value for name in names if (value := os.getenv(name))), None)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def load_agent_env() -> None:
    """Load only the Agent service .env without overriding process environment."""
    root = repository_root()
    values: dict[str, str] = {}
    for path in (root / "services" / "agent" / ".env",):
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or not key.replace("_", "").isalnum():
                continue
            values[key] = _clean_env_value(value)
    for key, value in values.items():
        os.environ.setdefault(key, value)


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    else:
        value = value.split(" #", 1)[0].rstrip()
    return value


@dataclass(frozen=True, slots=True)
class AgentSettings:
    host: str = "0.0.0.0"
    port: int = 8100
    environment: str = "development"
    log_level: str = "INFO"
    server_base_url: str = "http://127.0.0.1:8000"
    internal_token: str | None = None
    profile_root: Path = repository_root() / "services" / "agent" / "profiles"
    persistence_backend: str = "memory"
    checkpoint_backend: str = "memory"
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "project-assets"
    supabase_request_timeout_seconds: float = 60.0
    model_base_url: str | None = None
    model_chat_completions_url: str | None = None
    model_api_key: str | None = None
    default_model: str | None = None
    model_timeout_seconds: float = 300.0
    model_max_retries: int = 2
    model_retry_initial_backoff_seconds: float = 2.0
    model_retry_max_backoff_seconds: float = 30.0
    model_max_tokens: int | None = None
    model_fewshot_max_image_side: int = 1800
    model_enable_thinking: bool | None = None
    model_json_mode: bool = False
    extraction_max_pdf_pages: int = 0
    extraction_render_dpi: int = 300
    extraction_concurrency: int = 1
    extraction_reference_target_limit: int = 4
    extraction_keep_temp_images: bool = False
    extraction_output_mode: str = "library"
    terminal_strip_mapping: dict[str, str] | None = None
    import_template_path: Path | None = None
    profile_detection_dpi: int = 180
    profile_auto_select_threshold: float = 0.85
    profile_max_pdf_bytes: int = 200 * 1024 * 1024
    enable_improvement: bool = False
    inline_worker: bool = False
    workspace_root: Path = repository_root()

    @property
    def model_configured(self) -> bool:
        return bool((self.model_chat_completions_url or self.model_base_url) and self.default_model)

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @classmethod
    def from_env(cls) -> AgentSettings:
        load_agent_env()
        root = repository_root()
        profile_value = os.getenv("AGENT_PROFILE_ROOT")
        profile_root = Path(profile_value) if profile_value else root / "services" / "agent" / "profiles"
        if not profile_root.is_absolute():
            profile_root = root / profile_root
        base_url = _first_env("AGENT_MODEL_BASE_URL", "VLM_BASE_URL", "OPENAI_BASE_URL")
        model_api_key = _first_env("AGENT_MODEL_API_KEY", "VLM_API_KEY", "OPENAI_API_KEY")
        output_mode = (
            (os.getenv("AGENT_EXTRACTION_OUTPUT_MODE") or os.getenv("VLM_OUTPUT_MODE") or "library")
            .strip()
            .lower()
        )
        if output_mode not in {"library", "single_xlsx"}:
            raise ValueError("Extraction output mode must be 'library' or 'single_xlsx'.")
        template_value = _first_env("AGENT_IMPORT_XLS_TEMPLATE_PATH", "VLM_IMPORT_XLS_TEMPLATE_PATH")
        template_path = Path(template_value) if template_value else None
        if template_path is not None and not template_path.is_absolute():
            template_path = root / template_path
        legacy_supabase_enabled = _as_bool(os.getenv("SUPABASE_ENABLED"), False)
        persistence_backend = os.getenv(
            "AGENT_PERSISTENCE_BACKEND",
            "supabase" if legacy_supabase_enabled else "memory",
        ).strip().lower()
        if persistence_backend not in {"memory", "supabase"}:
            raise ValueError("Persistence backend must be 'memory' or 'supabase'.")
        checkpoint_backend = os.getenv("AGENT_CHECKPOINT_BACKEND", persistence_backend).strip().lower()
        if checkpoint_backend not in {"memory", "supabase"}:
            raise ValueError("Checkpoint backend must be 'memory' or 'supabase'.")
        return cls(
            host=os.getenv("AGENT_HOST", "0.0.0.0"),
            port=max(1, _as_int(os.getenv("AGENT_PORT"), 8100)),
            environment=os.getenv("AGENT_ENV", "development"),
            log_level=os.getenv("AGENT_LOG_LEVEL", "INFO").upper(),
            server_base_url=os.getenv("AGENT_SERVER_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            internal_token=os.getenv("AGENT_INTERNAL_TOKEN") or None,
            profile_root=profile_root.resolve(),
            persistence_backend=persistence_backend,
            checkpoint_backend=checkpoint_backend,
            supabase_url=(_first_env("AGENT_SUPABASE_URL", "SUPABASE_URL") or "").rstrip("/")
            or None,
            supabase_service_role_key=_first_env(
                "AGENT_SUPABASE_SERVICE_ROLE_KEY",
                "SUPABASE_SERVICE_ROLE_KEY",
            ),
            supabase_storage_bucket=os.getenv("AGENT_SUPABASE_STORAGE_BUCKET", "project-assets").strip(),
            supabase_request_timeout_seconds=max(
                1.0,
                _as_float(os.getenv("AGENT_SUPABASE_REQUEST_TIMEOUT_SECONDS"), 60.0),
            ),
            model_base_url=(base_url or ("https://api.openai.com/v1" if model_api_key else "")).rstrip("/")
            or None,
            model_chat_completions_url=_first_env(
                "AGENT_MODEL_CHAT_COMPLETIONS_URL",
                "VLM_CHAT_COMPLETIONS_URL",
                "OPENAI_CHAT_COMPLETIONS_URL",
            ),
            model_api_key=model_api_key,
            default_model=_first_env("AGENT_DEFAULT_MODEL", "VLM_MODEL", "OPENAI_MODEL"),
            model_timeout_seconds=max(
                1.0,
                _as_float(os.getenv("AGENT_MODEL_TIMEOUT_SECONDS", os.getenv("VLM_TIMEOUT_SECONDS")), 300.0),
            ),
            model_max_retries=max(
                0,
                _as_int(os.getenv("AGENT_MODEL_MAX_RETRIES", os.getenv("VLM_RETRY_COUNT")), 2),
            ),
            model_retry_initial_backoff_seconds=max(
                0.0,
                _as_float(
                    os.getenv(
                        "AGENT_MODEL_RETRY_INITIAL_BACKOFF_SECONDS",
                        os.getenv("VLM_RETRY_BACKOFF_SECONDS"),
                    ),
                    2.0,
                ),
            ),
            model_retry_max_backoff_seconds=max(
                0.0,
                _as_float(
                    os.getenv(
                        "AGENT_MODEL_RETRY_MAX_BACKOFF_SECONDS",
                        os.getenv("VLM_RETRY_MAX_BACKOFF_SECONDS"),
                    ),
                    30.0,
                ),
            ),
            model_max_tokens=(
                max(1, _as_int(os.getenv("AGENT_MODEL_MAX_TOKENS", os.getenv("VLM_MAX_TOKENS")), 0))
                if _as_int(os.getenv("AGENT_MODEL_MAX_TOKENS", os.getenv("VLM_MAX_TOKENS")), 0) > 0
                else None
            ),
            model_fewshot_max_image_side=max(
                1,
                _as_int(os.getenv("AGENT_MODEL_FEWSHOT_MAX_IMAGE_SIDE"), 1800),
            ),
            model_enable_thinking=_as_optional_bool(
                os.getenv("AGENT_MODEL_ENABLE_THINKING", os.getenv("VLM_ENABLE_THINKING"))
            ),
            model_json_mode=_as_bool(
                os.getenv("AGENT_MODEL_JSON_MODE", os.getenv("VLM_USE_RESPONSE_FORMAT")),
                False,
            ),
            extraction_max_pdf_pages=max(
                0,
                _as_int(os.getenv("AGENT_EXTRACTION_MAX_PDF_PAGES", os.getenv("VLM_MAX_PDF_PAGES")), 0),
            ),
            extraction_render_dpi=max(
                300,
                _as_int(os.getenv("AGENT_EXTRACTION_RENDER_DPI", os.getenv("VLM_PDF_RENDER_DPI")), 300),
            ),
            extraction_concurrency=max(
                1,
                _as_int(os.getenv("AGENT_EXTRACTION_CONCURRENCY", os.getenv("VLM_CONCURRENCY")), 1),
            ),
            extraction_reference_target_limit=max(
                1,
                _as_int(
                    os.getenv("AGENT_REFERENCE_TARGET_LIMIT", os.getenv("VLM_REFERENCE_TARGET_LIMIT")),
                    4,
                ),
            ),
            terminal_strip_mapping=_load_terminal_strip_mapping(),
            extraction_keep_temp_images=_as_bool(
                os.getenv("AGENT_KEEP_TEMP_IMAGES", os.getenv("VLM_KEEP_TEMP_IMAGES")),
                False,
            ),
            extraction_output_mode=output_mode,
            import_template_path=template_path.resolve() if template_path is not None else None,
            profile_detection_dpi=max(
                72,
                _as_int(os.getenv("AGENT_PROFILE_DETECTION_DPI"), 180),
            ),
            profile_auto_select_threshold=min(
                1.0,
                max(
                    0.0,
                    _as_float(os.getenv("AGENT_PROFILE_AUTO_SELECT_THRESHOLD"), 0.85),
                ),
            ),
            profile_max_pdf_bytes=max(
                1,
                _as_int(
                    os.getenv("AGENT_PROFILE_MAX_PDF_BYTES"),
                    200 * 1024 * 1024,
                ),
            ),
            enable_improvement=_as_bool(os.getenv("AGENT_ENABLE_IMPROVEMENT"), False),
            inline_worker=_as_bool(os.getenv("AGENT_INLINE_WORKER"), False),
            workspace_root=root,
        )


def _load_terminal_strip_mapping() -> dict[str, str]:
    mapping = dict(DEFAULT_TERMINAL_STRIP_MAPPING)
    raw = os.getenv("AGENT_TERMINAL_STRIP_MAP") or os.getenv("VLM_TERMINAL_STRIP_MAP")
    if not raw:
        return mapping
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Terminal strip mapping must be a JSON object.")
    mapping.update(validate_terminal_strip_mapping(parsed))
    return mapping
