from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .env import load_env_files
from .terminal_strips import (
    ALLOWED_TERMINAL_STRIPS,
    DEFAULT_TERMINAL_STRIP_MAPPING,
    validate_terminal_strip_mapping,
)


class ConfigError(RuntimeError):
    """Raised when required VLM configuration is missing."""


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    base_url: str
    chat_completions_endpoint: str | None
    model: str
    timeout_seconds: float
    max_pdf_pages: int
    concurrency: int
    image_batch_size: int
    use_response_format: bool
    prompt_path: Path
    retry_count: int = 2
    retry_backoff_seconds: float = 2.0
    retry_max_backoff_seconds: float = 30.0
    # None means "do not send"; True/False is forwarded as chat_template_kwargs.enable_thinking
    # (vLLM / SGLang style, e.g. Qwen3 reasoning models).
    enable_thinking: bool | None = None
    max_tokens: int | None = None
    library_root: Path | None = None
    grouping_prompt_path: Path | None = None
    grouping_image_batch_size: int = 8
    # Kept for compatibility with existing callers. Values loaded from .env
    # are derived from VLM_PDF_RENDER_DPI.
    pdf_render_scale: float = 300 / 72
    pdf_render_dpi: int = 300
    # Multimodal few-shot: attach example drawings + expected JSON as prior chat turns.
    few_shot_images: bool = True
    few_shot_examples_dir: Path | None = None
    segment_prompt_path: Path | None = None
    segment_concurrency: int = 4
    segment_retry_count: int = 1
    max_segment_pages: int = 20
    keep_temp_images: bool = False
    output_mode: str = "library"
    terminal_strip_mapping: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TERMINAL_STRIP_MAPPING))
    reference_target_limit: int = 4
    import_template_path: Path | None = None
    segment_few_shot_images: bool = True
    segment_few_shot_examples_dir: Path | None = None
    supabase_enabled: bool = False
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "images"
    # Three-stage page-agent configuration.
    page_scan_prompt_path: Path | None = None
    page_scan_few_shot_images: bool = True
    page_scan_few_shot_examples_dir: Path | None = None
    classification_prompt_path: Path | None = None
    classification_few_shot_images: bool = True
    classification_few_shot_examples_dir: Path | None = None
    cross_page_prompt_path: Path | None = None
    cross_page_few_shot_images: bool = True
    cross_page_few_shot_examples_dir: Path | None = None

    @property
    def chat_completions_url(self) -> str:
        if self.chat_completions_endpoint:
            return self.chat_completions_endpoint

        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _as_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid integer config value: {value}") from exc


