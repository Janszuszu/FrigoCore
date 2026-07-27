"""Quick seed — direct SQLite, bypasses REST."""
import sqlite3, uuid, random, os
from datetime import datetime, timezone, timedelta

DB = r"c:\Projekty\FrigoCore\backend\frigocore.db"

# Delete old DB and let backend recreate
if os.path.exists(DB):
    os.unlink(DB)
    print("Deleted old DB")

conn = sqlite3.connect(DB)
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA journal_mode = WAL")
c = conn.cursor()

now = datetime.now(timezone.utc).isoformat()
ts = lambda h=0: (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()

# Objects
objs = [
    ("11111111-1111-1111-1111-111111111111","Intermarche Szczytno","Supermarket - regaly chlodnicze",1),
    ("22222222-2222-2222-2222-222222222222","Biedronka Olsztyn","Dyskont spozywczy",1),
    ("33333333-3333-3333-3333-333333333333","Magazyn Centralny","Magazyn chlodniczy",1),
]
for oid, nm, desc, active in objs:
    c.execute("INSERT INTO objects(id,name,description,is_active,created_at,updated_at) VALUES(?,?,?,?,?,?)",
              (oid.replace('-',''),nm,desc,active,now,now))

# Sensors (id, object_id, name, mqtt_topic, temp, timeout)
sens = [
    ("11111111-aaaa-1111-aaaa-111111111111",objs[0][0],"Komora chlodnicza A1","frigo/intermarche/komora-a1",3.8,60),
    ("11111111-bbbb-1111-bbbb-111111111111",objs[0][0],"Mroznia B1","frigo/intermarche/mroznia-b1",-18.2,60),
    ("22222222-aaaa-2222-aaaa-222222222222",objs[1][0],"Lada miesna","frigo/biedronka/lada-miesna",2.1,90),
    ("22222222-bbbb-2222-bbbb-222222222222",objs[1][0],"Lada nabialowa","frigo/biedronka/lada-nabialowa",4.5,90),
    ("33333333-aaaa-3333-aaaa-333333333333",objs[2][0],"Komora mroznicza G1","frigo/magazyn/komora-g1",-22.0,120),
    ("33333333-bbbb-3333-bbbb-333333333333",objs[2][0],"Komora chlodnicza G2","frigo/magazyn/komora-g2",2.0,120),
]
for sid, oid, nm, topic, temp, timeout in sens:
    c.execute("INSERT INTO sensors(id,name,mqtt_topic,current_temperature,last_message_at,offline_timeout_seconds,is_active,object_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (sid.replace('-',''),nm,topic,temp,now,timeout,1,oid.replace('-',''),now,now))

# Alarm configs
thresholds = {"frigo/intermarche/komora-a1":(10.0,0.0),"frigo/intermarche/mroznia-b1":(8.0,-25.0),
              "frigo/biedronka/lada-miesna":(10.0,0.0),"frigo/biedronka/lada-nabialowa":(10.0,0.0),
              "frigo/magazyn/komora-g1":(8.0,-25.0),"frigo/magazyn/komora-g2":(10.0,0.0)}
for s in sens:
    sid, topic = s[0].replace('-',''), s[3]
    hi, lo = thresholds[topic]
    for atype, thresh in [("high_temperature",hi),("low_temperature",lo),("offline",None)]:
        c.execute("INSERT INTO alarm_configs(id,alarm_type,threshold_value,trigger_delay_seconds,is_enabled,sensor_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                  (uuid.uuid4().hex,atype,thresh,30,1,sid,now,now))

# Measurements (last 2h, every 5min)
for s in sens:
    sid = s[0].replace('-','')
    base = s[4]
    for i in range(24):
        t = (datetime.now(timezone.utc) - timedelta(minutes=(24-i)*5)).isoformat()
        temp = base + random.uniform(-0.6,0.6)
        c.execute("INSERT INTO measurements(id,temperature,received_at,sensor_id) VALUES(?,?,?,?)",
                  (uuid.uuid4().hex,round(temp,2),t,sid))

conn.commit()
conn.close()
print("SEED DONE - 3 objects, 6 sensors, 18 alarm configs, 144 measurements")