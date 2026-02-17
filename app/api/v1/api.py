from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.v1.endpoints import (
    app_settings,
    cities,
    device_auth,
    devices,
    invites,
    places,
    marks,
    login,
    manager_runtime,
    notifications,
    procedures,
    protocols,
    realtime,
    records,
    register,
    users,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.device import Device as DeviceSchema
from app.schemas.device import DeviceBind

api_router = APIRouter()
api_router.include_router(login.router, prefix="/login", tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(places.router, prefix="/places", tags=["places"])
api_router.include_router(cities.router, prefix="/cities", tags=["cities"])
api_router.include_router(marks.router, prefix="/marks", tags=["marks"])
api_router.include_router(records.router, prefix="/records", tags=["records"])
api_router.include_router(procedures.router, prefix="/procedures", tags=["procedures"])
api_router.include_router(protocols.router, prefix="/protocols", tags=["protocols"])
api_router.include_router(app_settings.router, prefix="/app-settings", tags=["app_settings"])
api_router.include_router(device_auth.router, prefix="/device-auth", tags=["device_auth"])
api_router.include_router(manager_runtime.router, prefix="/manager-runtime", tags=["manager_runtime"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(invites.router, prefix="/invites", tags=["invites"])
api_router.include_router(register.router, prefix="/register", tags=["register"])
api_router.include_router(realtime.router, prefix="/realtime", tags=["realtime"])


@api_router.post("/qr_code", response_model=DeviceSchema, tags=["binding"])
async def qr_code_binding(
    body: DeviceBind,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return await devices.bind_device(db=db, bind_in=body, current_user=current_user)
