"""Read the complete persisted replacement preview; decision bodies never contain patches."""

import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_simple_management_api import OWNER, PROJECT, ROW, Backend, api


def setup():
    run_id, new_id = str(uuid4()), str(uuid4())
    run = {
        "id": run_id,
        "project_id": PROJECT,
        "conversation_id": str(uuid4()),
        "batch_id": "run-one",
        "status": "ready",
        "stage": "ready",
        "request": {
            "scope": {"workspace_code": "003.C"},
            "fields": "all",
            "result_mode": "replace_scope",
        },
        "profile": {},
        "checksum": "fixture",
        "created_at": "now",
        "updated_at": "now",
        "candidate": {
            "replacement": {
                "version": 1,
                "scanned_pages": [1],
                "removed": [
                    {
                        "connection_id": ROW,
                        "record_version": 1,
                        "source_pdf_page_number": 1,
                        "before": {"start_terminal": "OLD", "end_terminal": None},
                    }
                ],
            },
            "changes": [
                {
                    "action": "insert",
                    "connection_id": new_id,
                    "record_version": 0,
                    "source_pdf_page_number": 1,
                    "after": {"start_terminal": "NEW", "end_terminal": None},
                }
            ],
        },
    }

    class Store(Backend):
        def __init__(self):
            super().__init__()
            self.decisions = []
            self.contract = 1

        def respond(self, request):
            if request.url.path.endswith("/rpc/rescan_replacement_contract"):
                return (
                    httpx.Response(404, json={"code": "PGRST202"})
                    if self.contract is None
                    else httpx.Response(200, json=self.contract)
                )
            if request.url.path.endswith("/connection_rescan_runs"):
                assert request.url.params["project_id"] == f"eq.{PROJECT}"
                assert request.url.params["created_by"] == f"eq.{OWNER}"
                return httpx.Response(200, json=[run])
            if request.url.path.endswith("/rpc/decide_connection_rescan"):
                self.decisions.append(json.loads(request.content)["value"])
                return httpx.Response(
                    200, json={**run, "status": "applied", "versions": {new_id: 1}}
                )
            return super().respond(request)

    backend = Store()
    app = api.create_app(
        api.Settings("http://database", "fixture"), httpx.MockTransport(backend.respond)
    )
    return app, backend, run_id


def test_persisted_preview_keeps_explicit_empty_values_and_authorized_scope():
    app, backend, run = setup()
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        result = client.get(f"/api/v1/projects/{PROJECT}/rescans/{run}")
        assert result.status_code == 200
        value = result.json()
        assert value["request"]["result_mode"] == "replace_scope"
        assert (
            "end_terminal" in value["candidate"]["replacement"]["removed"][0]["before"]
        )
        assert (
            value["candidate"]["replacement"]["removed"][0]["before"]["end_terminal"]
            is None
        )
        assert value["candidate"]["changes"][0]["after"]["end_terminal"] is None
        assert set(value["candidate"]["changes"][0]["after"]) == {"start_terminal", "end_terminal"}
        assert not backend.decisions
        assert (
            client.get(
                f"/api/v1/projects/{PROJECT}/rescans/{run}",
                headers={"Authorization": "Bearer other"},
            ).status_code
            == 403
        )


@pytest.mark.parametrize("extra", ["candidate", "replacement"])
def test_client_cannot_supply_range_deletion_or_replacement_content(extra):
    app, backend, run = setup()
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        response = client.post(
            f"/api/v1/projects/{PROJECT}/rescans/{run}/decision",
            json={"checksum": "fixture", "accepted": True, extra: {"removed": []}},
        )
        assert response.status_code == 422 and not backend.decisions


@pytest.mark.parametrize("contract", [None, 0])
def test_unmigrated_database_never_receives_replacement_candidate_to_legacy_merge_rpc(
    contract,
):
    app, backend, run = setup()
    backend.contract = contract
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        result = client.post(
            f"/api/v1/projects/{PROJECT}/rescans/{run}/decision",
            json={"checksum": "fixture", "accepted": True},
        )
        assert result.status_code == 503 and not backend.decisions
        assert result.json()["detail"]["code"] == "RESCAN_REPLACEMENT_UNAVAILABLE"


def test_supported_replacement_confirmation_sends_only_trusted_identity_checksum_and_decision():
    app, backend, run = setup()
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        result = client.post(
            f"/api/v1/projects/{PROJECT}/rescans/{run}/decision",
            json={"checksum": "fixture", "accepted": True},
        )
        assert result.status_code == 200 and result.json()["status"] == "applied"
        assert backend.decisions == [
            {
                "project_id": PROJECT,
                "id": run,
                "actor": OWNER,
                "checksum": "fixture",
                "accepted": True,
            }
        ]
