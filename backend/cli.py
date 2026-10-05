from __future__ import annotations

try:
    from .app.cli import main
except ImportError:
    from app.cli import main


if __name__ == "__main__":
    main()
