"""Uploaded chat images are private model input for their own turn, with no external calls."""

import asyncio
import hashlib
import json
from uuid import uuid4

import httpx
import pymupdf
import pytest

from src.agent.explain_agent import ExplainActor, ExplainTurn
from src.agent.explain_agent.models import ExplainError

from .test_explain_agent import OWNER, PROJECT, ROW
from .test_explain_edits import EditBackend, agent


class AttachmentBackend(EditBackend):
    def __init__(self):
        super().__init__()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
        pixmap.clear_with(255)
        self.image = pixmap.tobytes("png")
        self.override = {}
        self.downloads = 0

    def request(self, request):
        if request.url.path.endswith("/connection_rescan_assets"):
            expected = {
                key: request.url.params[key][3:]
                for key in ("id", "project_id", "created_by", "conversation_id")
            }
            path = (
                f"projects/{expected['project_id']}/explain/{expected['conversation_id']}/"
                f"assets/{expected['id']}.png"
            )
            return httpx.Response(
                200,
                json=[
                    {
                        **expected,
                        "pdf_page_number": 1,
                        "uploaded": True,
                        "storage_path": path,
                        "checksum": "sha256:" + hashlib.sha256(self.image).hexdigest(),
                        **self.override,
                    }
                ],
            )
        if request.method == "GET" and "/storage/v1/object/" in request.url.path:
            self.downloads += 1
            return httpx.Response(200, content=self.image)
        return super().request(request)


def test_chat_images_enter_model_and_are_not_carried_to_next_turn_or_saved_as_viewed_pages():
    async def run():
        backend = AttachmentBackend()
        assistant, gateway = agent(backend, ["本轮图片可见。", "这是下一轮文字问题。"])
        attachment = uuid4()
        turn = ExplainTurn(
            project_id=PROJECT, connection_id=ROW, message="查看图片", attachment_ids=[attachment]
        )
        result = await assistant.ask(turn, ExplainActor(user_id=OWNER))
        images = [
            part
            for message in gateway.calls[0].messages
            if isinstance(message.get("content"), list)
            for part in message["content"]
            if part["type"] == "image_url"
        ]
        assert len(images) == 1 and images[0]["image_url"]["url"].startswith("data:image/png;base64,")
        assert result.visual_pages == [] and backend.downloads == 1
        await assistant.ask(
            turn.model_copy(update={"turn_id": uuid4(), "message": "下一轮问题", "attachment_ids": []}),
            ExplainActor(user_id=OWNER),
        )
        assert not any(isinstance(message.get("content"), list) for message in gateway.calls[1].messages)
        assert backend.downloads == 1
        assert "/storage/" not in json.dumps(gateway.calls[0].messages)

    asyncio.run(run())


@pytest.mark.parametrize(
    "override",
    [
        {"created_by": str(uuid4())},
        {"project_id": str(uuid4())},
        {"conversation_id": str(uuid4())},
        {"storage_path": "projects/foreign/private.png"},
        {"uploaded": False},
    ],
)
def test_foreign_attachment_is_rejected_before_download_or_model(override):
    async def run():
        backend = AttachmentBackend()
        backend.override = override
        assistant, gateway = agent(backend, ["不应执行"])
        with pytest.raises(ExplainError) as error:
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, attachment_ids=[uuid4()]),
                ExplainActor(user_id=OWNER),
            )
        assert error.value.code == "ATTACHMENT_NOT_FOUND"
        assert backend.downloads == 0 and not gateway.calls

    asyncio.run(run())


def test_tampered_image_fails_without_sending_image_to_model():
    async def run():
        backend = AttachmentBackend()
        backend.override = {"checksum": "sha256:" + "0" * 64}
        assistant, gateway = agent(backend, ["不应执行"])
        with pytest.raises(ExplainError) as error:
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, attachment_ids=[uuid4()]),
                ExplainActor(user_id=OWNER),
            )
        assert error.value.code == "ATTACHMENT_UNAVAILABLE" and not gateway.calls

    asyncio.run(run())
