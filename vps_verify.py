#!/usr/bin/env python3
"""
Final verification: endpoints, logs without unicode issues
"""
import paramiko
import sys

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"

def run_cmd(client, cmd, timeout=60):
    print(f"\n{'='*60}")
    print(f"CMD: {cmd}")
    print(f"{'='*60}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("ascii", errors="replace")
    err = stderr.read().decode("ascii", errors="replace")
    exit_code = stdout.channel.recv_exit_status()
    if out:
        sys.stdout.write(out)
    if err:
        sys.stdout.write(err)
    print(f"EXIT: {exit_code}")
    return out, err, exit_code

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST, username=USER, password=PASSWORD,
        timeout=30, look_for_keys=False, allow_agent=False,
    )

    # 1. Git status
    run_cmd(client, f"cd {PROJECT_DIR} && git status")
    run_cmd(client, f"cd {PROJECT_DIR} && git log --oneline -3")

    # 2. Docker compose ps
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose ps")

    # 3. Frontend logs (using cat to avoid terminal escapes)
    run_cmd(client, "docker logs frigocore-frontend --tail=30 2>&1 | cat -v")

    # 4. Endpoint verification
    print("\n--- Verifying endpoints ---")
    for url, label in [
        ("http://localhost:8000/docs", "Backend API"),
        ("http://localhost:5173", "Frontend"),
        ("http://localhost:18083", "EMQX Dashboard"),
    ]:
        stdin, stdout, stderr = client.exec_command(
            'curl -s -o /dev/null -w "%{http_code}" ' + url, timeout=10
        )
        code = stdout.read().decode("ascii", errors="replace").strip()
        err = stderr.read().decode("ascii", errors="replace").strip()
        print(f"  {code} - {label} ({url})")
        if err:
            print(f"  stderr: {err}")

    # 5. Health check
    print("\n--- Health status ---")
    stdin, stdout, stderr = client.exec_command(
        "docker inspect --format='{{.Name}} {{.State.Status}}/{{.State.Health.Status}}' "
        "frigocore-postgres frigocore-redis frigocore-emqx "
        "frigocore-backend frigocore-frontend", timeout=10
    )
    out = stdout.read().decode("ascii", errors="replace")
    sys.stdout.write(out)

    # 6. Check listening ports
    print("\n--- Listening ports ---")
    run_cmd(client, "ss -tlnp 2>&1 | head -20")

    client.close()
    print("\nDone!")

if __name__ == "__main__":
    main()