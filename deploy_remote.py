#!/usr/bin/env python3
"""
FrigoCore Remote Deployment via Git
Step 1: SSH -> handle password expiry -> reconnect
Step 2: SSH again -> git pull/clone -> docker compose up
"""

import paramiko
import sys
import time
import os

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
NEW_PASSWORD = "fY8C488Tj54c"
REPO_URL = "https://github.com/Janszuszu/FrigoCore.git"
PROJECT_DIR = "/opt/FrigoCore"


def safe_write(data: bytes):
    """Write binary data to stdout safely (avoid unicode errors on win cp1250)"""
    try:
        sys.stdout.buffer.write(data)
    except Exception:
        # Fallback: strip non-ascii
        text = data.decode("ascii", errors="replace")
        sys.stdout.write(text)
    sys.stdout.flush()


def connect():
    """Create SSH connection"""
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
    return client


def step1_change_password():
    """
    Connect, detect expired password, change via interactive shell.
    After password change, the connection will be closed by server.
    """
    print("=" * 60)
    print("STEP 1: Handle password expiry")
    print("=" * 60)

    client = connect()
    channel = client.invoke_shell(width=160, height=50)
    time.sleep(2)

    # Collect initial output
    output = b""
    while channel.recv_ready():
        output += channel.recv(4096)
        time.sleep(0.2)
    time.sleep(0.5)
    while channel.recv_ready():
        output += channel.recv(4096)
        time.sleep(0.2)

    output_str = output.decode("utf-8", errors="replace")
    print(f"[INITIAL]\n{output_str}\n[/INITIAL]")

    if "expired" not in output_str.lower():
        print("Password not expired. Trying exec_command...")
        channel.close()
        client.close()
        return

    # Wait for "New password:" prompt if not already there
    waited = 0
    while "password" not in output_str.lower() and waited < 10:
        time.sleep(0.5)
        waited += 0.5
        if channel.recv_ready():
            chunk = channel.recv(4096)
            output += chunk
            safe_write(chunk)
            output_str = output.decode("utf-8", errors="replace")

    print("\n--- Sending new password ---")
    channel.send(NEW_PASSWORD + "\n")
    time.sleep(1)

    output = b""
    while channel.recv_ready():
        output += channel.recv(4096)
        time.sleep(0.2)
    time.sleep(0.5)
    while channel.recv_ready():
        output += channel.recv(4096)
        time.sleep(0.2)

    output_str = output.decode("utf-8", errors="replace")
    print(output_str)

    if "retype" in output_str.lower() or "password" in output_str.lower():
        print("--- Sending retype password ---")
        channel.send(NEW_PASSWORD + "\n")
        time.sleep(1)

        output = b""
        while channel.recv_ready():
            output += channel.recv(4096)
            time.sleep(0.2)
        time.sleep(0.5)
        while channel.recv_ready():
            output += channel.recv(4096)
            time.sleep(0.2)

        output_str = output.decode("utf-8", errors="replace")
        print(output_str)

    time.sleep(1)
    while channel.recv_ready():
        output += channel.recv(4096)
        time.sleep(0.2)

    channel.close()
    client.close()
    print("STEP 1 COMPLETE - Password changed, waiting for reconnect...\n")
    time.sleep(2)


