"""FrigoCore — complete dev setup: init DB + seed data."""
import asyncio, uuid, random
from datetime import datetime, timezone, timedelta

from app.database import async_session_factory, init_db
from app.models.object import Object
from app.models.sensor import Sensor
from app.models.alarm_config import AlarmConfig
from app.models.measurement import Measurement
from app.enums import AlarmType


async def main():
    await init_db()

    async with async_session_factory() as session:
        # Check if data exists
        from sqlalchemy import select
        count = await session.scalar(select(Object).limit(1))
        if count := await session.scalar(select(Object).limit(1)):
            print(f"Data exists — skipping seed ({count})")
            return

        now = datetime.now(timezone.utc)

        # ── Objects ──
        objects = [
            Object(name="Intermarche Szczytno", slug="intermarche-szczytno", description="Supermarket - regaly chlodnicze, mroznie", is_active=True),
            Object(name="Biedronka Olsztyn", slug="biedronka-olsztyn", description="Dyskont spozywczy - lady chlodnicze", is_active=True),
            Object(name="Magazyn Centralny", slug="magazyn-centralny", description="Magazyn chlodniczy - duze komory mroznicze", is_active=True),
        ]
        session.add_all(objects)
        await session.flush()

        # ── Sensors ──
        sdata = [
            (objects[0].id, "Komora chlodnicza A1", "komora-a1", 3.8, 60),
            (objects[0].id, "Mroznia B1", "mroznia-b1", -18.2, 60),
            (objects[1].id, "Lada miesna", "lada-miesna", 2.1, 90),
            (objects[1].id, "Lada nabialowa", "lada-nabialowa", 4.5, 90),
            (objects[2].id, "Komora mroznicza G1", "komora-g1", -22.0, 120),
            (objects[2].id, "Komora chlodnicza G2", "komora-g2", 2.0, 120),
        ]
        sensors = []
        for oid, nm, sl, temp, timeout in sdata:
            s = Sensor(name=nm, slug=sl, current_temperature=temp, last_message_at=now,
                       offline_timeout_seconds=timeout, is_active=True, object_id=oid)
            sensors.append(s)
        session.add_all(sensors)
        await session.flush()

        # ── Alarm Configs ──
        thresholds = {"komora-a1": (10.0, 0.0), "mroznia-b1": (8.0, -25.0), "lada-miesna": (10.0, 0.0),
                      "lada-nabialowa": (10.0, 0.0), "komora-g1": (8.0, -25.0), "komora-g2": (10.0, 0.0)}
        for s in sensors:
            hi, lo = thresholds[s.slug]
            for atype, thresh in [(AlarmType.HIGH_TEMPERATURE, hi), (AlarmType.LOW_TEMPERATURE, lo), (AlarmType.OFFLINE, None)]:
                session.add(AlarmConfig(alarm_type=atype, threshold_value=thresh, trigger_delay_seconds=30, is_enabled=True, sensor_id=s.id))
        await session.flush()

        # ── Measurements (last 2h) ──
        for s in sensors:
            base = s.current_temperature or 0
            for i in range(24):
                t = now - timedelta(minutes=(24 - i) * 5)
                temp = round(base + random.uniform(-0.6, 0.6), 2)
                session.add(Measurement(sensor_id=s.id, temperature=temp, received_at=t))

        await session.commit()
        print("SETUP DONE - 3 objects, 6 sensors, 18 alarm configs, 144 measurements")


if __name__ == "__main__":
    asyncio.run(main())