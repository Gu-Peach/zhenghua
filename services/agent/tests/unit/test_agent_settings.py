from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_service.config import AgentSettings, load_agent_env, repository_root


class AgentSettingsTests(unittest.TestCase):
    def test_only_services_agent_env_file_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").write_text("AGENT_DEFAULT_MODEL=root-model\n", encoding="utf-8")
            (root / "backend").mkdir()
            (root / "backend" / ".env").write_text("VLM_MODEL=backend-model\n", encoding="utf-8")
            agent_env = root / "services" / "agent" / ".env"
            agent_env.parent.mkdir(parents=True)
            agent_env.write_text("AGENT_DEFAULT_MODEL=agent-model\n", encoding="utf-8")

            with patch("agent_service.config.repository_root", return_value=root):
                with patch.dict(os.environ, {}, clear=True):
                    load_agent_env()
                    self.assertEqual(os.environ.get("AGENT_DEFAULT_MODEL"), "agent-model")
                    self.assertNotIn("VLM_MODEL", os.environ)

    def test_full_chat_completions_url_is_enough_to_configure_model(self) -> None:
        values = {
            "AGENT_MODEL_CHAT_COMPLETIONS_URL": "http://model.local/v1/chat/completions",
            "AGENT_DEFAULT_MODEL": "test-vlm",
        }
        with patch("agent_service.config.load_agent_env"), patch.dict(os.environ, values, clear=True):
            settings = AgentSettings.from_env()

        self.assertIsNone(settings.model_base_url)
        self.assertTrue(settings.model_configured)

    def test_legacy_vlm_environment_maps_to_standalone_agent_settings(self) -> None:
        values = {
            "VLM_BASE_URL": "http://model.local/v1",
            "VLM_CHAT_COMPLETIONS_URL": "http://model.local/v1/chat/completions",
            "VLM_API_KEY": "test-key",
            "VLM_MODEL": "test-vlm",
            "VLM_TIMEOUT_SECONDS": "91",
            "VLM_RETRY_COUNT": "3",
            "VLM_RETRY_BACKOFF_SECONDS": "0.5",
            "VLM_RETRY_MAX_BACKOFF_SECONDS": "4",
            "VLM_MAX_TOKENS": "4096",
            "AGENT_MODEL_FEWSHOT_MAX_IMAGE_SIDE": "1600",
            "VLM_USE_RESPONSE_FORMAT": "true",
            "VLM_ENABLE_THINKING": "false",
            "VLM_PDF_RENDER_DPI": "360",
            "VLM_CONCURRENCY": "2",
            "VLM_SEGMENT_CONCURRENCY": "3",
            "VLM_REFERENCE_TARGET_LIMIT": "5",
            "VLM_MAX_SEGMENT_PAGES": "25",
            "VLM_KEEP_TEMP_IMAGES": "true",
            "VLM_OUTPUT_MODE": "single_xlsx",
            "VLM_IMPORT_XLS_TEMPLATE_PATH": "case/template.xls",
        }
        with patch("agent_service.config.load_agent_env"), patch.dict(os.environ, values, clear=True):
            settings = AgentSettings.from_env()

        self.assertEqual(settings.model_base_url, "http://model.local/v1")
        self.assertEqual(settings.model_chat_completions_url, "http://model.local/v1/chat/completions")
        self.assertEqual(settings.default_model, "test-vlm")
        self.assertEqual(settings.model_timeout_seconds, 91)
        self.assertEqual(settings.model_max_retries, 3)
        self.assertEqual(settings.model_retry_initial_backoff_seconds, 0.5)
        self.assertEqual(settings.model_retry_max_backoff_seconds, 4)
        self.assertEqual(settings.model_max_tokens, 4096)
        self.assertEqual(settings.model_fewshot_max_image_side, 1600)
        self.assertTrue(settings.model_json_mode)
        self.assertFalse(settings.model_enable_thinking)
        self.assertEqual(settings.extraction_render_dpi, 360)
        self.assertEqual(settings.extraction_concurrency, 2)
        self.assertEqual(settings.extraction_reference_target_limit, 5)
        self.assertFalse(hasattr(settings, "extraction_segment_concurrency"))
        self.assertFalse(hasattr(settings, "extraction_max_segment_pages"))
        self.assertTrue(settings.extraction_keep_temp_images)
        self.assertEqual(settings.extraction_output_mode, "single_xlsx")
        self.assertEqual(
            settings.import_template_path,
            (repository_root() / Path("case/template.xls")).resolve(),
        )

    def test_supabase_persistence_requires_only_agent_namespaced_settings(self) -> None:
        values = {
            "AGENT_PERSISTENCE_BACKEND": "supabase",
            "AGENT_CHECKPOINT_BACKEND": "supabase",
            "AGENT_SUPABASE_URL": "http://127.0.0.1:54321/",
            "AGENT_SUPABASE_SERVICE_ROLE_KEY": "service-role-test",
            "AGENT_SUPABASE_STORAGE_BUCKET": "project-assets",
        }
        with patch("agent_service.config.load_agent_env"), patch.dict(os.environ, values, clear=True):
            settings = AgentSettings.from_env()

        self.assertEqual(settings.persistence_backend, "supabase")
        self.assertEqual(settings.checkpoint_backend, "supabase")
        self.assertEqual(settings.supabase_url, "http://127.0.0.1:54321")
        self.assertTrue(settings.supabase_configured)

    def test_legacy_supabase_credentials_enable_private_agent_persistence(self) -> None:
        values = {
            "SUPABASE_ENABLED": "true",
            "SUPABASE_URL": "http://127.0.0.1:54321/",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-test",
            "SUPABASE_STORAGE_BUCKET": "images",
        }
        with patch("agent_service.config.load_agent_env"), patch.dict(os.environ, values, clear=True):
            settings = AgentSettings.from_env()

        self.assertEqual(settings.persistence_backend, "supabase")
        self.assertEqual(settings.checkpoint_backend, "supabase")
        self.assertEqual(settings.supabase_url, "http://127.0.0.1:54321")
        self.assertEqual(settings.supabase_storage_bucket, "project-assets")
        self.assertTrue(settings.supabase_configured)


if __name__ == "__main__":
    unittest.main()
