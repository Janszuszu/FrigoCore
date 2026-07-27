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
    obj1 = post("/objects", {"name":"Intermarche Szczytno","slug":"intermarche-szczytno","description":"Supermarket"})
    obj2 = post("/objects", {"name":"Biedronka Olsztyn","slug":"biedronka-olsztyn","description":"Dyskont"})
    obj3 = post("/objects", {"name":"Magazyn Centralny","slug":"magazyn-centralny","description":"Magazyn chlodniczy"})
else:
    objects_list.sort(key=lambda x: x['slug'])
    obj1, obj2, obj3 = objects_list
    print(f"  Using existing objects")
print(f"  {obj1['id']} {obj2['id']} {obj3['id']}")

# ── Sensors ──
print("Creating sensors...")
sensors = [
    post(f"/objects/{obj1['id']}/sensors", {"name":"Komora chlodnicza A1","slug":"komora-a1","offline_timeout_seconds":60}),
    post(f"/objects/{obj1['id']}/sensors", {"name":"Mroznia B1","slug":"mroznia-b1","offline_timeout_seconds":60}),
    post(f"/objects/{obj2['id']}/sensors", {"name":"Lada miesna","slug":"lada-miesna","offline_timeout_seconds":90}),
    post(f"/objects/{obj2['id']}/sensors", {"name":"Lada nabialowa","slug":"lada-nabialowa","offline_timeout_seconds":90}),
    post(f"/objects/{obj3['id']}/sensors", {"name":"Komora mroznicza G1","slug":"komora-g1","offline_timeout_seconds":120}),
    post(f"/objects/{obj3['id']}/sensors", {"name":"Komora chlodnicza G2","slug":"komora-g2","offline_timeout_seconds":120}),
]
for s in sensors:
    print(f"  {s['slug']}: {s['id']}")

# ── Alarm Configs ──
print("Creating alarm configs...")
for s in sensors:
    thresholds = {
        "komora-a1": (10.0, 0.0),
        "mroznia-b1": (8.0, -25.0),
        "lada-miesna": (10.0, 0.0),
        "lada-nabialowa": (10.0, 0.0),
        "komora-g1": (8.0, -25.0),
        "komora-g2": (10.0, 0.0),
    }
    high_t, low_t = thresholds[s["slug"]]
    post(f"/sensors/{s['id']}/alarm-configs", {"alarm_type":"high_temperature","threshold_value":high_t,"trigger_delay_seconds":30,"is_enabled":True})
    post(f"/sensors/{s['id']}/alarm-configs", {"alarm_type":"low_temperature","threshold_value":low_t,"trigger_delay_seconds":30,"is_enabled":True})
    post(f"/sensors/{s['id']}/alarm-configs", {"alarm_type":"offline","threshold_value":None,"trigger_delay_seconds":30,"is_enabled":True})
print("  Done")

# ── Simulate initial measurements ──
print("Sending simulated MQTT measurements...")
temps = {
    "komora-a1": 3.8,
    "mroznia-b1": -18.2,
    "lada-miesna": 2.1,
    "lada-nabialowa": 4.5,
    "komora-g1": -22.0,
    "komora-g2": 2.0,
}
objects_slug = {
    "komora-a1": "intermarche-szczytno",
    "mroznia-b1": "intermarche-szczytno",
    "lada-miesna": "biedronka-olsztyn",
    "lada-nabialowa": "biedronka-olsztyn",
    "komora-g1": "magazyn-centralny",
    "komora-g2": "magazyn-centralny",
}
for s in sensors:
    slug = s["slug"]
    obj_slug = objects_slug[slug]
    t = temps[slug]
    # Send several measurements with variation
    import random
    for _ in range(8):
        post(f"/sim/simulate/{obj_slug}/{slug}", {"temperature": round(t + random.uniform(-0.5, 0.5), 2)})
print("  Done")

print("\nSEED COMPLETE")
print("Objects:", obj1["name"], obj2["name"], obj3["name"])
print("6 sensors with alarm configs and measurements")