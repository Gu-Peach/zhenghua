from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from test_main_assistant_api import AssistantBackend, client_for, seed_turn
from test_simple_management_api import PROJECT


class NumberBackend(AssistantBackend):
    def __init__(self):
        super().__init__()
        base = self.tables["extraction_connection_rows"][0]
        self.tables["extraction_connection_rows"] = [
            {
                **deepcopy(base),
                "id": str(uuid4()),
                "principle_number": f"082R50{i:02}",
                "row_order": i,
                "end_terminal": f"+10-MA{51 if i <= 3 else 52}:{i}",
            }
            for i in range(1, 6)
        ]

    def respond(self, request):
        value = request.url.params.get("principle_number", "")
        if request.url.path.endswith(
            "/extraction_connection_rows"
        ) and value.startswith("in.("):
            self.calls.append(request)
            values = json.loads("[" + value[4:-1] + "]")
            rows = [
                row
                for row in self.tables["extraction_connection_rows"]
                if row["principle_number"] in values
                and all(
                    str(row.get(key)) == val[3:]
                    for key, val in request.url.params.items()
                    if val.startswith("eq.")
                )
            ]
            offset, limit = (
                int(request.url.params.get("offset", 0)),
                int(request.url.params.get("limit", 100)),
            )
            return httpx.Response(200, json=rows[offset : offset + limit])
        return super().respond(request)


@pytest.mark.parametrize("value", ["082R5001-05", "082R5001-082R5005", "082R5001～05"])
def test_bounded_principle_range_returns_actual_five_rows(value):
    backend = NumberBackend()
    _, turn, headers = seed_turn(backend, {"project_id": PROJECT, "pdf_page_number": 1})
    with client_for(backend) as client:
        response = client.post(
            f"/api/internal/assistant/turns/{turn}/tools",
            headers=headers,
            json={
                "name": "search_connections",
                "arguments": {"principle_number": value},
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert [row["principle_number"] for row in result["rows"]] == [
            f"082R50{i:02}" for i in range(1, 6)
        ]
        assert result["query_interpretation"]["kind"] == "number_range"
        assert result["rows"][3]["end_terminal"].startswith("+10-MA52")


def test_explicit_multiple_principles_paginates_without_widening_scope():
    backend = NumberBackend()
    _, turn, headers = seed_turn(backend, {"project_id": PROJECT, "pdf_page_number": 1})
    with client_for(backend) as client:
        response = client.post(
            f"/api/internal/assistant/turns/{turn}/tools",
            headers=headers,
            json={
                "name": "search_connections",
                "arguments": {
                    "principle_numbers": ["082R5001", "082R5003", "082R5005"],
                    "limit": 2,
                },
            },
        )
        assert response.status_code == 200, response.text
        assert len(response.json()["rows"]) == 2 and response.json()["has_more"]


def test_literal_hyphenated_number_takes_precedence_over_range_even_on_later_offset():
    backend = NumberBackend()
    literal = {
        **backend.tables["extraction_connection_rows"][0],
        "id": str(uuid4()),
        "principle_number": "082R5001-05",
    }
    backend.tables["extraction_connection_rows"].append(literal)
    _, turn, headers = seed_turn(backend, {"project_id": PROJECT, "pdf_page_number": 1})
    with client_for(backend) as client:
        path = f"/api/internal/assistant/turns/{turn}/tools"
        for offset in (0, 1):
            value = client.post(
                path,
                headers=headers,
                json={
                    "name": "search_connections",
                    "arguments": {"principle_number": "082R5001-05", "offset": offset},
                },
            ).json()
            assert value["query_interpretation"]["kind"] == "exact"
            assert len(value["rows"]) == (1 if offset == 0 else 0)


@pytest.mark.parametrize("number", ["082R5005-01", "082R5001-9999", "082R5001-MA51"])
def test_invalid_or_unbounded_ranges_do_not_widen_query(number):
    backend = NumberBackend()
    _, turn, headers = seed_turn(backend, {"project_id": PROJECT, "pdf_page_number": 1})
    with client_for(backend) as client:
        result = client.post(
            f"/api/internal/assistant/turns/{turn}/tools",
            headers=headers,
            json={
                "name": "search_connections",
                "arguments": {"principle_number": number},
            },
        ).json()
        assert (
            result["rows"] == [] and result["query_interpretation"]["kind"] == "exact"
        )


def test_range_returns_only_existing_scoped_rows_and_rejects_mixed_inputs():
    backend = NumberBackend()
    backend.tables["extraction_connection_rows"].pop()
    backend.tables["extraction_connection_rows"].append(
        {
            **backend.tables["extraction_connection_rows"][0],
            "id": str(uuid4()),
            "project_id": str(uuid4()),
            "principle_number": "082R5005",
        }
    )
    _, turn, headers = seed_turn(backend, {"project_id": PROJECT, "pdf_page_number": 1})
    with client_for(backend) as client:
        path = f"/api/internal/assistant/turns/{turn}/tools"
        result = client.post(
            path,
            headers=headers,
            json={
                "name": "search_connections",
                "arguments": {"principle_number": "082R5001-05"},
            },
        ).json()
        assert (
            len(result["rows"]) == 4
            and "082R5005" not in result["matched_principle_numbers"]
        )
        assert (
            client.post(
                path,
                headers=headers,
                json={
                    "name": "search_connections",
                    "arguments": {
                        "principle_number": "082R5001",
                        "principle_numbers": ["082R5002"],
                    },
                },
            ).status_code
            == 422
        )
