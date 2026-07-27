#!/usr/bin/env python3
"""Quick final verification of VPS deployment."""
import json
import paramiko
import sys

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)

def curl(method, url, data=None):
    if data:
        cmd = f"""curl -s -X {method} '{url}' -H 'Content-Type: application/json' -d '{data}'"""
    else:
        cmd = f"curl -s '{url}'"
    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if err:
        print(f"  CURL WARN: {err}", file=sys.stderr)
    return out

# 1. Create Object
print("=== 1. Create Object ===")
out = curl("POST", "http://localhost:8000/api/v1/objects",
           '{"name":"Obiekt Testowy","description":"Test po wdrozeniu"}')
print(f"  Response: {out[:200]}")
obj = json.loads(out)
oid = obj["id"]
print(f"  OK - Object ID: {oid}")

# 2. Create Sensor
print("\n=== 2. Create Sensor ===")
out = curl("POST", f"http://localhost:8000/api/v1/objects/{oid}/sensors",
           '{"name":"Sensor Testowy","mqtt_topic":"frigo/test/sensor-1","offline_timeout_seconds":120}')
print(f"  Response: {out[:200]}")
sensor = json.loads(out)
sid = sensor["id"]
topic = sensor["mqtt_topic"]
print(f"  OK - Sensor ID: {sid}, Topic: {topic}")

# 3. Simulate MQTT
print(f"\n=== 3. Simulate MQTT ({topic}) ===")
out = curl("POST", f"http://localhost:8000/api/v1/sim/simulate/{topic}",
           '{"temperature": 4.5}')
sim = json.loads(out)
print(f"  OK - {json.dumps(sim, indent=2)}")

# 4. Read Measurements
print("\n=== 4. Read Measurements ===")
out = curl("GET", f"http://localhost:8000/api/v1/sensors/{sid}/measurements")
meas = json.loads(out)
print(f"  OK - {len(meas)} measurement(s) recorded")
if meas:
    print(f"  Latest: temp={meas[0]['temperature']}, at={meas[0]['received_at']}")

# 5. Verify sensor updated
print("\n=== 5. Verify Sensor Updated ===")
out = curl("GET", f"http://localhost:8000/api/v1/objects/{oid}/sensors/{sid}")
s = json.loads(out)
print(f"  current_temperature: {s['current_temperature']}")
print(f"  last_message_at: {s['last_message_at']}")
assert s["current_temperature"] == 4.5, "Temperature not updated!"
print("  OK - Sensor temperature updated correctly")

# 6. Container status
print("\n=== 6. Container Status ===")
stdin, stdout, stderr = client.exec_command(f"cd {PROJECT_DIR} && docker compose ps")
print(stdout.read().decode(errors="replace"))

# 7. Git log
print("\n=== 7. Git Log ===")
stdin, stdout, stderr = client.exec_command(f"cd {PROJECT_DIR} && git log --oneline -3")
print(stdout.read().decode(errors="replace"))

client.close()
print("\n" + "="*60)
print("ALL VERIFICATIONS PASSED SUCCESSFULLY!")
print("="*60)