#!/usr/bin/env python3
"""
FrigoCore VPS Full Deployment — git pull, fresh DB, rebuild, verify
"""
import json
import paramiko
import sys
import time
import urllib.request

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"


def run_cmd(client, cmd, timeout=120):
    """Execute a command via SSH and return stdout, stderr, exit_code."""
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
    print(f"Connecting to {HOST}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST,
        username=USER,
        password=PASSWORD,
        timeout=30,
        look_for_keys=False,
        allow_agent=False,
    )
    print("Connected!\n")

    # ================================================================
    # STEP 1: Git pull
    # ================================================================
    run_cmd(client, f"cd {PROJECT_DIR} && git pull")

    # ================================================================
    # STEP 2: Stop all containers
    # ================================================================
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose down", timeout=180)

    # ================================================================
    # STEP 3: Remove old PostgreSQL volume for a fresh database
    # ================================================================
    print("\n--- Removing old database volume for fresh start ---")
    run_cmd(client, "docker volume rm frigocore_postgres_data 2>/dev/null; echo 'Volume removed or already absent'")
    run_cmd(client, "docker volume rm frigocore_redis_data 2>/dev/null; echo 'Redis volume removed or absent'")

    # ================================================================
    # STEP 4: Build and start containers
    # ================================================================
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose up -d --build", timeout=300)

    # ================================================================
    # STEP 5: Wait for initialization
    # ================================================================
    print("\nWaiting 45 seconds for services to initialize...")
    time.sleep(45)

    # ================================================================
    # STEP 6: Container status
    # ================================================================
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose ps")

    # ================================================================
    # STEP 7: Logs
    # ================================================================
    for svc, label in [
        ("frigocore-postgres", "PostgreSQL"),
        ("frigocore-backend", "Backend"),
        ("frigocore-frontend", "Frontend"),
        ("frigocore-emqx", "EMQX"),
    ]:
        print(f"\n--- LOGS: {label} (last 30 lines) ---")
        run_cmd(client, f"docker logs {svc} --tail=30 2>&1")

    # ================================================================
    # STEP 8: Verify endpoints
    # ================================================================
    print("\n" + "="*60)
    print("VERIFYING ENDPOINTS...")
    print("="*60)

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
        print(f"  {code} - {label} ({url})")

    # ================================================================
    # STEP 9: Test API — create object + sensor + simulate MQTT
    # ================================================================
    print("\n" + "="*60)
    print("TESTING API OPERATIONS...")
    print("="*60)

    # Create object
    print("\n--- Creating object ---")
    stdin, stdout, stderr = client.exec_command(
        """curl -s -X POST http://localhost:8000/api/v1/objects \\
          -H 'Content-Type: application/json' \\
          -d '{"name":"Testowy Obiekt","description":"Obiekt testowy po wdrozeniu"}'""",
        timeout=10,
    )
    obj_response = stdout.read().decode("utf-8", errors="replace")
    print(f"  Response: {obj_response}")
    try:
        obj_data = json.loads(obj_response)
        object_id = obj_data.get("id", "")
        print(f"  Object ID: {object_id}")
    except json.JSONDecodeError:
        print("  ERROR: Could not parse object response")
        object_id = ""

    # Create sensor
    if object_id:
        print(f"\n--- Creating sensor for object {object_id} ---")
        stdin, stdout, stderr = client.exec_command(
            f"""curl -s -X POST http://localhost:8000/api/v1/objects/{object_id}/sensors \\
              -H 'Content-Type: application/json' \\
              -d '{{"name":"Sensor Testowy","mqtt_topic":"frigo/test/sensor-1","offline_timeout_seconds":120}}'""",
            timeout=10,
        )
        sensor_response = stdout.read().decode("utf-8", errors="replace")
        print(f"  Response: {sensor_response}")
        try:
            sensor_data = json.loads(sensor_response)
            sensor_id = sensor_data.get("id", "")
            mqtt_topic = sensor_data.get("mqtt_topic", "")
            print(f"  Sensor ID: {sensor_id}")
            print(f"  MQTT Topic: {mqtt_topic}")
        except json.JSONDecodeError:
            print("  ERROR: Could not parse sensor response")
            sensor_id = ""
            mqtt_topic = ""

        # Simulate MQTT measurement
        if sensor_id and mqtt_topic:
            print(f"\n--- Simulating MQTT measurement on {mqtt_topic} ---")
            stdin, stdout, stderr = client.exec_command(
                f"""curl -s -X POST 'http://localhost:8000/api/v1/sim/simulate/{mqtt_topic}' \\
                  -H 'Content-Type: application/json' \\
                  -d '{{"temperature": 4.5}}'""",
                timeout=10,
            )
            sim_response = stdout.read().decode("utf-8", errors="replace")
            print(f"  Response: {sim_response}")

            # Verify measurement was saved
            print(f"\n--- Fetching measurements for sensor {sensor_id} ---")
            stdin, stdout, stderr = client.exec_command(
                f"curl -s http://localhost:8000/api/v1/sensors/{sensor_id}/measurements",
                timeout=10,
            )
            meas_response = stdout.read().decode("utf-8", errors="replace")
            print(f"  Measurements: {meas_response[:200]}...")
            try:
                meas_data = json.loads(meas_response)
                print(f"  Count: {len(meas_data)} measurements saved")
            except json.JSONDecodeError:
                print("  ERROR: Could not parse measurements")

            # Verify sensor shows current_temperature
            print(f"\n--- Verifying sensor data updated ---")
            stdin, stdout, stderr = client.exec_command(
                f"curl -s http://localhost:8000/api/v1/objects/{object_id}/sensors/{sensor_id}",
                timeout=10,
            )
            sensor_get_response = stdout.read().decode("utf-8", errors="replace")
            print(f"  Sensor data: {sensor_get_response}")

    # ================================================================
    # STEP 10: Health check for all containers
    # ================================================================
    print("\n" + "="*60)
    print("CONTAINER HEALTH STATUS...")
    print("="*60)
    stdin, stdout, stderr = client.exec_command(
        "docker inspect --format='{{.Name}} {{.State.Status}}/{{.State.Health.Status}}' "
        "frigocore-postgres frigocore-redis frigocore-emqx "
        "frigocore-backend frigocore-frontend",
        timeout=10,
    )
    out = stdout.read().decode("ascii", errors="replace")
    sys.stdout.write(out)

    # ================================================================
    # DONE
    # ================================================================
    client.close()

    print("\n" + "="*60)
    print("DEPLOYMENT COMPLETE!")
    print("="*60)


if __name__ == "__main__":
    main()