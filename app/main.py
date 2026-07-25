from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.modules.auth.router import router as auth_router
from app.modules.insights.router import router as insights_router
from app.modules.profile.router import router as profile_router
from app.modules.payment_link.router import public_router as payment_link_public_router
from app.modules.payment_link.router import router as payment_link_router
from app.modules.settlement.router import router as settlement_router
from app.modules.wallet.router import router as wallet_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # For the hackathon we create tables on startup. In production use Alembic.
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="NusaWallet API",
    description="AI-powered multi-currency wallet — core service (auth, wallet, ledger, payment links, settlement).",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# Open CORS for the Expo dev client during the hackathon.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials="*" not in settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(wallet_router)
app.include_router(payment_link_router)
app.include_router(payment_link_public_router)
app.include_router(settlement_router)
app.include_router(insights_router)
app.include_router(profile_router)


@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "service": "nusawallet-backend",
        "environment": settings.app_env,
    }
