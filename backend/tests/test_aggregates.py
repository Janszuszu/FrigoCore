"""Aggregates (agregaty) — nameplate data plus an ordered group of sensors."""

from __future__ import annotations

import pytest

from app.enums import UserRole
from app.models.sensor import Sensor
from tests.conftest import auth_headers
from tests.helpers import make_object


async def _sensor(db, obj, name: str, kind: str = "temperature") -> Sensor:
    sensor = Sensor(name=name, object_id=obj.id, mqtt_topic=f"frigo/{obj.id}/{name}", kind=kind)
    db.add(sensor)
    await db.commit()
    await db.refresh(sensor)
    return sensor


async def _assign(db, user, obj) -> None:
    await db.refresh(user, attribute_names=["objects"])
    user.objects.append(obj)
    await db.commit()


@pytest.mark.asyncio
async def test_admin_creates_aggregate_and_owner_sees_it(client, db_session, make_user):
    admin, owner = await make_user(UserRole.ADMIN), await make_user(UserRole.USER)
    obj = await make_object(db_session)
    await _assign(db_session, owner, obj)
    outdoor = await _sensor(db_session, obj, "zewnetrzna")
    discharge = await _sensor(db_session, obj, "tloczenie")

    resp = await client.post(
        f"/api/v1/objects/{obj.id}/aggregates",
        json={"name": "Agregat mroźni", "compressor_model": "Bitzer 4FES-5Y", "refrigerant": "R404A",
              "refrigerant_charge_kg": 6.5, "installed_on": "2019-05-14",
              "sensor_ids": [str(discharge.id), str(outdoor.id)]},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get(f"/api/v1/objects/{obj.id}/aggregates", headers=auth_headers(owner))
    assert resp.status_code == 200
    [aggregate] = resp.json()
    assert aggregate["name"] == "Agregat mroźni"
    assert aggregate["compressor_model"] == "Bitzer 4FES-5Y"
    assert aggregate["refrigerant"] == "R404A"
    assert aggregate["refrigerant_charge_kg"] == 6.5
    assert aggregate["installed_on"] == "2019-05-14"
    # The technician's order is kept.
    assert aggregate["sensor_ids"] == [str(discharge.id), str(outdoor.id)]


@pytest.mark.asyncio
async def test_owner_cannot_configure_or_see_other_objects(client, db_session, make_user):
    owner = await make_user(UserRole.USER)
    obj = await make_object(db_session)
    url = f"/api/v1/objects/{obj.id}/aggregates"
    assert (await client.post(url, json={"name": "X"}, headers=auth_headers(owner))).status_code == 403
    assert (await client.get(url, headers=auth_headers(owner))).status_code == 404


@pytest.mark.asyncio
async def test_one_sensor_may_serve_several_aggregates(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    outdoor = await _sensor(db_session, obj, "zewnetrzna")
    url, headers = f"/api/v1/objects/{obj.id}/aggregates", auth_headers(admin)
    for name in ("A1", "A2"):
        resp = await client.post(url, json={"name": name, "sensor_ids": [str(outdoor.id)]}, headers=headers)
        assert resp.status_code == 201, resp.text
    listed = (await client.get(url, headers=headers)).json()
    assert [a["name"] for a in listed] == ["A1", "A2"]
    assert all(a["sensor_ids"] == [str(outdoor.id)] for a in listed)


@pytest.mark.asyncio
async def test_aggregate_validation_and_reordering(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj, other = await make_object(db_session), await make_object(db_session, "Inny")
    a, b, c = [await _sensor(db_session, obj, n) for n in ("a", "b", "c")]
    prad = await _sensor(db_session, obj, "prad", kind="current")
    obcy = await _sensor(db_session, other, "obcy")
    url, headers = f"/api/v1/objects/{obj.id}/aggregates", auth_headers(admin)

    for body in (
        {"name": "X", "sensor_ids": [str(obcy.id)]},
        {"name": "X", "sensor_ids": [str(a.id), str(a.id)]},
        {"name": "X", "refrigerant_charge_kg": -1},
        {"name": ""},
    ):
        assert (await client.post(url, json=body, headers=headers)).status_code in (400, 422), body

    created = await client.post(
        url, json={"name": "X", "sensor_ids": [str(a.id), str(b.id), str(prad.id)]}, headers=headers
    )
    assert created.status_code == 201
    aid = created.json()["id"]

    # Reorder, drop one and add one — the sensors kept must not clash.
    resp = await client.patch(f"{url}/{aid}", json={"sensor_ids": [str(c.id), str(b.id), str(a.id)]}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["sensor_ids"] == [str(c.id), str(b.id), str(a.id)]

    # Fields not sent stay as they were.
    resp = await client.patch(f"{url}/{aid}", json={"refrigerant": "R449A"}, headers=headers)
    assert resp.json()["sensor_ids"] == [str(c.id), str(b.id), str(a.id)]
    assert resp.json()["name"] == "X"

    assert (await client.patch(f"{url}/{aid}", json={"sensor_ids": [str(obcy.id)]}, headers=headers)).status_code == 400

    assert (await client.delete(f"{url}/{aid}", headers=headers)).status_code == 200
    assert (await client.get(url, headers=headers)).json() == []


@pytest.mark.asyncio
async def test_deleting_a_sensor_drops_it_from_the_aggregate(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    a, b = await _sensor(db_session, obj, "a"), await _sensor(db_session, obj, "b")
    url, headers = f"/api/v1/objects/{obj.id}/aggregates", auth_headers(admin)
    await client.post(url, json={"name": "X", "sensor_ids": [str(a.id), str(b.id)]}, headers=headers)
    assert (await client.delete(f"/api/v1/objects/{obj.id}/sensors/{a.id}", headers=headers)).status_code == 200
    [aggregate] = (await client.get(url, headers=headers)).json()
    assert aggregate["sensor_ids"] == [str(b.id)]
