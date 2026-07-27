#!/usr/bin/env python3
"""
FrigoCore VPS — Diagnostyka Docker
Łączy się przez SSH i wykonuje wszystkie kroki diagnostyczne.
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


def run_command(client, cmd, timeout=30):
    """Run a single command via SSH and return output."""
    print(f"\n{'='*70}")
    print(f"$ {cmd}")
    print(f"{'='*70}")
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read()
        err = stderr.read()
        if out:
            safe_write(out)
        if err:
            safe_write(b"\n[STDERR]\n")
            safe_write(err)
        return out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[ERROR] {e}")
        return "", str(e)


def main():
    print("FrigoCore VPS — Diagnostyka Docker")
    print(f"Host: {HOST}")
    print(f"Project: {PROJECT_DIR}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=HOST,
            username=USER,
            password=PASSWORD,
            timeout=30,
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception as e:
        print(f"[FATAL] SSH connection failed: {e}")
        sys.exit(1)

    print("\n[OK] SSH connected.\n")

    # --- 1. docker compose ps ---
    run_command(client, f"cd {PROJECT_DIR} && docker compose ps 2>&1")

    # --- 2. docker logs emqx ---
    run_command(client, "docker logs frigocore-emqx --tail=200 2>&1")

    # --- 3. docker inspect emqx (by container name) ---
    run_command(client, "docker inspect frigocore-emqx 2>&1 | head -200")

    # --- 4. Sprawdź czy emqx ping istnieje w obrazie ---
    run_command(client, "docker exec frigocore-emqx which emqx 2>&1")
    run_command(client, "docker exec frigocore-emqx emqx ping 2>&1")
    run_command(client, "docker exec frigocore-emqx emqx --help 2>&1 | head -30")

    # --- 5. Sprawdź wersję EMQX ---
    run_command(client, "docker exec frigocore-emqx emqx versions 2>&1")

    # --- 6. Sprawdź dostępne subkomendy emqx ---
    run_command(client, "docker exec frigocore-emqx ls /opt/emqx/bin/ 2>&1")

    # --- 7. Sprawdź czy broker nasłuchuje na porcie MQTT ---
    run_command(client, "docker exec frigocore-emqx netstat -tlnp 2>&1 || docker exec frigocore-emqx ss -tlnp 2>&1")

    # --- 8. Backend logs ---
    run_command(client, "docker logs frigocore-backend --tail=100 2>&1")

    # --- 9. Frontend logs ---
    run_command(client, "docker logs frigocore-frontend --tail=100 2>&1")

    # --- 10. Docker compose config (healthchecki) ---
    run_command(client, f"cd {PROJECT_DIR} && docker compose config 2>&1 | head -80")

    # --- 11. Sprawdź EMQX Dashboard ---
    run_command(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:18083 2>&1")

    # --- 12. Sprawdź MQTT port ---
    run_command(client, "timeout 2 bash -c 'echo > /dev/tcp/localhost/1883 && echo \"MQTT port OPEN\" || echo \"MQTT port CLOSED\"' 2>&1")

    client.close()
    print("\n\n============================================")
    print("DIAGNOSTYKA ZAKOŃCZONA")
    print("============================================")


if __name__ == "__main__":
    main()