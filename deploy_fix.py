#!/usr/bin/env python3
"""Deploy the ECONNREFUSED fix to VPS."""
import paramiko

HOST = "212.127.91.135"
USER = "root"
PASSWORD = "fY8C488Tj54c"
PROJECT_DIR = "/opt/FrigoCore"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    HOST, username=USER, password=PASSWORD,
    timeout=30, look_for_keys=False, allow_agent=False,
)

def run(cmd, timeout=30):
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.strip())
    if err.strip():
        print("[STDERR]", err.strip())
    return out, err

# 1. Show current vite.config.ts
run(f"cat {PROJECT_DIR}/frontend/vite.config.ts")

# 2. Apply the fix to vite.config.ts
new_vite_config = '''import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: (process.env.VITE_WS_TARGET || "ws://localhost:8000").replace(/^http/, "ws"),
        ws: true,
      },
    },
  },
});
'''

# Write new vite.config.ts
stdin, stdout, stderr = client.exec_command(
    f"cat > {PROJECT_DIR}/frontend/vite.config.ts", timeout=15
)
stdin.write(new_vite_config)
stdin.channel.shutdown_write()
out = stdout.read().decode()
err = stderr.read().decode()
print("VITE WRITE:", out, err)

# 3. Fix docker-compose.yml - change the two VITE_ env vars
# We'll use sed for precision
run(f"cd {PROJECT_DIR} && sed -i 's|VITE_API_BASE_URL: http://localhost:8000|VITE_API_TARGET: http://backend:8000|' docker-compose.yml")
run(f"cd {PROJECT_DIR} && sed -i 's|VITE_WS_URL: ws://localhost:8083|VITE_WS_TARGET: ws://backend:8000|' docker-compose.yml")

# 4. Verify changes
run(f"grep -A 3 'VITE_' {PROJECT_DIR}/docker-compose.yml")

# 5. Restart frontend container
run(f"cd {PROJECT_DIR} && docker compose up -d frontend 2>&1", timeout=120)

# 6. Wait for startup
import time
time.sleep(5)

# 7. Check frontend logs
run("docker logs frigocore-frontend --tail=20 2>&1")

# 8. Test - send POST request through frontend proxy (from within frontend container)
run("docker exec frigocore-frontend wget -q -O - --post-data='{\"name\":\"FixTest\",\"slug\":\"fix-test\",\"description\":\"\"}' --header='Content-Type: application/json' http://localhost:5173/api/v1/objects 2>&1 || echo 'wget not available, trying node'")

# 9. Alternative test via node in frontend container
run('''docker exec frigocore-frontend node -e "
const http = require('http');
const data = JSON.stringify({name:'FixTest2',slug:'fix-test-2',description:''});
const req = http.request({hostname:'localhost',port:5173,path:'/api/v1/objects',method:'POST',headers:{'Content-Type':'application/json','Content-Length':data.length}}, res => {
  let body='';
  res.on('data',chunk=>body+=chunk);
  res.on('end',()=>console.log('HTTP',res.statusCode,body));
});
req.on('error',e=>console.error('Error:',e.message));
req.write(data);
req.end();
" 2>&1''', timeout=15)

client.close()
print("\nDone.")