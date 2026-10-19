"""Catalog naming API; all storage and database requests stay in MockTransport."""

from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_simple_management_api import OWNER, PROFILE, Backend, api


@pytest.fixture
def catalog():
    backend = Backend()
    backend.rename_conflict = False
    row = backend.tables["extraction_profiles"][0]
    row["resource_ref"] = (
        f"storage://project-assets/profiles/{OWNER}/zh/2.1.0/" + "0" * 64 + ".zip"
    )
    writes = []

    def handle(request):
        if (
            request.method == "PATCH"
            and request.url.path == "/rest/v1/extraction_profiles"
        ):
            writes.append(request)
            if backend.rename_conflict:
                return httpx.Response(200, json=[])
            params = request.url.params
            selected = [
                r
                for r in backend.tables["extraction_profiles"]
                if all(
                    str(r.get(k)) == v.removeprefix("eq.") for k, v in params.items()
                )
            ]
            for item in selected:
                item.update(json.loads(request.content))
            return httpx.Response(200, json=selected)
        return backend.respond(request)

    with TestClient(
        api.create_app(
            api.Settings("http://database", "test"), httpx.MockTransport(handle)
        )
    ) as client:
        yield client, backend, writes


def test_rename_updates_only_catalog_name_and_is_idempotent(catalog):
    client, backend, writes = catalog
    before = deepcopy(backend.tables)
    original = before["extraction_profiles"][0]["display_name"]
    body = {"display_name": "  测试卷盘规则  ", "expected_display_name": original}
    url = f"/api/v1/rule-library/{PROFILE}"
    headers = {"Authorization": "Bearer owner"}
    response = client.patch(url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert (
        response.json()["display_name"] == "测试卷盘规则"
        and response.json()["can_rename"]
    )
    expected = deepcopy(before)
    expected["extraction_profiles"][0]["display_name"] = "测试卷盘规则"
    assert backend.tables == expected
    assert json.loads(writes[0].content) == {"display_name": "测试卷盘规则"}
    assert writes[0].url.params["created_by"] == f"eq.{OWNER}"
    assert writes[0].url.params["display_name"] == "eq." + original
    assert client.patch(url, headers=headers, json=body).status_code == 200
    assert len(writes) == 1
    listed = client.get("/api/v1/rule-library", headers=headers).json()
    assert listed[0]["display_name"] == "测试卷盘规则"
    assert not any("storage" in request.url.path for request in backend.calls)


def test_rename_owner_validation_conflict_and_missing(catalog):
    client, backend, writes = catalog
    url = f"/api/v1/rule-library/{PROFILE}"
    original = backend.tables["extraction_profiles"][0]["display_name"]
    body = {"display_name": "新规则", "expected_display_name": original}
    assert client.patch(url, json=body).status_code == 401
    assert (
        client.patch(
            url, headers={"Authorization": "Bearer other"}, json=body
        ).status_code
        == 403
    )
    headers = {"Authorization": "Bearer owner"}
    for name in ("", "   ", "字" * 121):
        assert (
            client.patch(
                url, headers=headers, json={**body, "display_name": name}
            ).status_code
            == 422
        )
    assert (
        client.patch(
            url, headers=headers, json={**body, "profile_key": "hijack"}
        ).status_code
        == 422
    )
    response = client.patch(
        url, headers=headers, json={**body, "expected_display_name": "过期名称"}
    )
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "PROFILE_NAME_CONFLICT"
    )
    assert (
        client.patch(
            f"/api/v1/rule-library/{uuid4()}", headers=headers, json=body
        ).status_code
        == 404
    )
    backend.tables["extraction_profiles"][0]["resource_ref"] = "local://zh/profile.json"
    assert client.patch(url, headers=headers, json=body).status_code == 422
    assert writes == []


def test_rename_conditional_update_conflict_leaves_all_data_unchanged(catalog):
    client, backend, writes = catalog
    before = deepcopy(backend.tables)
    backend.rename_conflict = True
    response = client.patch(
        f"/api/v1/rule-library/{PROFILE}",
        headers={"Authorization": "Bearer owner"},
        json={
            "display_name": "新名字",
            "expected_display_name": before["extraction_profiles"][0]["display_name"],
        },
    )
    assert response.status_code == 409
    assert backend.tables == before and len(writes) == 1
