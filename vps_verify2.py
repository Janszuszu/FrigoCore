#!/usr/bin/env python3
"""
Final verification - handle cp1250 encoding properly
"""
import paramiko
import sys

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"

def safe_write(data):
    """Write binary data safely avoiding cp1250 encoding errors."""
    if isinstance(data, str):
        data = data.encode("ascii", errors="replace")
    try:
        sys.stdout.buffer.write(data)
    except Exception:
        sys.stdout.write(data.decode("ascii", errors="replace"))
    sys.stdout.flush()

def run_cmd(client, cmd, timeout=60):
    safe_write(f"\n{'='*60}\nCMD: {cmd}\n{'='*60}\n".encode())
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read()
    err = stderr.read()
    exit_code = stdout.channel.recv_exit_status()
    if out:
        safe_write(out)
    if err:
        safe_write(err)
    safe_write(f"EXIT: {exit_code}\n".encode())
    return out, exit_code

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST, username=USER, password=PASSWORD,
        timeout=30, look_for_keys=False, allow_agent=False,
    )

    # 1. Fix git: stash, pull, drop stash
    safe_write(b"\n--- Fixing git (stash+pull) ---\n")
    stdin, stdout, stderr = client.exec_command(
        f"cd {PROJECT_DIR} && git stash && git pull && git stash drop", timeout=30
    )
    out = stdout.read()
    err = stderr.read()
    if out:
        safe_write(out)
    if err:
        safe_write(err)

    # 2. Git status + log
    run_cmd(client, f"cd {PROJECT_DIR} && git status")
    run_cmd(client, f"cd {PROJECT_DIR} && git log --oneline -3")

    # 3. Docker compose ps
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose ps")

    # 4. Health status
    safe_write(b"\n--- Health status ---\n")
    stdin, stdout, stderr = client.exec_command(
        "docker inspect --format='{{.Name}} {{.State.Status}}/{{.State.Health.Status}}' "
        "frigocore-postgres frigocore-redis frigocore-emqx "
        "frigocore-backend frigocore-frontend", timeout=10
    )
    safe_write(stdout.read())

    # 5. Backend logs
    safe_write(b"\n--- Backend logs (last 30 lines) ---\n")
    run_cmd(client, "docker logs frigocore-backend --tail=30 2>&1 | cat -v")

    # 6. EMQX logs
    safe_write(b"\n--- EMQX logs (last 30 lines) ---\n")
    run_cmd(client, "docker logs frigocore-emqx --tail=30 2>&1 | cat -v")

    # 7. Frontend logs
    safe_write(b"\n--- Frontend logs (last 30 lines) ---\n")
    run_cmd(client, "docker logs frigocore-frontend --tail=30 2>&1 | cat -v")

    # 8. Endpoint verification
    safe_write(b"\n--- Verifying endpoints ---\n")
    for url, label in [
        ("http://localhost:8000/docs", "Backend API"),
        ("http://localhost:5173", "Frontend"),
        ("http://localhost:18083", "EMQX Dashboard"),
    ]:
        stdin, stdout, stderr = client.exec_command(
            'curl -s -o /dev/null -w "%{http_code}" ' + url, timeout=10
        )
        code = stdout.read().decode("ascii", errors="replace").strip()
        safe_write(f"  {code} - {label} ({url})\n".encode())

    # 9. Listening ports
    safe_write(b"\n--- Listening ports ---\n")
    run_cmd(client, "ss -tlnp 2>&1 | head -20 | cat -v")

    client.close()
    print("\nDone!")

if __name__ == "__main__":
    main()