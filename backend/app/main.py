from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import auth, subscription

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bespin Subscription API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(subscription.router)

@app.get("/")
def read_root():
    return {"message": "Bespin Subscription API", "version": "1.0.0"}

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
