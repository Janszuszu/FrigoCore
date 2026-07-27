"""FrigoCore — Seed demo data via REST API."""
import urllib.request
import json

BASE = "http://localhost:8000/api/v1"

def post(path, data):
    req = urllib.request.Request(
        f"{BASE}{path}",
        json.dumps(data).encode(),
        {"Content-Type": "application/json"},
    )
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except Exception as e:
        print(f"  ERROR {path}: {e}")
        raise

# ── Objects ──
print("Creating objects...")
import urllib.request as ur

objects_list = json.loads(urllib.request.urlopen(f"{BASE}/objects").read())
if len(objects_list) < 3:
    obj1 = post("/objects", {"name":"Intermarche Szczytno","description":"Supermarket"})
    obj2 = post("/objects", {"name":"Biedronka Olsztyn","description":"Dyskont"})
    obj3 = post("/objects", {"name":"Magazyn Centralny","description":"Magazyn chlodniczy"})
else:
    objects_list.sort(key=lambda x: x['name'])
    obj1, obj2, obj3 = objects_list
    print(f"  Using existing objects")
print(f"  {obj1['id']} {obj2['id']} {obj3['id']}")

# ── Sensors ──
print("Creating sensors...")
sensor_data = [
    (obj1, "Komora chlodnicza A1", "frigo/intermarche/komora-a1", 60),
    (obj1, "Mroznia B1", "frigo/intermarche/mroznia-b1", 60),
    (obj2, "Lada miesna", "frigo/biedronka/lada-miesna", 90),
    (obj2, "Lada nabialowa", "frigo/biedronka/lada-nabialowa", 90),
    (obj3, "Komora mroznicza G1", "frigo/magazyn/komora-g1", 120),
    (obj3, "Komora chlodnicza G2", "frigo/magazyn/komora-g2", 120),
]
sensors = []
for obj, name, topic, timeout in sensor_data:
    s = post(f"/objects/{obj['id']}/sensors", {"name": name, "mqtt_topic": topic, "offline_timeout_seconds": timeout})
    sensors.append(s)
for s in sensors:
    print(f"  {s['mqtt_topic']}: {s['id']}")

# ── Alarm Configs ──
print("Creating alarm configs...")
for s in sensors:
    thresholds = {
        "frigo/intermarche/komora-a1": (10.0, 0.0),
        "frigo/intermarche/mroznia-b1": (8.0, -25.0),
        "frigo/biedronka/lada-miesna": (10.0, 0.0),
        "frigo/biedronka/lada-nabialowa": (10.0, 0.0),
        "frigo/magazyn/komora-g1": (8.0, -25.0),
        "frigo/magazyn/komora-g2": (10.0, 0.0),
    }
    high_t, low_t = thresholds[s["mqtt_topic"]]
    post(f"/sensors/{s['id']}/alarm-configs", {"alarm_type":"high_temperature","threshold_value":high_t,"trigger_delay_seconds":30,"is_enabled":True})
    post(f"/sensors/{s['id']}/alarm-configs", {"alarm_type":"low_temperature","threshold_value":low_t,"trigger_delay_seconds":30,"is_enabled":True})
    post(f"/sensors/{s['id']}/alarm-configs", {"alarm_type":"offline","threshold_value":None,"trigger_delay_seconds":30,"is_enabled":True})
print("  Done")

# ── Simulate initial measurements ──
print("Sending simulated MQTT measurements...")
temps = {
    "frigo/intermarche/komora-a1": 3.8,
    "frigo/intermarche/mroznia-b1": -18.2,
    "frigo/biedronka/lada-miesna": 2.1,
    "frigo/biedronka/lada-nabialowa": 4.5,
    "frigo/magazyn/komora-g1": -22.0,
    "frigo/magazyn/komora-g2": 2.0,
}
for s in sensors:
    topic = s["mqtt_topic"]
    t = temps[topic]
    # Send several measurements with variation
    import random
    for _ in range(8):
        post(f"/sim/simulate/{topic}", {"temperature": round(t + random.uniform(-0.5, 0.5), 2)})
print("  Done")

print("\nSEED COMPLETE")
print("Objects:", obj1["name"], obj2["name"], obj3["name"])
print("6 sensors with alarm configs and measurements")