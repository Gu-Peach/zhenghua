import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services/server/src"))
from wiring_server.config import Settings
from wiring_server.models import LoginInput, SessionResponse
from wiring_server.repository import Repository, ServiceError
from wiring_server.simple_management import ManagementService
from wiring_server.simple_routes import install_management_routes
from wiring_server.explain_routes import install_explain_routes
from wiring_server.profile_routes import install_profile_routes


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    config = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(600, connect=15), transport=transport
        ) as http:
            app.state.db = Repository(config, http)
            app.state.management = ManagementService(app.state.db)
            yield

    app = FastAPI(title="Wiring Workbench Server", version="2.16.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(
            {config.web_origin, "http://localhost:5174", "http://127.0.0.1:5174"}
        ),
        allow_credentials=True,
        expose_headers=["Content-Disposition"],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
        ],
    )

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        response = JSONResponse(
            status_code=exc.status,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )
        if exc.status == 401 and request.url.path == "/api/v1/auth/refresh":
            response.delete_cookie("wiring_refresh", path="/api/v1/auth")
        return response

    async def identity(
        request: Request, authorization: Annotated[str | None, Header()] = None
    ) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise ServiceError(401, "AUTH_REQUIRED", "请先登录")
        token = authorization[7:]
        try:
            response = await request.app.state.db.http.get(
                config.supabase_url + "/auth/v1/user",
                headers={
                    "apikey": config.service_key,
                    "Authorization": "Bearer " + token,
                },
            )
        except httpx.HTTPError as exc:
            raise ServiceError(503, "AUTH_UNAVAILABLE", "登录服务暂不可用") from exc
        if response.is_error:
            raise ServiceError(401, "SESSION_EXPIRED", "登录已过期，请重新登录")
        request.state.token = token
        return str(UUID(response.json()["id"]))

    async def auth_session(
        request: Request, response: Response, grant: str, payload: dict[str, str]
    ) -> dict[str, Any]:
        try:
            result = await request.app.state.db.http.post(
                config.supabase_url + "/auth/v1/token",
                params={"grant_type": grant},
                json=payload,
                headers={"apikey": config.service_key},
            )
        except httpx.HTTPError as exc:
            raise ServiceError(503, "AUTH_UNAVAILABLE", "登录服务暂不可用") from exc
        if result.is_error:
            if result.status_code >= 500 or result.status_code == 429:
                raise ServiceError(
                    503, "AUTH_UNAVAILABLE", "登录服务暂不可用，请稍后重试"
                )
            raise ServiceError(401, "LOGIN_FAILED", "邮箱或密码错误，或登录已过期")
        data = result.json()
        response.set_cookie(
            "wiring_refresh",
            data["refresh_token"],
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=30 * 86400,
            path="/api/v1/auth",
        )
        who = data["user"]
        return {
            "accessToken": data["access_token"],
            "expiresIn": data["expires_in"],
            "user": {
                "id": who["id"],
                "email": who.get("email", ""),
                "name": who.get("user_metadata", {}).get("display_name")
                or who.get("email", ""),
                "role": "工程师",
            },
        }

    @app.post("/api/v1/auth/login", response_model=SessionResponse)
    async def login(
        payload: LoginInput, request: Request, response: Response
    ) -> dict[str, Any]:
        return await auth_session(request, response, "password", payload.model_dump())

    def cookie_origin(request: Request) -> None:
        if request.headers.get("origin") not in {
            config.web_origin,
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        }:
            raise ServiceError(403, "ORIGIN_DENIED", "请求来源不受信任")

    @app.post("/api/v1/auth/refresh", response_model=SessionResponse)
    async def refresh(request: Request, response: Response) -> dict[str, Any]:
        cookie_origin(request)
        token = request.cookies.get("wiring_refresh")
        if not token:
            raise ServiceError(401, "AUTH_REQUIRED", "请先登录")
        return await auth_session(
            request, response, "refresh_token", {"refresh_token": token}
        )

    @app.post("/api/v1/auth/logout", status_code=204)
    async def logout(
        request: Request,
        response: Response,
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        cookie_origin(request)
        # Expired access JWT must not prevent clearing the local refresh cookie.
        if authorization and authorization.startswith("Bearer "):
            try:
                revoked = await request.app.state.db.http.post(
                    config.supabase_url + "/auth/v1/logout",
                    headers={
                        "apikey": config.service_key,
                        "Authorization": authorization,
                    },
                )
                if revoked.status_code >= 500:
                    logging.getLogger(__name__).warning(
                        "Remote logout unavailable; local session cleared"
                    )
            except httpx.HTTPError:
                logging.getLogger(__name__).warning(
                    "Remote logout unreachable; local session cleared"
                )
        response.delete_cookie("wiring_refresh", path="/api/v1/auth")
        response.status_code = 204
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    from wiring_server.assistant_routes import install_assistant_routes

    install_assistant_routes(app, identity)
    install_management_routes(app, identity)
    install_explain_routes(app, identity)
    install_profile_routes(app, identity)
    return app


app = create_app()
