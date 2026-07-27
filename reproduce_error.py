#!/usr/bin/env python3
"""Reproduce the 500 error by sending the exact same request the frontend sends."""
import paramiko, time

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)

# Step 1: Delete test object from previous run
stdin, stdout, stderr = client.exec_command(
    "docker exec frigocore-backend python3 -c \""
    "import asyncio; from app.database import async_session_factory; from app.models.object import Object; from sqlalchemy import select; "
    "async def main(): async with async_session_factory() as db: obj = await db.scalar(select(Object).where(Object.slug=='test-temp-xyz')); "
    "if obj: await db.delete(obj); await db.commit(); print('deleted'); else: print('not found'); "
    "asyncio.run(main())\" 2>&1",
    timeout=15
)
print("DELETE:", stdout.read().decode())

# Step 2: Wait a moment
time.sleep(1)

# Step 3: Send the POST request exactly as frontend does (description may be empty string)
send_script = r"""
import urllib.request, json
# Frontend sends: {name, slug, description?: string}
# Test with empty string description (common case)
data = json.dumps({"name":"TestFrontend","slug":"test-frontend","description":""}).encode()
req = urllib.request.Request("http://localhost:8000/api/v1/objects", data=data, headers={"Content-Type":"application/json"}, method="POST")
try:
    resp = urllib.request.urlopen(req)
    print("OK HTTP", resp.status, resp.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code, e.read().decode())
except Exception as ex:
    print("EXCEPTION:", ex)
"""

stdin, stdout, stderr = client.exec_command("cat > /tmp/repro_test.py && python3 /tmp/repro_test.py 2>&1", timeout=15)
stdin.write(send_script)
stdin.channel.shutdown_write()
print("RESPONSE:", stdout.read().decode())

# Step 4: Immediately grab logs - look for errors
stdin2, stdout2, stderr2 = client.exec_command(
    "docker logs frigocore-backend 2>&1 | grep -i -E 'error|traceback|exception|500|File.*line' | tail -50",
    timeout=15
)
print("ERROR LOGS:")
print(stdout2.read().decode())

client.close()