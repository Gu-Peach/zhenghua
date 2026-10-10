from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from agent_service.application.document_extraction.runtime import GraphRuntime
from agent_service.application.document_extraction.settings import Settings as ZhWorkflowSettings
from agent_service.config import AgentSettings
from agent_service.domain.enums import ErrorCode
from agent_service.domain.models.image_payload import ImagePayload
from agent_service.graphs.document_extraction.helpers import _is_fatal_model_request_error
from agent_service.graphs.document_extraction.pages import _classify_pages_node
from agent_service.harness.model_gateway import (
    ModelGatewayError,
    ModelRequest,
    OpenAICompatibleModelGateway,
)
from agent_service.harness.retry import RetryPolicy
from agent_service.profiles.zh.policy import ZhExtractionPolicy


class ModelGatewayHttpErrorTests(unittest.TestCase):
    def test_invalid_model_request_is_marked_fatal_to_the_pdf_workflow(self) -> None:
        failure = ModelGatewayError(ErrorCode.INVALID_REQUEST, "bad model request")

        self.assertTrue(_is_fatal_model_request_error(failure))
        self.assertFalse(_is_fatal_model_request_error(ValueError("bad model output")))

    def test_page_classification_stops_at_first_invalid_request(self) -> None:
        class RejectingClassifier:
            def __init__(self) -> None:
                self.calls = 0

            async def classify_page(self, _image: ImagePayload, *, context_text: str = "") -> object:
                self.calls += 1
                raise ModelGatewayError(ErrorCode.INVALID_REQUEST, "provider rejected image")

        async def run() -> None:
            classifier = RejectingClassifier()
            runtime = GraphRuntime(
                settings=ZhWorkflowSettings.from_agent(AgentSettings()),
                extraction_client=classifier,
                output_mode="library",
                policy=ZhExtractionPolicy(),
            )
            with tempfile.TemporaryDirectory() as temporary:
                pages = []
                payloads = {}
                for number in range(1, 4):
                    path = Path(temporary) / f"page-{number}.png"
                    pages.append(
                        {
                            "page_number": number,
                            "image_path": str(path),
                            "blank": False,
                            "is_non_wiring": False,
                        }
                    )
                    payload = ImagePayload(name=path.name, mime_type="image/png", content=b"image")
                    payloads[str(path.resolve())] = payload
                    payloads[str(path)] = payload
                runtime.payload_by_path = payloads

                with self.assertRaises(ModelGatewayError):
                    await _classify_pages_node(
                        {
                            "output_path": temporary,
                            "pages": pages,
                            "drawing_index": {},
                            "pdf_path": "test.pdf",
                        },
                        runtime,
                    )

            self.assertEqual(classifier.calls, 1)

        asyncio.run(run())

    def test_bad_request_exposes_provider_message_without_retrying(self) -> None:
        async def run() -> None:
            attempts = 0

            async def handler(_request: httpx.Request) -> httpx.Response:
                nonlocal attempts
                attempts += 1
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "Model does not support image input",
                            "type": "BadRequestError",
                            "code": "unsupported_image",
                            "param": "messages",
                        }
                    },
                )

            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                gateway = OpenAICompatibleModelGateway(
                    base_url="http://model.test/v1",
                    default_model="text-only-model",
                    retry_policy=RetryPolicy(max_retries=3, initial_backoff_seconds=0),
                    client=client,
                )
                with self.assertRaises(ModelGatewayError) as caught:
                    await gateway.invoke(
                        ModelRequest(
                            agent_name="page_classification",
                            run_id="run-1",
                            messages=[{"role": "user", "content": "test"}],
                        )
                    )

            self.assertEqual(attempts, 1)
            self.assertEqual(caught.exception.code, ErrorCode.INVALID_REQUEST)
            self.assertIn("Model does not support image input", str(caught.exception))
            self.assertEqual(caught.exception.details["provider_code"], "unsupported_image")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