def step2_deploy():
    """Reconnect after password change and run deployment commands"""
    print("=" * 60)
    print("STEP 2: Deploy via Git + Docker Compose")
    print("=" * 60)

    client = connect()
    channel = client.invoke_shell(width=160, height=50)
    time.sleep(2)

    # Read initial shell prompt
    output = b""
    while channel.recv_ready():
        output += channel.recv(4096)
        time.sleep(0.2)
    safe_write(output)

    output_str = output.decode("utf-8", errors="replace")
    if "expired" in output_str.lower():
        print("\n!!! Password STILL expired! Something went wrong. !!!")
        channel.close()
        client.close()
        return

    commands = [
        ("System info", "uname -a"),
        ("OS", "cat /etc/os-release | head -3"),
        ("Disk", "df -h / | tail -2"),
        ("Memory", "free -h | head -2"),
        ("Docker check", "docker --version 2>&1 || echo 'DOCKER_MISSING'"),
        ("Compose check", "docker compose version 2>&1 || echo 'COMPOSE_MISSING'"),
        ("Git check", "git --version 2>&1 || echo 'GIT_MISSING'"),
        ("Install Docker if missing",
            "if ! command -v docker >/dev/null 2>&1; then "
            "echo '>>> Installing Docker...' && "
            "curl -fsSL https://get.docker.com | sh && "
            "systemctl enable docker && systemctl start docker && "
            "echo '>>> Docker installed!'; "
            "else echo '>>> Docker already installed'; fi"),
        ("Install Compose if missing",
            "if ! docker compose version >/dev/null 2>&1; then "
            "echo '>>> Installing Docker Compose...' && "
            "apt-get update -y -qq && apt-get install -y -qq docker-compose-plugin && "
            "echo '>>> Compose installed!'; "
            "else echo '>>> Compose already installed'; fi"),
        ("Install Git if missing",
            "if ! command -v git >/dev/null 2>&1; then "
            "echo '>>> Installing Git...' && "
            "apt-get update -y -qq && apt-get install -y -qq git && "
            "echo '>>> Git installed!'; "
            "else echo '>>> Git already installed'; fi"),
        ("Git pull/clone",
            f"if [ -d {PROJECT_DIR} ]; then "
            f"echo '>>> Project exists, pulling...' && cd {PROJECT_DIR} && git pull origin main 2>&1 && echo '>>> Pull done!'; "
            f"else echo '>>> Cloning repo...' && git clone {REPO_URL} {PROJECT_DIR} && echo '>>> Clone done!'; fi"),
        ("Stop old containers",
            f"cd {PROJECT_DIR} && docker compose down 2>&1 || echo 'Nothing to stop'"),
        ("Pull images",
            f"cd {PROJECT_DIR} && docker compose pull 2>&1"),
        ("Build images",
            f"cd {PROJECT_DIR} && docker compose build 2>&1"),
        ("Start services",
            f"cd {PROJECT_DIR} && docker compose up -d 2>&1"),
        ("Container status",
            f"cd {PROJECT_DIR} && docker compose ps 2>&1"),
        ("Listening ports",
            "ss -tlnp 2>&1 | head -25"),
    ]

    for desc, cmd in commands:
        print(f"\n>>> {desc}")
        print(f"    $ {cmd}")
        channel.send(cmd + "\n")
        time.sleep(0.5)

        cmd_output = b""
        waited = 0
        max_wait = 120 if "apt-get" in cmd or "curl" in cmd or "docker compose" in cmd or "Install" in desc else 20

        while waited < max_wait:
            time.sleep(0.5)
            waited += 0.5
            if channel.recv_ready():
                chunk = channel.recv(8192)
                cmd_output += chunk
                safe_write(chunk)
                waited = 0

            output_str_check = cmd_output.decode("utf-8", errors="replace")
            if output_str_check.rstrip().endswith("#") or output_str_check.rstrip().endswith("$"):
                time.sleep(0.3)
                if channel.recv_ready():
                    chunk = channel.recv(4096)
                    cmd_output += chunk
                    safe_write(chunk)
                break

        print()

    channel.close()
    client.close()

    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE!")
    print("=" * 60)
    print(f"""
Services should be available at:
  Frontend:    http://{HOST}:5173
  Backend API: http://{HOST}:8000/docs
  EMQX Dashboard: http://{HOST}:18083 (admin / frigocore_admin_dev)
  PostgreSQL:  {HOST}:5432
  MQTT:        {HOST}:1883
    """)


def main():
    try:
        step1_change_password()
        step2_deploy()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()