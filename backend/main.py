import os

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from app.core.config import settings
from app.api.routes import router as transaction_router
from app.api.imports import router as import_router
from app.api.misc import router as misc_router
from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.services.auth_service import require_auth, resolve_cookie_secure, validate_auth_settings

# AUTH_ENABLED=true 但 OIDC 配置缺失 → 启动即失败（fail-fast，设计 §5）
validate_auth_settings()

app = FastAPI(title="BeanWEB API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.AUTH_ENABLED:
    # 仅 on 模式挂载：off 模式零中间件零扰动（设计 §6）。
    # max_age 即会话绝对超时（签名时间戳超龄 = 会话清空，调小配置即刻吊销存量会话）
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.AUTH_SECRET_KEY,
        session_cookie="beanweb_session",
        max_age=settings.AUTH_SESSION_MAX_AGE,
        same_site="lax",
        https_only=resolve_cookie_secure(),
    )

app.include_router(auth_router)
app.include_router(transaction_router, dependencies=[Depends(require_auth)])
app.include_router(import_router, dependencies=[Depends(require_auth)])
app.include_router(misc_router, dependencies=[Depends(require_auth)])
app.include_router(analytics_router, dependencies=[Depends(require_auth)])


@app.get("/health")
def health_check():
    return {"status": "ok"}


if os.path.isdir(settings.FRONTEND_DIST_DIR):
    # P2（形态 B）：同端口 serve 前端 dist，TLS/入口统一交给反代。
    # 路由先于 Mount 注册，/api 与 /health 优先匹配；目录缺失（未 build）则整体跳过
    _INDEX_HTML = os.path.join(settings.FRONTEND_DIST_DIR, "index.html")

    app.mount("/", StaticFiles(directory=settings.FRONTEND_DIST_DIR, html=True), name="frontend")

    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request: Request, exc: StarletteHTTPException):
        # SPA fallback：非 /api 的 404（如 /transactions 前端路由）回落 index.html；
        # /api 路径与非 404 状态保持 FastAPI 默认 JSON 语义
        if (
            exc.status_code == 404
            and not request.url.path.startswith("/api")
            and os.path.isfile(_INDEX_HTML)
        ):
            return FileResponse(_INDEX_HTML)
        headers = getattr(exc, "headers", None)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)
