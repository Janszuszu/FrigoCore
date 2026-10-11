"""Meters (liczniki) — consumption periods and the API."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.enums import UserRole
from app.models.measurement import Measurement
from app.models.sensor import Sensor
from app.services.energy import ENERGY_TIMEZONE, combine, period_start, summarize
from tests.conftest import auth_headers
from tests.helpers import make_object

# Wednesday 2026-10-07: the week began on Monday the 5th (inside October),
# so "this month" reaches further back than "this week".
WEDNESDAY = date(2026, 10, 7)


def test_periods_count_from_monday_and_from_the_first():
    days = {
        date(2026, 9, 30): 9.0,  # last month — not counted
        date(2026, 10, 1): 1.0,
        date(2026, 10, 4): 2.0,  # Sunday of the previous week
        date(2026, 10, 5): 3.0,
        date(2026, 10, 7): 4.5,
    }
    used = summarize(days, WEDNESDAY)
    assert used.today_kwh == 4.5
    assert used.week_kwh == 7.5
    assert used.month_kwh == 10.5


def test_week_spanning_two_months_starts_at_monday():
    # Thursday 1 October: the week began on Monday 28 September.
    assert period_start(date(2026, 10, 1)) == date(2026, 9, 28)
    assert period_start(WEDNESDAY) == date(2026, 10, 1)
    used = summarize({date(2026, 9, 28): 2.0, date(2026, 10, 1): 1.0}, date(2026, 10, 1))
    assert used.week_kwh == 3.0
    assert used.month_kwh == 1.0


def test_periods_without_data_are_null():
    used = summarize({}, WEDNESDAY)
    assert (used.today_kwh, used.week_kwh, used.month_kwh) == (None, None, None)


def test_meters_add_up_day_by_day():
    a = summarize({date(2026, 10, 6): 1.0, date(2026, 10, 7): 2.0}, WEDNESDAY)
    b = summarize({date(2026, 10, 7): 0.5}, WEDNESDAY)
    total = combine([a, b], WEDNESDAY)
    assert total.days == {date(2026, 10, 6): 1.0, date(2026, 10, 7): 2.5}
    assert total.today_kwh == 2.5
    assert total.week_kwh == 3.5


# --- API ---------------------------------------------------------------------

def _local(day_offset: int, hour: int) -> datetime:
    day = datetime.now(ENERGY_TIMEZONE).date() + timedelta(days=day_offset)
    return datetime.combine(day, time(hour), ENERGY_TIMEZONE).astimezone(timezone.utc)


async def _sensor(db, obj, name: str, kind: str, value: float | None = None, readings=()) -> Sensor:
    sensor = Sensor(
        name=name, object_id=obj.id, mqtt_topic=f"frigo/t/{uuid.uuid4()}", kind=kind,
        current_temperature=value, last_message_at=datetime.now(timezone.utc),
    )
    db.add(sensor)
    await db.flush()
    for at, v in readings:
        db.add(Measurement(sensor_id=sensor.id, temperature=v, received_at=at))
    await db.commit()
    await db.refresh(sensor)
    return sensor


async def _assign(db, user, obj) -> None:
    await db.refresh(user, attribute_names=["objects"])
    user.objects.append(obj)
    await db.commit()


@pytest.mark.asyncio
async def test_owner_sees_meter_readings_and_consumption(client, db_session, make_user):
    admin, owner = await make_user(UserRole.ADMIN), await make_user(UserRole.USER)
    obj = await make_object(db_session)
    await _assign(db_session, owner, obj)
    energy = await _sensor(db_session, obj, "energia", "energy", 342.5, [
        (_local(0, 0), 340.0), (_local(0, 1), 342.5),  # 2.5 kWh today
    ])
    power = await _sensor(db_session, obj, "moc", "power", 1450.0)
    voltage = await _sensor(db_session, obj, "napiecie", "voltage", 231.0)

    resp = await client.post(
        f"/api/v1/objects/{obj.id}/meters",
        json={"name": "Licznik główny", "energy_sensor_id": str(energy.id),
              "power_sensor_id": str(power.id), "voltage_sensor_id": str(voltage.id)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get(f"/api/v1/objects/{obj.id}/meters", headers=auth_headers(owner))
    assert resp.status_code == 200
    [meter] = resp.json()
    assert meter["name"] == "Licznik główny"
    assert meter["total_kwh"] == 342.5
    assert meter["power_w"] == 1450.0
    assert meter["voltage_v"] == 231.0
    assert meter["current_a"] is None
    used = meter["consumption"]
    assert used["today_kwh"] == 2.5
    assert used["week_kwh"] >= 2.5 and used["month_kwh"] >= 2.5
    assert used["days"][-1] == {"day": _local(0, 12).astimezone(ENERGY_TIMEZONE).date().isoformat(), "kwh": 2.5}


@pytest.mark.asyncio
async def test_total_adds_up_active_meters(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    headers, url = auth_headers(admin), f"/api/v1/objects/{obj.id}/meters"
    for name, start, end, watts in (("A", 100.0, 101.0, 500.0), ("B", 50.0, 53.0, 700.0)):
        energy = await _sensor(db_session, obj, f"{name}-e", "energy", end, [(_local(0, 0), start), (_local(0, 1), end)])
        power = await _sensor(db_session, obj, f"{name}-p", "power", watts)
        body = {"name": name, "energy_sensor_id": str(energy.id), "power_sensor_id": str(power.id)}
        assert (await client.post(url, json=body, headers=headers)).status_code == 201
    hidden = await _sensor(db_session, obj, "C-e", "energy", 9.0, [(_local(0, 0), 1.0), (_local(0, 1), 9.0)])
    await client.post(url, json={"name": "C", "energy_sensor_id": str(hidden.id), "is_active": False}, headers=headers)

    total = (await client.get(f"{url}/total", headers=headers)).json()
    assert total["meter_count"] == 2
    assert total["total_kwh"] == 154.0
    assert total["power_w"] == 1200.0
    assert total["consumption"]["today_kwh"] == 4.0


@pytest.mark.asyncio
async def test_owner_cannot_configure_or_see_other_objects(client, db_session, make_user):
    owner = await make_user(UserRole.USER)
    obj = await make_object(db_session)
    url = f"/api/v1/objects/{obj.id}/meters"
    assert (await client.post(url, json={"name": "X"}, headers=auth_headers(owner))).status_code == 403
    assert (await client.get(url, headers=auth_headers(owner))).status_code == 404
    assert (await client.get(f"{url}/total", headers=auth_headers(owner))).status_code == 404


@pytest.mark.asyncio
async def test_meter_validation_and_sensor_removal(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj, other = await make_object(db_session), await make_object(db_session, "Inny")
    energy = await _sensor(db_session, obj, "energia", "energy", 10.0)
    temp = await _sensor(db_session, obj, "komora", "temperature", 3.0)
    foreign = await _sensor(db_session, other, "obca", "energy", 1.0)
    url, headers = f"/api/v1/objects/{obj.id}/meters", auth_headers(admin)

    for body in (
        {"name": "X", "energy_sensor_id": str(temp.id)},
        {"name": "X", "energy_sensor_id": str(foreign.id)},
        {"name": "X", "power_sensor_id": str(energy.id)},
    ):
        assert (await client.post(url, json=body, headers=headers)).status_code == 400, body

    created = (await client.post(url, json={"name": "X", "energy_sensor_id": str(energy.id)}, headers=headers)).json()
    resp = await client.patch(f"{url}/{created['id']}", json={"voltage_sensor_id": str(temp.id)}, headers=headers)
    assert resp.status_code == 400

    assert (await client.delete(f"/api/v1/objects/{obj.id}/sensors/{energy.id}", headers=headers)).status_code == 200
    [meter] = (await client.get(url, headers=headers)).json()
    assert meter["energy_sensor_id"] is None
    assert meter["consumption"]["today_kwh"] is None

    assert (await client.delete(f"{url}/{meter['id']}", headers=headers)).status_code == 200
    assert (await client.get(url, headers=headers)).json() == []
