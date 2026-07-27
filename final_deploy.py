#!/usr/bin/env python3
"""Final deploy: pgrep-based healthcheck + start all services."""
import paramiko, sys, time

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"

def safe_write(data):
    try: sys.stdout.buffer.write(data)
    except: sys.stdout.write(data.decode("ascii","replace"))
    sys.stdout.flush()

def run_shell(client, cmds, wait_per_cmd=3):
    """Run commands via invoke_shell, collect output."""
    ch = client.invoke_shell(width=200, height=50)
    time.sleep(2)
    # drain initial output
    output = b""
    while ch.recv_ready():
        output += ch.recv(8192)
        time.sleep(0.2)
    safe_write(output)

    for desc, cmd in cmds:
        safe_write(f"\n>>> {desc}\n".encode())
        safe_write(f"$ {cmd}\n".encode())
        ch.send(cmd + "\n")
        waited = 0
        max_wait = wait_per_cmd
        cmd_output = b""
        while waited < max_wait:
            time.sleep(0.5)
            waited += 0.5
            if ch.recv_ready():
                chunk = ch.recv(8192)
                cmd_output += chunk
                safe_write(chunk)
                waited = 0
        # extra drain
        time.sleep(0.5)
        while ch.recv_ready():
            chunk = ch.recv(4096)
            cmd_output += chunk
            safe_write(chunk)

    ch.close()
    return output

def main():
    safe_write(b"FrigoCore VPS - Final Deploy\n")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)
    safe_write(b"[OK] SSH connected.\n")

    # ========================================
    # STEP 1: Upload docker-compose.yml
    # ========================================
    safe_write(b"\n--- Uploading docker-compose.yml ---\n")
    sftp = client.open_sftp()
    sftp.put("docker-compose.yml", f"{PROJECT_DIR}/docker-compose.yml")
    sftp.close()
    safe_write(b"[OK] Uploaded.\n")

    # ========================================
    # STEP 2: Check pgrep availability
    # ========================================
    run_shell(client, [
        ("Check pgrep", "docker exec frigocore-emqx which pgrep 2>&1"),
        ("Test pgrep", "docker exec frigocore-emqx pgrep beam.smp 2>&1"),
    ], wait_per_cmd=5)

    # ========================================
    # STEP 3: Restart EMQX
    # ========================================
    run_shell(client, [
        ("Stop EMQX", f"cd {PROJECT_DIR} && docker compose stop emqx 2>&1"),
        ("Remove EMQX", f"cd {PROJECT_DIR} && docker compose rm -f emqx 2>&1"),
        ("Start EMQX", f"cd {PROJECT_DIR} && docker compose up -d emqx 2>&1"),
    ], wait_per_cmd=10)

    # ========================================
    # STEP 4: Wait for EMQX healthy
    # ========================================
    safe_write(b"\n--- Waiting for EMQX healthy (up to 120s)... ---\n")
    for i in range(24):
        time.sleep(5)
        stdin, stdout, stderr = client.exec_command(
            "docker inspect frigocore-emqx --format '{{.State.Health.Status}}'",
            timeout=10
        )
        status = stdout.read().decode().strip()
        safe_write(f"  [{i+1}] {status}\n".encode())
        if status == "healthy":
            safe_write(b"[OK] EMQX is healthy!\n")
            break
    else:
        safe_write(b"[WARN] EMQX not healthy after timeout.\n")

    # ========================================
    # STEP 5: Start backend
    # ========================================
    safe_write(b"\n--- Starting backend ---\n")
    run_shell(client, [
        ("Start backend", f"cd {PROJECT_DIR} && docker compose up -d backend 2>&1"),
    ], wait_per_cmd=90)
    time.sleep(5)
    run_shell(client, [
        ("Backend logs", "docker logs frigocore-backend --tail=80 2>&1"),
    ], wait_per_cmd=10)

    # ========================================
    # STEP 6: Start frontend
    # ========================================
    safe_write(b"\n--- Starting frontend ---\n")
    run_shell(client, [
        ("Start frontend", f"cd {PROJECT_DIR} && docker compose up -d frontend 2>&1"),
    ], wait_per_cmd=90)
    time.sleep(5)
    run_shell(client, [
        ("Frontend logs", "docker logs frigocore-frontend --tail=40 2>&1"),
    ], wait_per_cmd=10)

    # ========================================
    # STEP 7: Final verification
    # ========================================
    safe_write(b"\n" + b"="*60 + b"\nFINAL STATUS\n" + b"="*60 + b"\n")
    run_shell(client, [
        ("docker compose ps", f"cd {PROJECT_DIR} && docker compose ps 2>&1"),
        ("EMQX Dashboard", "curl -s -o /dev/null -w '%{http_code}' http://localhost:18083 2>&1"),
        ("Backend API", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/docs 2>&1 || echo 'Backend Not Responding'"),
        ("Frontend", "curl -s -o /dev/null -w '%{http_code}' http://localhost:5173 2>&1 || echo 'Frontend Not Responding'"),
        ("EMQX logs", "docker logs frigocore-emqx --tail=10 2>&1"),
        ("Backend logs", "docker logs frigocore-backend --tail=10 2>&1"),
    ], wait_per_cmd=10)

    client.close()
    safe_write(b"\n[DEPLOY COMPLETE]\n")

if __name__ == "__main__":
    main()