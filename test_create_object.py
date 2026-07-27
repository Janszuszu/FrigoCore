#!/usr/bin/env python3
"""Test: create object via FrigoCore API on remote VPS."""
import paramiko

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)

# Write test script on remote
script = r"""
import urllib.request, json
d = json.dumps({"name":"TestTemp","slug":"test-temp-xyz","description":"test"}).encode()
r = urllib.request.Request("http://localhost:8000/api/v1/objects", data=d, headers={"Content-Type":"application/json"}, method="POST")
try:
    resp = urllib.request.urlopen(r)
    print("HTTP", resp.status)
    print(resp.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code)
    print(e.read().decode())
"""

stdin, stdout, stderr = client.exec_command("cat > /tmp/test_create.py && python3 /tmp/test_create.py 2>&1", timeout=15)
stdin.write(script)
stdin.channel.shutdown_write()

out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
print("OUT:", out)
print("ERR:", err)
client.close()