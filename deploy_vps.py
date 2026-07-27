#!/usr/bin/env python3
"""Deploy latest changes to VPS - pull, rebuild, restart, and verify."""
import paramiko
import time

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30,
               look_for_keys=False, allow_agent=False)

def run(cmd, timeout=120):
    print(f"> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    exit_code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out[-800:])
    if err.strip():
        print(f"STDERR: {err[-400:]}")
    print(f"exit={exit_code}")
    return exit_code

# Step 1: Pull latest code
print("=" * 60)
print("STEP 1: Pull latest code from GitHub")
print("=" * 60)
run(f"cd {PROJECT_DIR} && git pull origin main 2>&1")

# Step 2: Remove old DB to force fresh seed
print("\n" + "=" * 60)
print("STEP 2: Remove old database and volumes")
print("=" * 60)
run(f"cd {PROJECT_DIR} && docker compose down -v 2>&1", 60)
run("docker volume prune -f 2>&1", 30)

# Step 3: Rebuild and start
print("\n" + "=" * 60)
print("STEP 3: Rebuild and start containers")
print("=" * 60)
run(f"cd {PROJECT_DIR} && docker compose up -d --build 2>&1", 300)

# Step 4: Wait for initialization
print("\n" + "=" * 60)
print("STEP 4: Wait 40s for initialization")
print("=" * 60)
time.sleep(40)

# Step 5: Check container status
print("\n" + "=" * 60)
print("STEP 5: Container status")
print("=" * 60)
run(f"cd {PROJECT_DIR} && docker compose ps 2>&1")

# Step 6: Check backend logs
print("\n" + "=" * 60)
print("STEP 6: Backend logs")
print("=" * 60)
run("docker logs frigocore-backend --tail=20 2>&1")

# Step 7: Test health endpoint
print("\n" + "=" * 60)
print("STEP 7: Test health endpoint")
print("=" * 60)
run("curl -s http://localhost:8000/health", 10)

# Step 8: Test objects list
print("\n" + "=" * 60)
print("STEP 8: Test objects list")
print("=" * 60)
run("curl -s http://localhost:8000/api/v1/objects", 10)

# Step 9: Test alarm config endpoint
print("\n" + "=" * 60)
print("STEP 9: Test alarm config endpoint on first sensor")
print("=" * 60)
run("""curl -s http://localhost:8000/api/v1/sensors/$(curl -s http://localhost:8000/api/v1/objects/$(curl -s http://localhost:8000/api/v1/objects | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")/sensors | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'] if json.load(sys.stdin) else 'none')")/alarm-config 2>&1""", 10)

# Step 10: Test alarm config update
print("\n" + "=" * 60)
print("STEP 10: Test alarm config PUT")
print("=" * 60)
run("""curl -s -X PUT http://localhost:8000/api/v1/sensors/$(curl -s http://localhost:8000/api/v1/objects/$(curl -s http://localhost:8000/api/v1/objects | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")/sensors | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'] if json.load(sys.stdin) else 'none')")/alarm-config -H "Content-Type: application/json" -d '{"high_temperature": 8.0, "high_delay": 60}' 2>&1""", 10)

# Step 11: Test MQTT simulation
print("\n" + "=" * 60)
print("STEP 11: Test MQTT simulation")
print("=" * 60)
run("""curl -s -X POST http://localhost:8000/api/v1/sim/frigo/intermarche/komora-a1 -H "Content-Type: application/json" -d '{"temperature": 5.5}' 2>&1""", 10)

# Step 12: Check frontend
print("\n" + "=" * 60)
print("STEP 12: Check frontend")
print("=" * 60)
run("curl -s -o /dev/null -w '%{http_code}' http://localhost:5173/", 10)

client.close()
print("\n" + "=" * 60)
print("DEPLOYMENT COMPLETE")
print("=" * 60)