#!/usr/bin/env python3
"""Test the fix by sending a POST through frontend's Vite proxy."""
import paramiko, sys

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)

node_script = r"""
const http = require('http');
const data = JSON.stringify({name:'FixTest3',slug:'fix-test-3',description:''});
const req = http.request({
  hostname: 'localhost',
  port: 5173,
  path: '/api/v1/objects',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Content-Length': data.length
  }
}, res => {
  let body = '';
  res.on('data', chunk => body += chunk);
  res.on('end', () => console.log('HTTP', res.statusCode, body));
});
req.on('error', e => console.error('ERR:', e.message));
req.write(data);
req.end();
"""

stdin, stdout, stderr = client.exec_command(
    "cat > /tmp/test_fix.js && docker exec -i frigocore-frontend node < /tmp/test_fix.js 2>&1",
    timeout=15
)
stdin.write(node_script)
stdin.channel.shutdown_write()
out = stdout.read()
err = stderr.read()
sys.stdout.buffer.write(out)
if err:
    sys.stderr.buffer.write(err)

client.close()