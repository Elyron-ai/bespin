import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base, SessionLocal
from app.gateway import models as gateway_models  # noqa: F401 - import for table creation
from app.gateway.router import router as gateway_router
from app.gateway.billing_router import router as billing_router
from app.console.router import router as console_router
from app.playground.router import router as playground_router
from app.gateway.billing_seed import seed_all_billing_data

Base.metadata.create_all(bind=engine)

# Seed billing data on startup
def _seed_billing_data():
    """Seed default billing data (metered events, plans, capabilities)."""
    db = SessionLocal()
    try:
        seed_all_billing_data(db)
    finally:
        db.close()

_seed_billing_data()

app = FastAPI(title="Bespin Tool Invocation Gateway", version="0.1.0")

# Configure CORS origins from environment variable
# In production, set CORS_ORIGINS to a comma-separated list of allowed origins
# Example: CORS_ORIGINS=https://app.example.com,https://admin.example.com
cors_origins_env = os.environ.get("CORS_ORIGINS", "")
if cors_origins_env:
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
else:
    # Default to localhost origins for development only
    cors_origins = ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:3000", "http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(gateway_router)
app.include_router(billing_router)
app.include_router(console_router)
app.include_router(playground_router)

@app.get("/")
def read_root():
    return {"message": "Bespin Tool Invocation Gateway", "version": "0.1.0"}

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
