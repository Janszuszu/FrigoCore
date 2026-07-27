#!/usr/bin/env python3
"""VPS Diagnostics - pinpoint MQTT communication break."""
import paramiko
import sys

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"

def run(client, cmd, timeout=15):
    print(f"\n{'='*60}")
    print(f"$ {cmd}")
    print(f"{'='*60}")
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out.strip():
            print(out)
        if err.strip():
            print(f"[STDERR] {err}")
    except Exception as e:
        print(f"[ERROR] {e}")

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)
    print("[OK] SSH connected")

    # 1. Backend .env file
    run(client, "cat /opt/FrigoCore/backend/.env 2>/dev/null || echo 'NO .ENV FILE'")

    # 2. Backend environment variables (MQTT)
    run(client, "docker inspect frigocore-backend | python3 -c \"import sys,json; d=json.load(sys.stdin); env={e.split('=',1)[0]: e.split('=',1)[1] for e in d[0]['Config']['Env']}; [print(f'{k}={v}') for k,v in sorted(env.items()) if 'MQTT' in k or 'EMQX' in k]\" 2>/dev/null || echo 'INSPECT FAILED'")

    # 3. EMQX config - auth/ACL
    run(client, "docker exec frigocore-emqx sh -c 'ls /opt/emqx/etc/*.conf /opt/emqx/etc/*.acl 2>/dev/null'")
    run(client, "docker exec frigocore-emqx sh -c 'cat /opt/emqx/etc/emqx.conf 2>/dev/null | head -200'")
    run(client, "docker exec frigocore-emqx sh -c 'cat /opt/emqx/etc/acl.conf 2>/dev/null; cat /opt/emqx/etc/authz.conf 2>/dev/null; cat /opt/emqx/data/authz/acl.conf 2>/dev/null; echo \"---NO ACL FILES---\"'")

    # 4. Connected clients
    run(client, "docker exec frigocore-emqx emqx ctl clients list 2>/dev/null || docker exec frigocore-emqx emqx_ctl clients list 2>/dev/null || echo 'CLIENTS LIST FAILED'")
    run(client, "docker exec frigocore-emqx emqx ctl status 2>/dev/null || docker exec frigocore-emqx emqx_ctl status 2>/dev/null || echo 'STATUS FAILED'")

    # 5. EMQX subscriptions
    run(client, "docker exec frigocore-emqx emqx ctl subscriptions list 2>/dev/null || docker exec frigocore-emqx emqx_ctl subscriptions list 2>/dev/null || echo 'SUBS LIST FAILED'")

    # 6. Backend logs with MQTT keywords
    run(client, "docker logs frigocore-backend --tail=200 2>&1 | grep -i -E 'mqtt|subscribe|connect|auth|permission|denied|error|warning' || echo 'NO MATCHING LOGS'")

    # 7. Full backend startup logs
    run(client, "docker logs frigocore-backend --tail=50 2>&1 | head -50")

    # 8. EMQX logs - authorization failures
    run(client, "docker logs frigocore-emqx --tail=100 2>&1 | grep -i -E 'auth|acl|denied|permission|subscribe' || echo 'NO MATCHING LOGS'")

    # 9. Check if backend container can reach EMQX
    run(client, "docker exec frigocore-backend sh -c 'timeout 2 bash -c \"echo > /dev/tcp/emqx/1883\" 2>/dev/null && echo \"BACKEND -> EMQX: OK\" || echo \"BACKEND -> EMQX: FAILED\"'")

    # 10. Check ESP published messages (if any)
    run(client, "docker logs frigocore-emqx --tail=500 2>&1 | grep -i -E 'publish|frigo/test/komora|received' | tail -50 || echo 'NO MESSAGES FOUND'")

    client.close()
    print("\n\n=== DIAGNOSIS COMPLETE ===")

if __name__ == "__main__":
    main()