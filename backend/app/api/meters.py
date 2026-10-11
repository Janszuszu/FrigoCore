"""FrigoCore — Meters (liczniki) API.

Everyone who can see an object can list its meters with the live readings
and the electricity used; only an administrator configures them — from the
web panel. With several meters, /meters/total adds them all up.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.api.routes import _check_object_visible
from app.database import get_db
from app.models.meter import Meter
from app.models.object import Object
from app.models.sensor import Sensor
from app.models.user import User
from app.schemas import (
    ConsumptionResponse,
    EnergyDayResponse,
    MeterCreate,
    MeterResponse,
    MeterTotalResponse,
    MeterUpdate,
)
from app.sensor_kinds import SensorKind
from app.services.energy import Consumption, combine, consumption, local_today, summarize

meters_router = APIRouter()

# Which kind each sensor slot accepts.
SLOT_KINDS = {
    "energy_sensor_id": SensorKind.ENERGY,
    "power_sensor_id": SensorKind.POWER,
    "current_sensor_id": SensorKind.CURRENT,
    "voltage_sensor_id": SensorKind.VOLTAGE,
}


def _reading(sensor: Sensor | None) -> float | None:
    return sensor.current_temperature if sensor else None


def _consumption_response(c: Consumption) -> ConsumptionResponse:
    return ConsumptionResponse(
        today_kwh=c.today_kwh,
        week_kwh=c.week_kwh,
        month_kwh=c.month_kwh,
        days=[EnergyDayResponse(day=day, kwh=kwh) for day, kwh in sorted(c.days.items())],
    )


async def _consumption(db: AsyncSession, meter: Meter, today: date) -> Consumption:
    if meter.energy_sensor_id is None:
        return summarize({}, today)
    return await consumption(db, meter.energy_sensor_id, today)


def _response(meter: Meter, used: Consumption) -> MeterResponse:
    return MeterResponse(
        id=meter.id,
        name=meter.name,
        object_id=meter.object_id,
        energy_sensor_id=meter.energy_sensor_id,
        power_sensor_id=meter.power_sensor_id,
        current_sensor_id=meter.current_sensor_id,
        voltage_sensor_id=meter.voltage_sensor_id,
        display_order=meter.display_order,
        is_active=meter.is_active,
        total_kwh=_reading(meter.energy_sensor),
        power_w=_reading(meter.power_sensor),
        current_a=_reading(meter.current_sensor),
        voltage_v=_reading(meter.voltage_sensor),
        last_message_at=meter.energy_sensor.last_message_at if meter.energy_sensor else None,
        consumption=_consumption_response(used),
    )


async def _validate(db: AsyncSession, object_id: UUID, meter: Meter) -> None:
    """Every sensor must belong to the object and measure what its slot says."""
    for slot, kind in SLOT_KINDS.items():
        sensor_id = getattr(meter, slot)
        if sensor_id is None:
            continue
        sensor = await db.get(Sensor, sensor_id)
        if sensor is None or sensor.object_id != object_id:
            raise HTTPException(status_code=400, detail="Sensor does not belong to this object")
        if sensor.kind != kind.value:
            raise HTTPException(status_code=400, detail=f"{slot} must be a {kind.value} sensor")


async def _meter_or_404(db: AsyncSession, object_id: UUID, meter_id: UUID) -> Meter:
    meter = await db.get(Meter, meter_id)
    if meter is None or meter.object_id != object_id:
        raise HTTPException(status_code=404, detail="Meter not found")
    return meter


async def _visible_meters(db: AsyncSession, object_id: UUID, user: User) -> list[Meter]:
    _check_object_visible(object_id, user)
    if await db.get(Object, object_id) is None:
        raise HTTPException(status_code=404, detail="Object not found")
    result = await db.execute(
        select(Meter).where(Meter.object_id == object_id).order_by(Meter.display_order, Meter.name)
    )
    return list(result.scalars().all())


async def _saved(db: AsyncSession, meter: Meter) -> MeterResponse:
    await db.commit()
    await db.refresh(meter, ["energy_sensor", "power_sensor", "current_sensor", "voltage_sensor"])
    today = local_today()
    return _response(meter, await _consumption(db, meter, today))


@meters_router.get("/{object_id}/meters", response_model=list[MeterResponse])
async def list_meters(
    object_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[MeterResponse]:
    today = local_today()
    return [_response(m, await _consumption(db, m, today)) for m in await _visible_meters(db, object_id, user)]


@meters_router.get("/{object_id}/meters/total", response_model=MeterTotalResponse)
async def meters_total(
    object_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> MeterTotalResponse:
    """The object's active meters added up: counters, power and every day's use."""
    meters = [m for m in await _visible_meters(db, object_id, user) if m.is_active]
    today = local_today()
    parts = [await _consumption(db, m, today) for m in meters]

    def added(values: list[float | None]) -> float | None:
        present = [v for v in values if v is not None]
        return round(sum(present), 3) if present else None

    return MeterTotalResponse(
        meter_count=len(meters),
        total_kwh=added([_reading(m.energy_sensor) for m in meters]),
        power_w=added([_reading(m.power_sensor) for m in meters]),
        consumption=_consumption_response(combine(parts, today)),
    )


@meters_router.post("/{object_id}/meters", response_model=MeterResponse, status_code=status.HTTP_201_CREATED)
async def create_meter(
    object_id: UUID, body: MeterCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> MeterResponse:
    if await db.get(Object, object_id) is None:
        raise HTTPException(status_code=404, detail="Object not found")
    highest = await db.scalar(select(func.max(Meter.display_order)).where(Meter.object_id == object_id))
    meter = Meter(object_id=object_id, display_order=0 if highest is None else highest + 1, **body.model_dump())
    await _validate(db, object_id, meter)
    db.add(meter)
    return await _saved(db, meter)


@meters_router.patch("/{object_id}/meters/{meter_id}", response_model=MeterResponse)
async def update_meter(
    object_id: UUID,
    meter_id: UUID,
    body: MeterUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MeterResponse:
    meter = await _meter_or_404(db, object_id, meter_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(meter, field, value)
    await _validate(db, object_id, meter)
    return await _saved(db, meter)


@meters_router.delete("/{object_id}/meters/{meter_id}")
async def delete_meter(
    object_id: UUID, meter_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> dict:
    meter = await _meter_or_404(db, object_id, meter_id)
    await db.delete(meter)
    await db.commit()
    return {"status": "deleted"}
