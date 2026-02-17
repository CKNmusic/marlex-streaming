from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.models.user import User
from app.schemas.manager_runtime import (
    IngestGatewayBandwidthEstimate,
    IngestGatewayStatus,
    ManagerMetric,
    ManagerMetricHistory,
)
from app.services.ingest_upload_gateway import ingest_upload_gateway
from app.services.system_metrics import metrics_collector

router = APIRouter()


@router.get("/metrics/current", response_model=ManagerMetric)
async def get_manager_current_metrics(
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    return metrics_collector.current()


@router.get("/metrics/history", response_model=ManagerMetricHistory)
async def get_manager_metrics_history(
    limit: int = Query(default=120, ge=1, le=5000),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    return {"items": metrics_collector.history(limit=limit)}


@router.get("/ingest-gateway/status", response_model=IngestGatewayStatus)
async def get_ingest_gateway_status(
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    return ingest_upload_gateway.status()


@router.get("/ingest-gateway/bandwidth", response_model=IngestGatewayBandwidthEstimate)
async def get_ingest_gateway_bandwidth(
    upload_count: int = Query(default=1, ge=1, le=4096),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    return ingest_upload_gateway.bandwidth_recommendation(upload_count=upload_count)
