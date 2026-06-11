from fastapi import FastAPI

from backend.health.router import router as health_router

app = FastAPI(title="NorthwindAI")
app.include_router(health_router)

