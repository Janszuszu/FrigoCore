"""FrigoCore — Receivers (odbiorniki) API.

Everyone who can see an object can list its receivers with their live
state; only an administrator configures them (which sensors, which
working temperatures) — from the web panel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.api.routes import _check_object_visible
from app.database import get_db
from app.models.measurement import Measurement
from app.models.object import Object
from app.models.receiver import Receiver
from app.models.sensor import Sensor
from app.models.user import User
from app.schemas import ReceiverCreate, ReceiverResponse, ReceiverUpdate
from app.services.receiver_state import TIMELINE_LOOKBACK, WINDOW, Point, analyze

receivers_router = APIRouter()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite stores naive UTC


async def _history(db: AsyncSession, sensor_ids: set[UUID], now: datetime) -> dict[UUID, list[Point]]:
    """Oldest-first readings per sensor, enough for analyze() to also find
    when the current state began."""
    if not sensor_ids:
        return {}
    result = await db.execute(
        select(Measurement.sensor_id, Measurement.received_at, Measurement.temperature)
        .where(
            Measurement.sensor_id.in_(sensor_ids),
            Measurement.received_at >= now - TIMELINE_LOOKBACK - WINDOW,
        )
        .order_by(Measurement.received_at.asc())
    )
    history: dict[UUID, list[Point]] = {sid: [] for sid in sensor_ids}
    for sensor_id, received_at, temperature in result.all():
        history[sensor_id].append((_aware(received_at), temperature))
    return history


def _response(receiver: Receiver, history: dict[UUID, list[Point]], now: datetime) -> ReceiverResponse:
    chamber, evaporator = receiver.chamber_sensor, receiver.evaporator_sensor
    analysis = analyze(
        history.get(receiver.chamber_sensor_id, []) if chamber else [],
        history.get(receiver.evaporator_sensor_id) if evaporator else None,
        now,
        target=receiver.cut_out,
        cut_in=receiver.cut_in,
    )
    return ReceiverResponse(
        id=receiver.id,
        name=receiver.name,
        object_id=receiver.object_id,
        chamber_sensor_id=receiver.chamber_sensor_id,
        evaporator_sensor_id=receiver.evaporator_sensor_id,
        cut_in=receiver.cut_in,
        cut_out=receiver.cut_out,
        display_order=receiver.display_order,
        is_active=receiver.is_active,
        chamber_temperature=chamber.current_temperature if chamber else None,
        evaporator_temperature=evaporator.current_temperature if evaporator else None,
        last_message_at=chamber.last_message_at if chamber else None,
        state=analysis.state,
        state_since=analysis.state_since,
        minutes_to_cut_out=analysis.minutes_to_target,
        chamber_rate=analysis.chamber_rate,
        cycle_phase=analysis.cycle_phase,
        cooling_seconds=analysis.cooling_seconds,
        idle_seconds=analysis.idle_seconds,
    )


async def _responses(db: AsyncSession, receivers: list[Receiver]) -> list[ReceiverResponse]:
    now = datetime.now(timezone.utc)
    sensor_ids = {
        sid for r in receivers for sid in (r.chamber_sensor_id, r.evaporator_sensor_id) if sid is not None
    }
    history = await _history(db, sensor_ids, now)
    return [_response(r, history, now) for r in receivers]


async def _validate(db: AsyncSession, object_id: UUID, receiver: Receiver) -> None:
    """Both sensors must be temperature sensors of the same object, and
    cooling must stop below where it starts."""
    if receiver.chamber_sensor_id is not None and receiver.chamber_sensor_id == receiver.evaporator_sensor_id:
        raise HTTPException(status_code=400, detail="Chamber and evaporator must be different sensors")
    for sensor_id in (receiver.chamber_sensor_id, receiver.evaporator_sensor_id):
        if sensor_id is None:
            continue
        sensor = await db.get(Sensor, sensor_id)
        if sensor is None or sensor.object_id != object_id:
            raise HTTPException(status_code=400, detail="Sensor does not belong to this object")
        if sensor.kind != "temperature":
            raise HTTPException(status_code=400, detail="Receiver sensors must measure temperature")
    if receiver.cut_in is not None and receiver.cut_out is not None and receiver.cut_out >= receiver.cut_in:
        raise HTTPException(status_code=400, detail="Cut-out temperature must be below cut-in temperature")


async def _receiver_or_404(db: AsyncSession, object_id: UUID, receiver_id: UUID) -> Receiver:
    receiver = await db.get(Receiver, receiver_id)
    if receiver is None or receiver.object_id != object_id:
        raise HTTPException(status_code=404, detail="Receiver not found")
    return receiver


@receivers_router.get("/{object_id}/receivers", response_model=list[ReceiverResponse])
async def list_receivers(
    object_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ReceiverResponse]:
    _check_object_visible(object_id, user)
    if await db.get(Object, object_id) is None:
        raise HTTPException(status_code=404, detail="Object not found")
    result = await db.execute(
        select(Receiver).where(Receiver.object_id == object_id).order_by(Receiver.display_order, Receiver.name)
    )
    return await _responses(db, list(result.scalars().all()))


@receivers_router.post(
    "/{object_id}/receivers", response_model=ReceiverResponse, status_code=status.HTTP_201_CREATED
)
async def create_receiver(
    object_id: UUID, body: ReceiverCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> ReceiverResponse:
    if await db.get(Object, object_id) is None:
        raise HTTPException(status_code=404, detail="Object not found")
    highest = await db.scalar(select(func.max(Receiver.display_order)).where(Receiver.object_id == object_id))
    receiver = Receiver(object_id=object_id, display_order=0 if highest is None else highest + 1, **body.model_dump())
    await _validate(db, object_id, receiver)
    db.add(receiver)
    await db.commit()
    await db.refresh(receiver, ["chamber_sensor", "evaporator_sensor"])
    return (await _responses(db, [receiver]))[0]


@receivers_router.patch("/{object_id}/receivers/{receiver_id}", response_model=ReceiverResponse)
async def update_receiver(
    object_id: UUID,
    receiver_id: UUID,
    body: ReceiverUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ReceiverResponse:
    receiver = await _receiver_or_404(db, object_id, receiver_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(receiver, field, value)
    await _validate(db, object_id, receiver)
    await db.commit()
    await db.refresh(receiver, ["chamber_sensor", "evaporator_sensor"])
    return (await _responses(db, [receiver]))[0]


@receivers_router.delete("/{object_id}/receivers/{receiver_id}")
async def delete_receiver(
    object_id: UUID, receiver_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> dict:
    receiver = await _receiver_or_404(db, object_id, receiver_id)
    await db.delete(receiver)
    await db.commit()
    return {"status": "deleted"}
