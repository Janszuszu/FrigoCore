#!/usr/bin/env python3
"""
FrigoCore Final Verification — fix git pull, verify endpoints, test API
"""
import json
import paramiko
import sys

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"


def run_cmd(client, cmd, timeout=30):
    print(f"\n{'='*60}")
    print(f"CMD: {cmd}")
    print(f"{'='*60}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    exit_code = stdout.channel.recv_exit_status()
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    print(f"EXIT: {exit_code}")
    return out, err, exit_code


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST, username=USER, password=PASSWORD,
        timeout=30, look_for_keys=False, allow_agent=False,
    )
    print("Connected!")

    # ── Step 1: Stash local changes + pull actual code ──
    print("\n--- Fixing git pull (stash local changes) ---")
    run_cmd(client, f"cd {PROJECT_DIR} && git stash && git pull")

    # ── Step 2: Container status ──
    print("\n--- Container status ---")
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose ps")

    # ── Step 3: Verify endpoints ──
    print("\n--- HTTP endpoints ---")
    endpoints = [
        ("http://localhost:8000/health", "Backend Health"),
        ("http://localhost:8000/docs", "Backend API Docs"),
        ("http://localhost:5173", "Frontend"),
        ("http://localhost:18083", "EMQX Dashboard"),
    ]
    for url, label in endpoints:
        stdin, stdout, stderr = client.exec_command(
            'curl -s -o /dev/null -w "%{http_code}" ' + url, timeout=10
        )
        code = stdout.read().decode("ascii", errors="replace").strip()
        err = stderr.read().decode("ascii", errors="replace").strip()
        status = "OK" if code == "200" else f"UNEXPECTED ({code})"
        print(f"  {code} - {label} - {status}")
        if err:
            print(f"  stderr: {err}")

    # ── Step 4: Test API operations ──
    print("\n--- Testing: Create Object ---")
    stdin, stdout, stderr = client.exec_command(
        "curl -s -X POST http://localhost:8000/api/v1/objects "
        "-H 'Content-Type: application/json' "
        "-d '{\"name\":\"Obiekt Testowy\",\"description\":\"Utworzony po wdrozeniu\"}'",
        timeout=10,
    )
    obj = json.loads(stdout.read().decode())
    oid = obj.get("id", "?")
    print(f"  Object created: id={oid}, name={obj.get('name')}")

    print("\n--- Testing: Create Sensor ---")
    stdin, stdout, stderr = client.exec_command(
        f"curl -s -X POST http://localhost:8000/api/v1/objects/{oid}/sensors "
        "-H 'Content-Type: application/json' "
        "-d '{\"name\":\"Sensor Testowy\",\"mqtt_topic\":\"frigo/test/sensor-1\",\"offline_timeout_seconds\":120}'",
        timeout=10,
    )
    sensor = json.loads(stdout.read().decode())
    sid = sensor.get("id", "?")
    topic = sensor.get("mqtt_topic", "")
    print(f"  Sensor created: id={sid}, mqtt_topic={topic}")

    print(f"\n--- Testing: Simulate MQTT on {topic} ---")
    stdin, stdout, stderr = client.exec_command(
        f"curl -s -X POST 'http://localhost:8000/api/v1/sim/simulate/{topic}' "
        "-H 'Content-Type: application/json' "
        "-d '{\"temperature\": 4.5}'",
        timeout=10,
    )
    sim_result = json.loads(stdout.read().decode())
    print(f"  Sim result: {json.dumps(sim_result, indent=2)}")

    print(f"\n--- Testing: Read measurements ---")
    stdin, stdout, stderr = client.exec_command(
        f"curl -s http://localhost:8000/api/v1/sensors/{sid}/measurements",
        timeout=10,
    )
    measurements = json.loads(stdout.read().decode())
    print(f"  Measurements count: {len(measurements)}")
    if measurements:
        m = measurements[0]
        print(f"  Latest: temp={m['temperature']} at={m['received_at']}")

    print(f"\n--- Testing: Verify sensor updated ---")
    stdin, stdout, stderr = client.exec_command(
        f"curl -s http://localhost:8000/api/v1/objects/{oid}/sensors/{sid}",
        timeout=10,
    )
    sensor_read = json.loads(stdout.read().decode())
    print(f"  Sensor current_temperature: {sensor_read.get('current_temperature')}")
    print(f"  Sensor last_message_at: {sensor_read.get('last_message_at')}")

    # ── Step 5: Git log ──
    print("\n--- Git log ---")
    run_cmd(client, f"cd {PROJECT_DIR} && git log --oneline -3")

    # ── Step 6: Container health ──
    print("\n--- Container health ---")
    stdin, stdout, stderr = client.exec_command(
        "docker inspect --format='{{.Name}} {{.State.Status}}/{{.State.Health.Status}}' "
        "frigocore-postgres frigocore-redis frigocore-emqx "
        "frigocore-backend frigocore-frontend",
        timeout=10,
    )
    out = stdout.read().decode("ascii", errors="replace")
    sys.stdout.write(out)

    client.close()
    print("\n=== VERIFICATION COMPLETE ===")


if __name__ == "__main__":
    main()