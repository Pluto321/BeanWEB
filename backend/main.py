from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import router as transaction_router
from app.api.imports import router as import_router
from app.api.misc import router as misc_router
from app.api.analytics import router as analytics_router

app = FastAPI(title="BeanWEB API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transaction_router)
app.include_router(import_router)
app.include_router(misc_router)
app.include_router(analytics_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
