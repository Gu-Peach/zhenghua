from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request


async def require_internal_service(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    expected = request.app.state.settings.internal_token
    if not expected:
        if request.app.state.settings.environment.lower() not in {"development", "test"}:
            raise HTTPException(
                status_code=503,
                detail="Internal service authentication is not configured.",
            )
        return
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Internal service authorization is required.")
    supplied = authorization[len(prefix) :]
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Internal service authorization is invalid.")
