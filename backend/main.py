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
    # 静态资源挂 /assets 子路径而非 Mount("/")——后者匹配一切路径，会在
    # Starlette redirect_slashes 之前吃掉依赖 307 的无斜杠 API 变体
    # （/api/transactions → 404，回归引入于 3e56b72）；页面级路由由 404 异常处理器兜底
    _DIST_ROOT = os.path.normpath(settings.FRONTEND_DIST_DIR)
    _INDEX_HTML = os.path.join(_DIST_ROOT, "index.html")
    _ASSETS_DIR = os.path.join(_DIST_ROOT, "assets")

    if os.path.isdir(_ASSETS_DIR):
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="frontend-assets")

    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request: Request, exc: StarletteHTTPException):
        # 非 /api 的 404：先找 dist 内真实文件（favicon 等），否则回 index.html（SPA 前端路由）；
        # /api 路径与非 404 状态保持 FastAPI 默认 JSON 语义
        if exc.status_code == 404 and not request.url.path.startswith("/api"):
            candidate = os.path.normpath(os.path.join(_DIST_ROOT, request.url.path.lstrip("/")))
            if candidate.startswith(_DIST_ROOT + os.sep) and os.path.isfile(candidate):
                return FileResponse(candidate)
            if os.path.isfile(_INDEX_HTML):
                return FileResponse(_INDEX_HTML)
        headers = getattr(exc, "headers", None)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)
