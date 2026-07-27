#!/usr/bin/env python3
"""Apply final fix: EMQX with NODE_COOKIE + emqx ping healthcheck."""
import paramiko, sys, time

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"

def run(client, cmd, to=60):
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=to)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip(): print(out[:2000])
    if err.strip() and "WARNING" not in err and "warning" not in err: print(f"[STDERR] {err[:500]}")
    return out, err

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)
print("[OK] SSH connected.")

# Upload
print("\n--- Uploading docker-compose.yml ---")
sftp = client.open_sftp()
sftp.put("docker-compose.yml", f"{PROJECT_DIR}/docker-compose.yml")
sftp.close()
print("[OK] Uploaded.")

# Stop, rm, up EMQX
run(client, f"cd {PROJECT_DIR} && docker compose stop emqx")
run(client, f"cd {PROJECT_DIR} && docker compose rm -f emqx")
run(client, f"cd {PROJECT_DIR} && docker compose up -d emqx", to=60)

# Wait for EMQX healthy
print("\n--- Waiting for EMQX healthy... ---")
for i in range(15):
    time.sleep(5)
    out, _ = run(client, "docker inspect frigocore-emqx --format '{{.State.Health.Status}}'", to=10)
    status = out.strip()
    print(f"  [{i+1}] {status}")
    if status == "healthy":
        print("[OK] EMQX is healthy!")
        break
else:
    print("[WARN] EMQX not healthy after timeout.")

# Up backend
print("\n--- Starting backend ---")
run(client, f"cd {PROJECT_DIR} && docker compose up -d backend", to=120)
time.sleep(5)
run(client, "docker logs frigocore-backend --tail=80")

# Up frontend
print("\n--- Starting frontend ---")
run(client, f"cd {PROJECT_DIR} && docker compose up -d frontend", to=120)
time.sleep(5)
run(client, "docker logs frigocore-frontend --tail=40")

# Final
print("\n" + "="*60 + "\nFINAL STATUS\n" + "="*60)
run(client, f"cd {PROJECT_DIR} && docker compose ps")
run(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/docs 2>&1 || echo 'BACKEND_NOT_RESPONDING'")
run(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:5173 2>&1 || echo 'FRONTEND_NOT_RESPONDING'")
run(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:18083 2>&1 || echo 'EMQX_NOT_RESPONDING'")

client.close()
print("\n[DONE]")