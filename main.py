from fastapi import FastAPI

from api.routes import health_router

app = FastAPI(title="AI Code Review Agent")

app.include_router(health_router)
