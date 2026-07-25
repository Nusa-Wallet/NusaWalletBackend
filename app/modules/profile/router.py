from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.models import Device, NotificationPref, User

router = APIRouter(prefix="/profile", tags=["profile"])


# ── Device endpoints ──

class DeviceResponse(BaseModel):
    id: int
    name: str
    os: str
    last_active: str
    is_current: bool

    model_config = {"from_attributes": True}


@router.get("/devices", response_model=list[DeviceResponse])
def list_devices(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    devices = db.query(Device).filter(Device.user_id == current.id).order_by(Device.last_active.desc()).all()
    if not devices:
        return []
    return devices


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_device(
    device_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.id == device_id, Device.user_id == current.id).first()
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    db.delete(device)
    db.commit()


# ── Notification preference endpoints ──

class NotificationPrefResponse(BaseModel):
    key: str
    push: bool
    email: bool


class NotificationPrefsUpdate(BaseModel):
    push: bool | None = None
    email: bool | None = None


@router.get("/notifications", response_model=list[NotificationPrefResponse])
def list_notification_prefs(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prefs = db.query(NotificationPref).filter(NotificationPref.user_id == current.id).all()
    return prefs


@router.put("/notifications/{key}", response_model=NotificationPrefResponse)
def update_notification_pref(
    key: str,
    payload: NotificationPrefsUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pref = db.query(NotificationPref).filter(
        NotificationPref.user_id == current.id,
        NotificationPref.key == key,
    ).first()
    if not pref:
        pref = NotificationPref(user_id=current.id, key=key)
        db.add(pref)
    if payload.push is not None:
        pref.push = payload.push
    if payload.email is not None:
        pref.email = payload.email
    db.commit()
    db.refresh(pref)
    return pref
