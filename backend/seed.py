"""FrigoCore — Seed demo data for development.

Creates:
  - 3 monitored objects (shops)
  - 6 sensors (2 per object)
  - Alarm configs (HIGH, LOW, OFFLINE) for each sensor
  - Sample measurements with realistic temperatures
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from app.config import settings
from app.database import async_session_factory, engine, init_db
from app.models.object import Object
from app.models.sensor import Sensor
from app.models.alarm_config import AlarmConfig
from app.models.measurement import Measurement
from app.enums import AlarmType


async def seed() -> None:
    await init_db()

    async with async_session_factory() as session:
        # ── Objects ────────────────────────────────────────────
        objects = [
            Object(
                id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                name="Intermarche Szczytno",
                slug="intermarche-szczytno",
                description="Supermarket — regały chłodnicze, mroźnie",
                is_active=True,
            ),
            Object(
                id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                name="Biedronka Olsztyn",
                slug="biedronka-olsztyn",
                description="Dyskont spożywczy — lady chłodnicze",
                is_active=True,
            ),
            Object(
                id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
                name="Magazyn Centralny",
                slug="magazyn-centralny",
                description="Magazyn chłodniczy — duże komory mroźnicze",
                is_active=True,
            ),
        ]
        session.add_all(objects)
        await session.flush()

        # ── Sensors ────────────────────────────────────────────
        sensors_data = [
            # Intermarche Szczytno
            ("11111111-aaaa-1111-aaaa-111111111111", objects[0].id, "Komora chłodnicza A1", "komora-a1", 3.8, 60),
            ("11111111-bbbb-1111-bbbb-111111111111", objects[0].id, "Mroźnia B1", "mroznia-b1", -18.2, 60),
            # Biedronka Olsztyn
            ("22222222-aaaa-2222-aaaa-222222222222", objects[1].id, "Lada mięsna", "lada-miesna", 2.1, 90),
            ("22222222-bbbb-2222-bbbb-222222222222", objects[1].id, "Lada nabiałowa", "lada-nabialowa", 4.5, 90),
            # Magazyn Centralny
            ("33333333-aaaa-3333-aaaa-333333333333", objects[2].id, "Komora mroźnicza G1", "komora-g1", -22.0, 120),
            ("33333333-bbbb-3333-bbbb-333333333333", objects[2].id, "Komora chłodnicza G2", "komora-g2", 2.0, 120),
        ]

        sensors = []
        now = datetime.now(timezone.utc)
        for sid, oid, name, slug, temp, timeout in sensors_data:
            s = Sensor(
                id=uuid.UUID(sid),
                name=name,
                slug=slug,
                current_temperature=temp,
                last_message_at=now,
                offline_timeout_seconds=timeout,
                is_active=True,
                object_id=oid,
            )
            sensors.append(s)
        session.add_all(sensors)
        await session.flush()

        # ── Alarm Configs ──────────────────────────────────────
        for s in sensors:
            configs = [
                AlarmConfig(
                    alarm_type=AlarmType.HIGH_TEMPERATURE,
                    threshold_value=8.0 if "mroź" in s.name.lower() or "mroź" in s.slug else 10.0,
                    trigger_delay_seconds=30,  # short for demo
                    is_enabled=True,
                    sensor_id=s.id,
                ),
                AlarmConfig(
                    alarm_type=AlarmType.LOW_TEMPERATURE,
                    threshold_value=-25.0 if "mroź" in s.name.lower() or "mroź" in s.slug else 0.0,
                    trigger_delay_seconds=30,
                    is_enabled=True,
                    sensor_id=s.id,
                ),
                AlarmConfig(
                    alarm_type=AlarmType.OFFLINE,
                    threshold_value=None,
                    trigger_delay_seconds=30,
                    is_enabled=True,
                    sensor_id=s.id,
                ),
            ]
            session.add_all(configs)
        await session.flush()

        # ── Sample Measurements (last 2 hours, every 5 min) ────
        for s in sensors:
            base_temp = float(s.current_temperature or 2.0)
            for i in range(24):
                t = now - timedelta(minutes=(24 - i) * 5)
                # slight variation
                import random
                temp = base_temp + random.uniform(-0.8, 0.8)
                session.add(Measurement(
                    sensor_id=s.id,
                    temperature=round(temp, 2),
                    received_at=t,
                ))

        await session.commit()
        print("SEED COMPLETE - 3 objects, 6 sensors, alarm configs, 144 measurements")


if __name__ == "__main__":
    asyncio.run(seed())