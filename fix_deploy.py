#!/usr/bin/env python3
"""
FrigoCore VPS — Poprawka i wdrożenie
1. Wgrywa poprawiony docker-compose.yml na VPS
2. Restartuje EMQX z nowym healthcheckiem
3. Uruchamia backend i frontend
4. Weryfikuje końcowy stan
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


def run_command(client, cmd, timeout=120):
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
    print("FrigoCore VPS — Fix & Deploy")

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

    # 1. Wgraj poprawiony docker-compose.yml przez git (bo projekt jest w git repo na VPS)
    # Najpierw skopiuj lokalny plik na VPS przez scp albo git push
    # Ponieważ nie mamy SCP bezpośrednio, użyjemy prostego podejścia:
    # Przetworzymy plik lokalnie i wyślemy przez echo/cat heredoc na VPS.

    # Odczytaj poprawiony docker-compose.yml lokalnie
    with open("docker-compose.yml", "r", encoding="utf-8") as f:
        compose_content = f.read()

    print("\n--- Uploading fixed docker-compose.yml to VPS ---")
    # Użyj bezpośredniego SCP przez paramiko
    sftp = client.open_sftp()
    try:
        sftp.put("docker-compose.yml", f"{PROJECT_DIR}/docker-compose.yml")
        print("[OK] docker-compose.yml uploaded.")
    finally:
        sftp.close()

    # 2. Zatrzymaj stare kontenery
    run_command(client, f"cd {PROJECT_DIR} && docker compose stop emqx 2>&1")
    run_command(client, f"cd {PROJECT_DIR} && docker compose rm -f emqx 2>&1")

    # 3. Uruchom ponownie EMQX
    run_command(client, f"cd {PROJECT_DIR} && docker compose up -d emqx 2>&1", timeout=60)

    # 4. Czekaj aż EMQX będzie healthy
    print("\n--- Waiting for EMQX to become healthy (max 60s)... ---")
    for i in range(12):
        time.sleep(5)
        out, _ = run_command(client, f"cd {PROJECT_DIR} && docker compose ps emqx --format json 2>&1")
        if "healthy" in out.lower():
            print("[OK] EMQX is now healthy!")
            break
        print(f"  ... still waiting ({i+1} * 5s) ...")
    else:
        print("[WARN] Timeout waiting for EMQX health. Checking status...")
        run_command(client, f"cd {PROJECT_DIR} && docker compose ps emqx 2>&1")

    # 5. Uruchom backend
    run_command(client, f"cd {PROJECT_DIR} && docker compose up -d backend 2>&1", timeout=60)

    # 6. Czekaj chwilę i sprawdź backend
    time.sleep(5)
    run_command(client, f"cd {PROJECT_DIR} && docker compose ps 2>&1")
    run_command(client, "docker logs frigocore-backend --tail=50 2>&1")

    # 7. Uruchom frontend
    run_command(client, f"cd {PROJECT_DIR} && docker compose up -d frontend 2>&1", timeout=60)

    # 8. Czekaj i sprawdź frontend
    time.sleep(5)
    run_command(client, "docker logs frigocore-frontend --tail=30 2>&1")

    # 9. Końcowy stan
    print("\n\n============================================")
    print("FINAL STATUS")
    print("============================================")
    run_command(client, f"cd {PROJECT_DIR} && docker compose ps 2>&1")

    # 10. EMQX logs
    run_command(client, "docker logs frigocore-emqx --tail=10 2>&1")

    # 11. Backend API test
    run_command(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/docs 2>&1 || echo 'Backend not responding'")

    # 12. Frontend test
    run_command(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:5173 2>&1 || echo 'Frontend not responding'")

    client.close()
    print("\n\n============================================")
    print("FIX & DEPLOY COMPLETE")
    print("============================================")


if __name__ == "__main__":
    main()