from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_service.config import AgentSettings
from agent_service.main import create_app
from agent_service.profiles import ProfileRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROFILE_ROOT = REPOSITORY_ROOT / "services" / "agent" / "profiles"


def registry() -> ProfileRegistry:
    value = ProfileRegistry(
        profile_root=PROFILE_ROOT,
        workspace_root=REPOSITORY_ROOT,
        allow_legacy_references=True,
    )
    value.load_all()
    return value


def test_live_is_available_when_model_is_not_configured() -> None:
    settings = AgentSettings(profile_root=PROFILE_ROOT, workspace_root=REPOSITORY_ROOT)
    client = TestClient(create_app(settings=settings, profile_registry=registry()))
    assert client.get("/health/live").status_code == 200
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["model"]["ready"] is False
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert "/health/ready" in openapi.json()["paths"]


def test_ready_and_profile_contract_when_dependencies_are_configured() -> None:
    settings = AgentSettings(
        profile_root=PROFILE_ROOT,
        workspace_root=REPOSITORY_ROOT,
        model_base_url="http://model.test/v1",
        default_model="fake-vlm",
    )
    client = TestClient(create_app(settings=settings, profile_registry=registry()))
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    profiles = client.get("/v1/profiles")
    assert profiles.status_code == 200
    assert {item["key"] for item in profiles.json()["items"]} == {"zh", "abb"}
    rules = client.get("/v1/profiles/zh/versions/1.0.0/rules")
    assert rules.status_code == 200
    assert rules.json()["rules"]["profile_key"] == "zh"
    assert rules.json()["rules"]["extraction"]["output_contract"] == "wiring_connection_v1"
