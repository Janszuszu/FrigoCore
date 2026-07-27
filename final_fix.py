#!/usr/bin/env python3
"""
FrigoCore VPS — Final Fix
Wgrywa poprawiony docker-compose.yml (curl-based healthcheck),
restartuje EMQX, uruchamia backend i frontend.
"""
import paramiko
import sys
import time

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"


def safe_write(data: bytes):
    try:
        sys.stdout.buffer.write(data)
    except Exception:
        text = data.decode("ascii", errors="replace")
        sys.stdout.write(text)
    sys.stdout.flush()


def run_cmd(client, cmd, timeout=60):
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read()
    err = stderr.read()
    if out:
        safe_write(out)
    if err:
        err_s = err.decode("utf-8", errors="replace").strip()
        if err_s and "WARNING" not in err_s and "warning" not in err_s.lower():
            safe_write(b"\n[STDERR]\n")
            safe_write(err)
    return out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")


def main():
    print("FrigoCore VPS — Final Fix (curl healthcheck)")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)
    print("[OK] SSH connected.\n")

    # 1. Upload fixed docker-compose.yml
    print("--- Uploading fixed docker-compose.yml ---")
    sftp = client.open_sftp()
    sftp.put("docker-compose.yml", f"{PROJECT_DIR}/docker-compose.yml")
    sftp.close()
    print("[OK] docker-compose.yml uploaded.")

    # 2. Verify curl is available in emqx image
    run_cmd(client, "docker exec frigocore-emqx which curl 2>&1 || echo 'CURL NOT FOUND, trying apk add'")
    run_cmd(client, "docker exec frigocore-emqx curl -sf http://localhost:18083 2>&1 && echo 'CURL_WORKS' || echo 'CURL_FAILED'")

    # 3. Stop, remove, recreate EMQX with new healthcheck
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose stop emqx 2>&1")
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose rm -f emqx 2>&1")
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose up -d emqx 2>&1", timeout=60)

    # 4. Wait for EMQX healthy
    print("\n--- Waiting for EMQX healthy (curl check)... ---")
    for i in range(15):
        time.sleep(5)
        out, _ = run_cmd(client, "docker inspect frigocore-emqx --format '{{.State.Health.Status}}' 2>&1")
        if "healthy" in out:
            print("[OK] EMQX is healthy!")
            break
        print(f"  ... attempt {i+1}: {out.strip()}")
    else:
        print("[WARN] Timeout. Checking status...")
        run_cmd(client, f"cd {PROJECT_DIR} && docker compose ps emqx 2>&1")

    # 5. Start backend
    print("\n--- Starting backend ---")
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose up -d backend 2>&1", timeout=120)
    time.sleep(10)
    run_cmd(client, "docker logs frigocore-backend --tail=60 2>&1")

    # 6. Start frontend
    print("\n--- Starting frontend ---")
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose up -d frontend 2>&1", timeout=120)
    time.sleep(10)
    run_cmd(client, "docker logs frigocore-frontend --tail=40 2>&1")

    # 7. Final status
    print("\n" + "="*60)
    print("FINAL STATUS")
    print("="*60)
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose ps 2>&1")
    run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/docs 2>&1 || echo 'Backend not responding'")
    run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:5173 2>&1 || echo 'Frontend not responding'")
    run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:18083 2>&1 || echo 'EMQX Dashboard not responding'")

    client.close()
    print("\n[DONE] All services should be running.")


if __name__ == "__main__":
    main()