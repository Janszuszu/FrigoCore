#!/usr/bin/env python3
"""
Fix VPS: stash local changes, git pull, restart
"""
import paramiko
import sys
import time

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"


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

    # Step 1: Stash local changes and pull
    cmds = [
        (f"cd {PROJECT_DIR} && git stash", "Stash local changes"),
        (f"cd {PROJECT_DIR} && git pull", "Git pull"),
        (f"cd {PROJECT_DIR} && git stash drop", "Drop stash"),
    ]

    for cmd, desc in cmds:
        print(f"\n{'='*60}")
        print(f">>> {desc}")
        print(f"{'='*60}")
        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out:
            sys.stdout.write(out)
        if err:
            sys.stderr.write(err)

    # Step 2: Docker compose up -d --build
    print(f"\n{'='*60}")
    print(">>> Starting docker compose up -d --build...")
    print(f"{'='*60}")

    stdin, stdout, stderr = client.exec_command(
        f"cd {PROJECT_DIR} && docker compose up -d --build",
        timeout=300
    )
    
    # Stream output in real-time
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            data = stdout.channel.recv(8192)
            sys.stdout.write(data.decode("utf-8", errors="replace"))
            sys.stdout.flush()
        if stderr.channel.recv_ready():
            data = stderr.channel.recv(8192)
            sys.stderr.write(data.decode("utf-8", errors="replace"))
            sys.stderr.flush()
        time.sleep(0.5)

    # Get remaining
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)

    print("\nWaiting 20s for initialization...")
    time.sleep(20)

    # Step 3: docker compose ps
    print(f"\n{'='*60}")
    print(">>> docker compose ps")
    print(f"{'='*60}")
    stdin, stdout, stderr = client.exec_command(f"cd {PROJECT_DIR} && docker compose ps", timeout=10)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)

    # Step 4: Check health
    print(f"\n{'='*60}")
    print(">>> Health status of all containers")
    print(f"{'='*60}")
    stdin, stdout, stderr = client.exec_command(
        "docker inspect --format='{{.Name}} {{.State.Health.Status}}' "
        "frigocore-postgres frigocore-redis frigocore-emqx "
        "frigocore-backend frigocore-frontend 2>&1",
        timeout=10
    )
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)

    # Step 5: Logs
    containers = [
        ("backend", "frigocore-backend"),
        ("emqx", "frigocore-emqx"),
        ("frontend", "frigocore-frontend"),
    ]
    for name, cname in containers:
        print(f"\n{'='*60}")
        print(f">>> LOGS: {name} (last 50)")
        print(f"{'='*60}")
        stdin, stdout, stderr = client.exec_command(f"docker logs {cname} --tail=50 2>&1", timeout=10)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out:
            sys.stdout.write(out)
        if err:
            sys.stderr.write(err)

    # Step 6: Verify endpoints
    print(f"\n{'='*60}")
    print(">>> VERIFYING ENDPOINTS")
    print(f"{'='*60}")
    for url, label in [
        ("http://localhost:8000/docs", "Backend API"),
        ("http://localhost:5173", "Frontend"),
        ("http://localhost:18083", "EMQX Dashboard"),
    ]:
        stdin, stdout, stderr = client.exec_command(
            f'curl -s -o /dev/null -w "%{{http_code}}" {url}', timeout=10
        )
        code = stdout.read().decode("utf-8", errors="replace").strip()
        print(f"  {code} - {label} ({url})")

    client.close()
    print("\nDone!")


if __name__ == "__main__":
    main()