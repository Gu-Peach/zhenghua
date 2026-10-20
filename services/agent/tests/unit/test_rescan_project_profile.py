"""Explicit per-project upgrade freezes a new task package without rewriting old batches."""

import asyncio
import io
import zipfile
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.agent.explain_agent.rescan_execution import CandidateSession, frozen_binding
from src.agent.explain_agent.rescan_worker import RescanSnapshot
from src.config import AgentSettings
from src.profiles.package import checksum, seal_package
from tests.unit.test_profile_validation import package as package


@pytest.fixture
def archive(package):
    root, *_ = package
    seal_package(root, source_checksum="sha256:" + "0" * 64)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as writer:
        for path in root.rglob("*"):
            if path.is_file():
                writer.writestr(path.relative_to(root).as_posix(), path.read_bytes())
    return stream.getvalue()


@pytest.mark.parametrize("source", ["project_reference", "historical"])
def test_task_source_selects_exact_snapshot_without_overwriting_history(tmp_path, archive, source):
    project, batch = str(uuid4()), str(uuid4())
    ref = f"profiles/{uuid4()}/optional_negative/1.0.0/{checksum(archive)[7:]}.zip"
    old = f"projects/{project}/runs/{batch}/profile.zip"
    calls = []

    class Repo:
        async def artifact(self, *args):
            calls.append("artifact")
            assert source == "historical"
            return {"snapshot": {"path": old, "checksum": checksum(archive)}}

        async def get(self, bucket, path):
            calls.append(path)
            assert path == (ref if source == "project_reference" else old)
            return archive

    job = {
        "project_id": project,
        "batch_id": batch,
        "profile": {"key": "optional_negative", "version": "1.0.0", "checksum": checksum(archive)},
        "project_snapshot": {"profile_source": source, "profile_ref": "storage://project-assets/" + ref},
    }
    binding = asyncio.run(frozen_binding(CandidateSession(Repo(), job), AgentSettings(), tmp_path / "run"))
    assert binding.profile.key == "optional_negative" and binding.profile.version == "1.0.0"
    assert ("artifact" in calls) == (source == "historical")


@pytest.mark.parametrize("failure", ["checksum", "local_ref", "foreign_path", "unknown_source"])
def test_current_rule_failure_never_falls_back_to_batch_or_local(tmp_path, archive, failure):
    class Repo:
        async def artifact(self, *args):
            raise AssertionError("Cannot use historical batch for explicitly upgraded task")

        async def get(self, bucket, path):
            return archive

    job = {
        "project_id": str(uuid4()),
        "batch_id": str(uuid4()),
        "profile": {"key": "optional_negative", "version": "1.0.0", "checksum": checksum(archive)},
        "project_snapshot": {
            "profile_source": "project_reference",
            "profile_ref": f"storage://project-assets/profiles/{uuid4()}/optional_negative/1.0.0/{checksum(archive)[7:]}.zip",
        },
    }
    if failure == "checksum":
        job["profile"]["checksum"] = "sha256:" + "0" * 64
    elif failure == "local_ref":
        job["project_snapshot"]["profile_ref"] = "local://optional_negative/profile.json"
    elif failure == "foreign_path":
        job["project_snapshot"]["profile_ref"] = "storage://project-assets/projects/elsewhere/package.zip"
    else:
        job["project_snapshot"]["profile_source"] = "guess_latest"
    with pytest.raises(ValueError):
        asyncio.run(frozen_binding(CandidateSession(Repo(), job), AgentSettings(), tmp_path / "run"))


def test_worker_snapshot_keeps_explicit_source_and_legacy_default():
    value = {
        "pages": [],
        "scan_pages": [],
        "profile_ref": "storage://selected",
        "profile_source": "project_reference",
        "profile_id": str(uuid4()),
    }
    snapshot = RescanSnapshot.model_validate(value).model_dump(mode="json")
    assert snapshot["profile_source"] == "project_reference" and snapshot["profile_id"] == value["profile_id"]
    assert RescanSnapshot(pages=[], scan_pages=[], profile_ref="legacy").profile_source == "historical"
    with pytest.raises(ValidationError):
        RescanSnapshot.model_validate({**value, "profile_source": "latest_at_runtime"})
