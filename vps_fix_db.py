#!/usr/bin/env python3
"""Fix VPS database - force clean PostgreSQL volume and restart."""
import paramiko
import time
import sys

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)

def run(cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    exit_code = stdout.channel.recv_exit_status()
    if out.strip():
        sys.stdout.write(out[-500:])
    if err.strip():
        sys.stderr.write(err[-200:])
    print(f"exit={exit_code}")
    return out, err, exit_code

# Step 1: Stop all containers
print("=== Stopping containers ===")
run("cd /opt/FrigoCore && docker compose down -v 2>&1", 60)

# Step 2: Force remove volumes
print("\n=== Force removing volumes ===")
run("docker volume prune -f 2>&1", 30)

# Step 3: Verify volumes are gone
print("\n=== Verify volumes ===")
run("docker volume ls 2>&1", 10)

# Step 4: Rebuild and start
print("\n=== Building and starting ===")
run("cd /opt/FrigoCore && docker compose up -d --build 2>&1", 300)

print("\n=== Waiting 40s for initialization ===")
time.sleep(40)

# Step 5: Check status
print("\n=== Container status ===")
run("cd /opt/FrigoCore && docker compose ps 2>&1", 10)

# Step 6: Check backend logs
print("\n=== Backend logs ===")
run("docker logs frigocore-backend --tail=20 2>&1", 10)

# Step 7: Test API
print("\n=== Testing health endpoint ===")
run("curl -s http://localhost:8000/health", 10)

print("\n=== Testing objects list ===")
run("curl -s http://localhost:8000/api/v1/objects", 10)

print("\n=== Creating test object ===")
run('curl -s -X POST http://localhost:8000/api/v1/objects -H "Content-Type: application/json" -d \'{"name":"Test Obiekt","description":"Testowy"}\'', 10)

client.close()
print("\n=== DONE ===")