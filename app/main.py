import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.runtime_schema import ensure_runtime_schema
from app.services.device_presence_monitor import device_presence_monitor
from app.services.event_bus import realtime_event_bus
from app.services.ingest_publish_state import ingest_publish_state
from app.services.ingest_runtime_metadata import ingest_runtime_metadata
from app.services.ingest_upload_gateway import ingest_upload_gateway
from app.services.realtime_hub import realtime_hub
from app.services.realtime_events import reset_device_status_cache
from app.services.system_metrics import metrics_collector

# Configure logging to ensure we see INFO logs in uvicorn output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "Medical Streaming API is running",
        "docs": "/docs",
        "version": "0.1.0",
    }


@app.on_event("startup")
async def on_startup() -> None:
    await ensure_runtime_schema()
    ingest_publish_state.clear_all()
    ingest_runtime_metadata.clear_all()
    reset_device_status_cache()
    realtime_event_bus.set_handler(realtime_hub.dispatch_event)
    await realtime_event_bus.start()
    await metrics_collector.start()
    await ingest_upload_gateway.start()
    await device_presence_monitor.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await device_presence_monitor.stop()
    await ingest_upload_gateway.stop()
    await metrics_collector.stop()
    await realtime_event_bus.stop()


app.include_router(api_router, prefix=settings.API_V1_STR)
