"""Receivers (odbiorniki) — state inference rules and the API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.enums import UserRole
from app.models.measurement import Measurement
from app.models.sensor import Sensor
from app.services.receiver_state import COOLING, DEFROST, IDLE, UNKNOWN, analyze, classify
from tests.conftest import auth_headers
from tests.helpers import make_object

NOW = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)


def trace(start: float, per_minute: float, minutes: int = 20, end: datetime = NOW):
    """One reading a minute for `minutes`, ending at `end`, changing linearly."""
    return [
        (end - timedelta(minutes=minutes - i), start + per_minute * i)
        for i in range(minutes + 1)
    ]


# --- state rules -------------------------------------------------------------

def test_cold_evaporator_is_cooling():
    assert classify(trace(-17, -0.1), trace(-28, 0), NOW) == COOLING


def test_evaporator_warmer_than_chamber_is_defrost():
    assert classify(trace(-19, 0.05), trace(-10, 1.0), NOW) == DEFROST


def test_freezer_evaporator_above_zero_is_defrost_even_if_chamber_warmer():
    # Chamber has already warmed to -1 but the heater keeps the coil above 0.
    assert classify(trace(-3, 0.1), trace(2, 0.3), NOW) == DEFROST


def test_evaporator_drifting_back_up_is_idle():
    # Compressor just stopped: coil still colder than the room but rising fast.
    assert classify(trace(-21, 0.05), trace(-30, 0.5), NOW) == IDLE


def test_evaporator_close_to_chamber_is_idle():
    assert classify(trace(4, 0.02), trace(3, 0.02), NOW) == IDLE


def test_without_evaporator_falling_chamber_is_cooling_else_idle():
    assert classify(trace(6, -0.1), None, NOW) == COOLING
    assert classify(trace(4, 0.05), None, NOW) == IDLE


def test_stale_or_sparse_data_is_unknown():
    assert classify(trace(4, 0, end=NOW - timedelta(minutes=30)), None, NOW) == UNKNOWN
    assert classify([(NOW, 4.0)], None, NOW) == UNKNOWN
    assert classify([], None, NOW) == UNKNOWN


def test_missing_evaporator_data_falls_back_to_chamber_trend():
    assert classify(trace(6, -0.1), [], NOW) == COOLING


def series(values, end: datetime = NOW):
    """One reading a minute ending at `end` — real traces copied from the
    Biskupiec controllers on 2026-10-10."""
    return [(end - timedelta(minutes=len(values) - 1 - i), v) for i, v in enumerate(values)]


def test_freezer_with_a_small_evaporator_gap_is_cooling():
    # Running compressor, but the coil reads only ~1.5 °C below the air.
    chamber = series([-20.2, -20.4, -20.7, -20.9, -21.1, -21.4, -21.5])
    evaporator = series([-21.2, -21.7, -22.1, -22.4, -22.6, -22.7, -23.0])
    assert classify(chamber, evaporator, NOW, cut_in=-19.9) == COOLING


def test_freezer_coil_drifting_up_after_cooling_is_idle():
    chamber = series([-22.1, -21.8, -21.6, -21.4, -21.2, -20.9, -20.7])
    evaporator = series([-23.8, -23.9, -23.5, -23.0, -22.5, -21.9, -21.4])
    assert classify(chamber, evaporator, NOW, cut_in=-19.9) == IDLE


def test_freezer_right_after_defrost_is_cooling():
    # The 22:13 case: the window still holds the defrost rise, but the coil
    # is plunging and the chamber follows.
    chamber = series([-2.1, 0.7, 0.5, 1.7, 0.8, -0.4, -2.1])
    evaporator = series([-2.5, 1.3, -1.5, -1.4, -1.8, -3.0, -5.6])
    assert classify(chamber, evaporator, NOW, cut_in=-19.9) == COOLING


def test_freezer_warming_far_above_cut_in_is_defrost():
    # No heater signature on the coil, but the air is 8 °C over the cut-in
    # and nothing is cooling it.
    chamber = series([-18.3, -14.1, -11.7, -7.6, -4.9, -3.3, -2.1])
    evaporator = series([-17.5, -13.8, -10.3, -8.9, -5.4, -3.4, -2.5])
    assert classify(chamber, evaporator, NOW, cut_in=-19.9) == DEFROST


def test_cold_room_coil_reading_warm_at_rest_is_idle():
    # A resting coil sensor ~1.2 °C above the air is not a defrost.
    chamber = series([5.0, 5.0, 5.1, 5.1, 5.1, 5.1, 5.2])
    evaporator = series([6.1, 6.1, 6.2, 6.2, 6.3, 6.3, 6.4])
    assert classify(chamber, evaporator, NOW, cut_in=6.0) == IDLE


def test_cold_room_heater_defrost():
    chamber = series([3.9, 4.0, 4.1, 4.1, 4.2, 4.3, 4.3])
    evaporator = series([-1.4, 2.6, 21.4, 32.4, 32.8, 30.8, 28.5])
    assert classify(chamber, evaporator, NOW, cut_in=6.0) == DEFROST


def test_cooling_ends_as_soon_as_the_coil_warms():
    # Chamber trend still falling from the last cycle, coil already rising.
    chamber = series([4.2, 4.0, 3.7, 3.5, 3.5, 3.5, 3.7])
    evaporator = series([-8.0, -8.5, -8.8, -13.1, -8.4, -2.4, -1.6])
    assert classify(chamber, evaporator, NOW, cut_in=6.0) == IDLE


def test_time_to_target_follows_the_cooling_rate():
    # -15 °C falling 0.25 °C/min towards -20 °C → 20 min.
    result = analyze(trace(-10, -0.25), trace(-28, 0), NOW, target=-20)
    assert result.state == COOLING
    assert result.minutes_to_target == pytest.approx(20, abs=0.5)
    assert result.chamber_rate == pytest.approx(-0.25, abs=0.01)


def test_no_estimate_when_idle_or_already_there():
    assert analyze(trace(4, 0.02), trace(3, 0.02), NOW, target=2).minutes_to_target is None
    assert analyze(trace(-19, -0.1), trace(-28, 0), NOW, target=-25).minutes_to_target is not None
    assert analyze(trace(-21, -0.1), trace(-28, 0), NOW, target=-20).minutes_to_target is None


def test_state_since_finds_when_cooling_started():
    # Idle for an hour (coil close to the room), then cooling for the last 18 min.
    start = NOW - timedelta(minutes=80)
    chamber, evaporator = [], []
    for i in range(81):
        t = start + timedelta(minutes=i)
        cooling = i >= 62
        chamber.append((t, -18 - (0.1 * (i - 62) if cooling else 0)))
        evaporator.append((t, -28.0 if cooling else -19.0))
    result = analyze(chamber, evaporator, NOW)
    assert result.state == COOLING
    assert NOW - result.state_since == pytest.approx(timedelta(minutes=18), abs=timedelta(minutes=3))


def freezer_cycles(minutes: int, end: datetime = NOW):
    """A freezer cycling every 25 min like the Biskupiec one: 12 min cooling
    from -19.9 to -22.1, then 13 min idle drifting back up. Ends `minutes`
    into a cycle. One reading a minute, chamber and evaporator."""
    chamber, evaporator = [], []
    total = 6 * 60 + 25 + minutes
    for i in range(total + 1):
        t = end - timedelta(minutes=total - i)
        k = (i - (total - minutes)) % 25
        if k < 12:  # cooling
            chamber.append((t, -19.9 - 2.2 * k / 12))
            evaporator.append((t, -21.5 - 2.4 * k / 12))
        else:  # idle
            chamber.append((t, -22.1 + 2.2 * (k - 12) / 13))
            evaporator.append((t, -23.9 + 4.0 * (k - 12) / 13))
    return chamber, evaporator


def test_stopwatches_while_cooling_show_the_last_idle():
    chamber, evaporator = freezer_cycles(8)
    result = analyze(chamber, evaporator, NOW, target=-22.1, cut_in=-19.9)
    assert result.cycle_phase == "cooling"
    assert result.cooling_seconds == pytest.approx(8 * 60, abs=90)
    assert result.idle_seconds == pytest.approx(13 * 60, abs=90)


def test_stopwatches_while_idle_show_the_last_cooling():
    chamber, evaporator = freezer_cycles(18)
    result = analyze(chamber, evaporator, NOW, target=-22.1, cut_in=-19.9)
    assert result.cycle_phase == "idle"
    assert result.idle_seconds == pytest.approx(6 * 60, abs=90)
    assert result.cooling_seconds == pytest.approx(12 * 60, abs=90)


def test_reaching_the_cut_out_switches_to_idle_at_once():
    # The first reading at -22.1: the controller has just stopped the
    # compressor, even though the coil is still cold and the trend lags.
    chamber, evaporator = freezer_cycles(12)
    result = analyze(chamber, evaporator, NOW, target=-22.1, cut_in=-19.9)
    assert result.cycle_phase == "idle"
    assert result.idle_seconds is not None and result.idle_seconds < 90


def test_compressor_start_delay_does_not_break_the_cooling_phase():
    # At the cut-in the air stays flat for two minutes before it falls.
    chamber = series([-20.6, -20.3, -20.1, -19.9, -19.9, -19.9, -20.0, -20.2, -20.4, -20.6])
    evaporator = series([-21.0, -20.8, -20.6, -20.4, -20.4, -20.6, -21.2, -21.8, -22.2, -22.6])
    result = analyze(chamber, evaporator, NOW, target=-22.1, cut_in=-19.9)
    assert result.cycle_phase == "cooling"
    assert result.cooling_seconds == pytest.approx(6 * 60, abs=60)


def test_no_stopwatch_without_a_phase_change_in_view():
    flat = trace(4, 0.0, minutes=60)
    result = analyze(flat, trace(3.8, 0.0, minutes=60), NOW)
    assert result.cycle_phase == "idle"
    assert result.cooling_seconds is None and result.idle_seconds is None


# --- API ---------------------------------------------------------------------

async def _sensor(db, obj, name: str, kind: str = "temperature", temperature: float | None = None) -> Sensor:
    sensor = Sensor(
        object_id=obj.id, name=name, mqtt_topic=f"frigo/t/{name}", kind=kind,
        current_temperature=temperature, last_message_at=datetime.now(timezone.utc),
    )
    db.add(sensor)
    await db.commit()
    await db.refresh(sensor)
    return sensor


async def _readings(db, sensor: Sensor, points) -> None:
    db.add_all(Measurement(sensor_id=sensor.id, temperature=v, received_at=t) for t, v in points)
    await db.commit()


async def _assign(db, user, obj) -> None:
    await db.refresh(user, attribute_names=["objects"])
    user.objects.append(obj)
    await db.commit()


@pytest.mark.asyncio
async def test_admin_creates_receiver_and_owner_sees_its_live_state(client, db_session, make_user):
    admin, owner = await make_user(UserRole.ADMIN), await make_user(UserRole.USER)
    obj = await make_object(db_session)
    await _assign(db_session, owner, obj)
    chamber = await _sensor(db_session, obj, "komora", temperature=-15.0)
    evaporator = await _sensor(db_session, obj, "parownik", temperature=-28.0)
    now = datetime.now(timezone.utc)
    await _readings(db_session, chamber, trace(-10, -0.25, end=now))
    await _readings(db_session, evaporator, trace(-28, 0, end=now))

    resp = await client.post(
        f"/api/v1/objects/{obj.id}/receivers",
        json={"name": "Mroźnia", "chamber_sensor_id": str(chamber.id), "evaporator_sensor_id": str(evaporator.id),
              "cut_in": -18, "cut_out": -20},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get(f"/api/v1/objects/{obj.id}/receivers", headers=auth_headers(owner))
    assert resp.status_code == 200
    [receiver] = resp.json()
    assert receiver["name"] == "Mroźnia"
    assert receiver["state"] == "cooling"
    assert receiver["chamber_temperature"] == -15.0
    assert receiver["evaporator_temperature"] == -28.0
    # Time left is counted to the cut-out, where cooling stops.
    assert receiver["minutes_to_cut_out"] == pytest.approx(20, abs=1)


@pytest.mark.asyncio
async def test_owner_cannot_configure_or_see_other_objects(client, db_session, make_user):
    owner = await make_user(UserRole.USER)
    obj = await make_object(db_session)
    resp = await client.post(
        f"/api/v1/objects/{obj.id}/receivers", json={"name": "X"}, headers=auth_headers(owner)
    )
    assert resp.status_code == 403
    resp = await client.get(f"/api/v1/objects/{obj.id}/receivers", headers=auth_headers(owner))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_receiver_validation(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj, other = await make_object(db_session), await make_object(db_session, "Inny")
    komora = await _sensor(db_session, obj, "komora")
    prad = await _sensor(db_session, obj, "prad", kind="current")
    obcy = await _sensor(db_session, other, "obcy")
    url, headers = f"/api/v1/objects/{obj.id}/receivers", auth_headers(admin)

    for body in (
        {"name": "A", "chamber_sensor_id": str(prad.id)},
        {"name": "A", "chamber_sensor_id": str(obcy.id)},
        {"name": "A", "chamber_sensor_id": str(komora.id), "evaporator_sensor_id": str(komora.id)},
        {"name": "A", "cut_in": -22, "cut_out": -18},
    ):
        assert (await client.post(url, json=body, headers=headers)).status_code == 400, body

    created = await client.post(url, json={"name": "A", "cut_in": -18, "cut_out": -22}, headers=headers)
    assert created.status_code == 201
    rid = created.json()["id"]
    # A patch is checked against the merged result, not just the fields sent.
    resp = await client.patch(f"{url}/{rid}", json={"cut_out": -10}, headers=headers)
    assert resp.status_code == 400
    resp = await client.patch(f"{url}/{rid}", json={"name": "B", "cut_in": -15}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "B"
    assert resp.json()["state"] == "unknown"


@pytest.mark.asyncio
async def test_deleting_a_sensor_keeps_the_receiver(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    komora = await _sensor(db_session, obj, "komora")
    headers = auth_headers(admin)
    await client.post(
        f"/api/v1/objects/{obj.id}/receivers",
        json={"name": "Chłodnia", "chamber_sensor_id": str(komora.id)}, headers=headers,
    )
    assert (await client.delete(f"/api/v1/objects/{obj.id}/sensors/{komora.id}", headers=headers)).status_code == 200
    [receiver] = (await client.get(f"/api/v1/objects/{obj.id}/receivers", headers=headers)).json()
    assert receiver["chamber_sensor_id"] is None
    assert receiver["state"] == "unknown"
