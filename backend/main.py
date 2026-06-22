from fastapi import FastAPI

from backend.health.router import router as health_router
from backend.ladder.router import router as ladder_router

app = FastAPI(title="NorthwindAI")
app.include_router(health_router)
app.include_router(ladder_router)
