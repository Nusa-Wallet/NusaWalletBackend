from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine
from app.modules.auth.router import router as auth_router
from app.modules.insights.router import router as insights_router
from app.modules.payment_link.router import router as payment_link_router
from app.modules.settlement.router import router as settlement_router
from app.modules.wallet.router import router as wallet_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # For the hackathon we create tables on startup. In production use Alembic.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="NusaWallet API",
    description="AI-powered multi-currency wallet — core service (auth, wallet, ledger, payment links, settlement).",
    version="0.1.0",
    lifespan=lifespan,
)

# Open CORS for the Expo dev client during the hackathon.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(wallet_router)
app.include_router(payment_link_router)
app.include_router(settlement_router)
app.include_router(insights_router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": "nusawallet-backend"}
