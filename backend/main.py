from __future__ import annotations

try:
    from .app.main import app, create_app
except ImportError:
    from app.main import app, create_app

__all__ = ["app", "create_app"]