def _as_float(value: str | None, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid float config value: {value}") from exc


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_optional_bool(value: str | None) -> bool | None:
    if value is None or value.strip() == "":
        return None
    return _as_bool(value)


def _as_optional_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    parsed = _as_int(value, 0)
    return parsed if parsed > 0 else None


def _terminal_strip_mapping(value: str | None) -> dict[str, str]:
    if not value or not value.strip():
        return dict(DEFAULT_TERMINAL_STRIP_MAPPING)
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ConfigError("VLM_TERMINAL_STRIP_MAP must be valid JSON.") from exc
    if not isinstance(raw, dict):
        raise ConfigError("VLM_TERMINAL_STRIP_MAP must be a JSON object.")
    mapping = dict(DEFAULT_TERMINAL_STRIP_MAPPING)
    try:
        mapping.update(validate_terminal_strip_mapping(raw))
    except ValueError as exc:
        raise ConfigError("VLM_TERMINAL_STRIP_MAP contains an unsupported terminal strip.") from exc
    return mapping


def default_prompt_path() -> Path:
    return default_page_scan_prompt_path()


def default_grouping_prompt_path() -> Path:
    return default_page_classification_prompt_path()


def default_segment_prompt_path() -> Path:
    return default_page_classification_prompt_path()


def default_prompts_root() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "zh"


def default_segment_few_shot_examples_dir() -> Path:
    return default_prompts_root() / "example_segment"


def default_few_shot_examples_dir() -> Path:
    return default_page_scan_few_shot_examples_dir()


def default_page_scan_prompt_path() -> Path:
    return default_prompts_root() / "page_scan_index.md"


def default_page_scan_few_shot_examples_dir() -> Path:
    return default_prompts_root() / "examples_wiring" / "002c"


def default_page_classification_prompt_path() -> Path:
    return default_prompts_root() / "page_classification.md"


def default_page_classification_few_shot_examples_dir() -> Path:
    return default_prompts_root() / "examples_page_classification"


def default_cross_page_prompt_path() -> Path:
    return default_prompts_root() / "page_cross_page_completion.md"


def default_cross_page_few_shot_examples_dir() -> Path:
    return default_prompts_root() / "examples_wiring" / "002c"


def default_library_root() -> Path:
    return Path(__file__).resolve().parents[3] / "frontend" / "public" / "library"


def load_settings(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    max_pdf_pages: int | None = None,
) -> Settings:
    load_env_files()

    resolved_model = model or _env_first("VLM_MODEL", "OPENAI_MODEL")
    if not resolved_model:
        raise ConfigError("Missing VLM model. Set VLM_MODEL or pass model in the request.")

    prompt_path = Path(os.getenv("VLM_PAGE_SCAN_PROMPT_PATH", default_page_scan_prompt_path()))
    grouping_prompt_path = None
    segment_prompt_path = None
    page_scan_prompt_path = Path(os.getenv("VLM_PAGE_SCAN_PROMPT_PATH", default_page_scan_prompt_path()))
    classification_prompt_path = Path(
        os.getenv("VLM_PAGE_CLASSIFICATION_PROMPT_PATH", default_page_classification_prompt_path())
    )
    cross_page_prompt_path = Path(
        os.getenv("VLM_CROSS_PAGE_PROMPT_PATH", default_cross_page_prompt_path())
    )
    library_root = Path(os.getenv("VLM_LIBRARY_ROOT", default_library_root()))
    resolved_base_url = base_url or _env_first("VLM_BASE_URL", "OPENAI_BASE_URL") or "https://api.openai.com/v1"
    chat_completions_endpoint = _env_first("VLM_CHAT_COMPLETIONS_URL", "OPENAI_CHAT_COMPLETIONS_URL")

    return Settings(
        api_key=api_key if api_key is not None else _env_first("VLM_API_KEY", "OPENAI_API_KEY"),
        base_url=resolved_base_url,
        chat_completions_endpoint=chat_completions_endpoint,
        model=resolved_model,
        timeout_seconds=_as_float(os.getenv("VLM_TIMEOUT_SECONDS"), 300.0),
        retry_count=max(0, _as_int(os.getenv("VLM_RETRY_COUNT"), 2)),
        retry_backoff_seconds=max(0.0, _as_float(os.getenv("VLM_RETRY_BACKOFF_SECONDS"), 2.0)),
        retry_max_backoff_seconds=max(
            0.0,
            _as_float(os.getenv("VLM_RETRY_MAX_BACKOFF_SECONDS"), 30.0),
        ),
        max_pdf_pages=max_pdf_pages if max_pdf_pages is not None else _as_int(os.getenv("VLM_MAX_PDF_PAGES"), 0),
        reference_target_limit=max(1, _as_int(os.getenv("VLM_REFERENCE_TARGET_LIMIT"), 4)),
        import_template_path=(Path(os.getenv("VLM_IMPORT_XLS_TEMPLATE_PATH"))
                              if os.getenv("VLM_IMPORT_XLS_TEMPLATE_PATH") else None),
        concurrency=max(1, _as_int(os.getenv("VLM_CONCURRENCY"), 1)),
        image_batch_size=max(1, _as_int(os.getenv("VLM_IMAGE_BATCH_SIZE"), 4)),
        use_response_format=_as_bool(os.getenv("VLM_USE_RESPONSE_FORMAT"), False),
        prompt_path=prompt_path,
        enable_thinking=_as_optional_bool(os.getenv("VLM_ENABLE_THINKING")),
        max_tokens=_as_optional_int(os.getenv("VLM_MAX_TOKENS")),
        library_root=library_root,
        grouping_prompt_path=grouping_prompt_path,
        grouping_image_batch_size=max(1, _as_int(os.getenv("VLM_GROUPING_IMAGE_BATCH_SIZE"), 8)),
        pdf_render_scale=max(
            300 / 72,
            _as_float(
                os.getenv("VLM_PDF_RENDER_SCALE"),
                _as_int(os.getenv("VLM_PDF_RENDER_DPI"), 300) / 72,
            ),
        ),
        pdf_render_dpi=max(300, _as_int(os.getenv("VLM_PDF_RENDER_DPI"), 300)),
        few_shot_images=False,
        few_shot_examples_dir=None,
        segment_prompt_path=segment_prompt_path,
        segment_concurrency=max(1, _as_int(os.getenv("VLM_SEGMENT_CONCURRENCY"), 4)),
        segment_retry_count=max(0, _as_int(os.getenv("VLM_SEGMENT_RETRY_COUNT"), 1)),
        max_segment_pages=max(1, _as_int(os.getenv("VLM_MAX_SEGMENT_PAGES"), 20)),
        keep_temp_images=_as_bool(os.getenv("VLM_KEEP_TEMP_IMAGES"), False),
        output_mode=os.getenv("VLM_OUTPUT_MODE", "library").strip().lower() or "library",
        terminal_strip_mapping=_terminal_strip_mapping(os.getenv("VLM_TERMINAL_STRIP_MAP")),
        segment_few_shot_images=False,
        segment_few_shot_examples_dir=None,
        supabase_enabled=_as_bool(os.getenv("SUPABASE_ENABLED"), False),
        supabase_url=(os.getenv("SUPABASE_URL") or "").rstrip("/") or None,
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY") or None,
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None,
        supabase_storage_bucket=os.getenv("SUPABASE_STORAGE_BUCKET", "images").strip() or "images",
        page_scan_prompt_path=page_scan_prompt_path,
        page_scan_few_shot_images=_as_bool(os.getenv("VLM_PAGE_SCAN_FEW_SHOT_IMAGES"), True),
        page_scan_few_shot_examples_dir=Path(
            os.getenv("VLM_PAGE_SCAN_FEW_SHOT_EXAMPLES_DIR", default_page_scan_few_shot_examples_dir())
        ),
        classification_prompt_path=classification_prompt_path,
        classification_few_shot_images=_as_bool(os.getenv("VLM_PAGE_CLASSIFICATION_FEW_SHOT_IMAGES"), True),
        classification_few_shot_examples_dir=Path(
            os.getenv(
                "VLM_PAGE_CLASSIFICATION_FEW_SHOT_EXAMPLES_DIR",
                default_page_classification_few_shot_examples_dir(),
            )
        ),
        cross_page_prompt_path=cross_page_prompt_path,
        cross_page_few_shot_images=_as_bool(os.getenv("VLM_CROSS_PAGE_FEW_SHOT_IMAGES"), True),
        cross_page_few_shot_examples_dir=Path(
            os.getenv(
                "VLM_CROSS_PAGE_FEW_SHOT_EXAMPLES_DIR",
                default_cross_page_few_shot_examples_dir(),
            )
        ),
    )
