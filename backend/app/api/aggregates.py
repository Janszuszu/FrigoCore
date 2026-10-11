"""FrigoCore — Aggregates (agregaty) API.

Everyone who can see an object can list its aggregates; only an
administrator configures them (nameplate data, which sensors) — from the
web panel. Readings come from the regular sensor endpoints: an aggregate
only says which of the object's sensors belong to it and in what order.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.api.routes import _check_object_visible
from app.database import get_db
from app.models.aggregate import Aggregate, AggregateSensor
from app.models.object import Object
from app.models.sensor import Sensor
from app.models.user import User
from app.schemas import AggregateCreate, AggregateResponse, AggregateUpdate

aggregates_router = APIRouter()


async def _set_sensors(db: AsyncSession, object_id: UUID, aggregate: Aggregate, sensor_ids: list[UUID]) -> None:
    """Replace the aggregate's sensors, keeping the given order. Every one
    must belong to the aggregate's object."""
    if len(set(sensor_ids)) != len(sensor_ids):
        raise HTTPException(status_code=400, detail="A sensor can appear only once in an aggregate")
    if sensor_ids:
        found = set(
            (await db.execute(
                select(Sensor.id).where(Sensor.id.in_(sensor_ids), Sensor.object_id == object_id)
            )).scalars().all()
        )
        if found != set(sensor_ids):
            raise HTTPException(status_code=400, detail="Sensor does not belong to this object")
    # Reuse the rows that stay so no (aggregate, sensor) key is deleted and
    # re-inserted within the same flush.
    existing = {link.sensor_id: link for link in aggregate.sensor_links}
    links = []
    for position, sensor_id in enumerate(sensor_ids):
        link = existing.get(sensor_id) or AggregateSensor(sensor_id=sensor_id)
        link.position = position
        links.append(link)
    aggregate.sensor_links = links


async def _aggregate_or_404(db: AsyncSession, object_id: UUID, aggregate_id: UUID) -> Aggregate:
    aggregate = await db.get(Aggregate, aggregate_id)
    if aggregate is None or aggregate.object_id != object_id:
        raise HTTPException(status_code=404, detail="Aggregate not found")
    return aggregate


async def _saved(db: AsyncSession, aggregate: Aggregate) -> AggregateResponse:
    await db.commit()
    await db.refresh(aggregate, ["sensor_links"])
    return AggregateResponse.model_validate(aggregate)


@aggregates_router.get("/{object_id}/aggregates", response_model=list[AggregateResponse])
async def list_aggregates(
    object_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[AggregateResponse]:
    _check_object_visible(object_id, user)
    if await db.get(Object, object_id) is None:
        raise HTTPException(status_code=404, detail="Object not found")
    result = await db.execute(
        select(Aggregate).where(Aggregate.object_id == object_id).order_by(Aggregate.display_order, Aggregate.name)
    )
    return [AggregateResponse.model_validate(a) for a in result.scalars().all()]


@aggregates_router.post(
    "/{object_id}/aggregates", response_model=AggregateResponse, status_code=status.HTTP_201_CREATED
)
async def create_aggregate(
    object_id: UUID, body: AggregateCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> AggregateResponse:
    if await db.get(Object, object_id) is None:
        raise HTTPException(status_code=404, detail="Object not found")
    highest = await db.scalar(select(func.max(Aggregate.display_order)).where(Aggregate.object_id == object_id))
    aggregate = Aggregate(
        object_id=object_id,
        display_order=0 if highest is None else highest + 1,
        sensor_links=[],
        **body.model_dump(exclude={"sensor_ids"}),
    )
    await _set_sensors(db, object_id, aggregate, body.sensor_ids)
    db.add(aggregate)
    return await _saved(db, aggregate)


@aggregates_router.patch("/{object_id}/aggregates/{aggregate_id}", response_model=AggregateResponse)
async def update_aggregate(
    object_id: UUID,
    aggregate_id: UUID,
    body: AggregateUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AggregateResponse:
    aggregate = await _aggregate_or_404(db, object_id, aggregate_id)
    changes = body.model_dump(exclude_unset=True)
    sensor_ids = changes.pop("sensor_ids", None)
    for field, value in changes.items():
        setattr(aggregate, field, value)
    if sensor_ids is not None:
        await _set_sensors(db, object_id, aggregate, sensor_ids)
    return await _saved(db, aggregate)


@aggregates_router.delete("/{object_id}/aggregates/{aggregate_id}")
async def delete_aggregate(
    object_id: UUID, aggregate_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> dict:
    aggregate = await _aggregate_or_404(db, object_id, aggregate_id)
    await db.delete(aggregate)
    await db.commit()
    return {"status": "deleted"}
