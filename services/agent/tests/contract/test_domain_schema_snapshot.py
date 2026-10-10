from __future__ import annotations

from pathlib import Path

from agent_service.domain.schema import contract_schema_checksum

SNAPSHOT = Path(__file__).resolve().parents[2] / "contracts" / "domain-schema.sha256"


def test_domain_schema_matches_reviewed_snapshot() -> None:
    assert contract_schema_checksum() == SNAPSHOT.read_text(encoding="ascii").strip()
