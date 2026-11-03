"""FastAPI app. Run: uvicorn app.main:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, auth, manage, maps, sensors, webhooks
from app.config import get_settings

app = FastAPI(title="Kampung Adem API", version="0.1.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

for r in (auth.router, sensors.router, maps.router, alerts.router, manage.router,
          webhooks.router):
    app.include_router(r, prefix="/api/v1")
