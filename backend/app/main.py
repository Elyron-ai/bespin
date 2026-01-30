from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.gateway import models as gateway_models  # noqa: F401 - import for table creation
from app.gateway.router import router as gateway_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bespin Tool Invocation Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gateway_router)

@app.get("/")
def read_root():
    return {"message": "Bespin Tool Invocation Gateway", "version": "0.1.0"}

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
