#!/usr/bin/env python3
"""
FrigoCore VPS Update — git pull, restart, verify
"""
import paramiko
import sys
import time

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"


def run_cmd(client, cmd, timeout=60):
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
    print("Connected!")

    # 1. Git pull
    run_cmd(client, f"cd {PROJECT_DIR} && git pull")

    # 2. Down
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose down", timeout=180)

    # 3. Up --build -d
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose up -d --build", timeout=300)

    # 4. Wait for services to initialize
    print("\nWaiting 30 seconds for services to initialize...")
    time.sleep(30)

    # 5. Check status
    run_cmd(client, f"cd {PROJECT_DIR} && docker compose ps")

    # 6. Logs
    print("\n" + "="*60)
    print("LOGS: backend (last 50 lines)")
    print("="*60)
    run_cmd(client, f"docker logs frigocore-backend --tail=50 2>&1")

    print("\n" + "="*60)
    print("LOGS: emqx (last 50 lines)")
    print("="*60)
    run_cmd(client, f"docker logs frigocore-emqx --tail=50 2>&1")

    print("\n" + "="*60)
    print("LOGS: frontend (last 50 lines)")
    print("="*60)
    run_cmd(client, f"docker logs frigocore-frontend --tail=50 2>&1")

    print("\n" + "="*60)
    print("VERIFYING ENDPOINTS...")
    print("="*60)

    run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/docs")
    run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:5173")
    run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:18083")

    client.close()
    print("\nDone!")


if __name__ == "__main__":
    main()