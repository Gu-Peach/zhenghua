from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Request


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


async def refresh_current_profiles(
    request: Request,
    _: None = Depends(require_internal_service),
) -> None:
    """New commands see the remote active set; running frozen bindings stay unchanged."""
    packages = getattr(request.app.state, "profile_packages", None)
    if packages is not None and (request.method == "POST" or request.url.path.startswith("/v1/profiles")):
        try:
            await packages.load_registry(request.app.state.profile_registry)
        except Exception as exc:
            raise HTTPException(503, detail="规则注册同步失败，请稍后重试") from exc
