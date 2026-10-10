from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..domain.models.profiles import ProfileSnapshot


@runtime_checkable
class DrawingProfile(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def checksum(self) -> str: ...

    @property
    def snapshot(self) -> ProfileSnapshot: ...

    def resource(self, name: str) -> Path: ...


class SnapshotDrawingProfile:
    def __init__(self, snapshot: ProfileSnapshot) -> None:
        self._snapshot = snapshot

    @property
    def key(self) -> str:
        return self._snapshot.manifest.key

    @property
    def version(self) -> str:
        return self._snapshot.manifest.version

    @property
    def checksum(self) -> str:
        return self._snapshot.checksum

    @property
    def snapshot(self) -> ProfileSnapshot:
        return self._snapshot

    def resource(self, name: str) -> Path:
        return self._snapshot.resource(name)
