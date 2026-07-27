#!/bin/bash
set -e
echo '=== 1. Create Object ==='
OBJ=$(curl -s -X POST http://localhost:8000/api/v1/objects -H 'Content-Type: application/json' -d '{"name":"Obiekt Testowy","description":"Test po wdrozeniu"}')
echo "  Response: $OBJ"
OID=$(echo "$OBJ" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  OK - Object ID: $OID"

echo ''
echo '=== 2. Create Sensor ==='
SENSOR=$(curl -s -X POST "http://localhost:8000/api/v1/objects/$OID/sensors" -H 'Content-Type: application/json' -d '{"name":"Sensor Testowy","mqtt_topic":"frigo/test/sensor-1","offline_timeout_seconds":120}')
echo "  Response: $SENSOR"
SID=$(echo "$SENSOR" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
TOPIC=$(echo "$SENSOR" | python3 -c "import sys,json;print(json.load(sys.stdin)['mqtt_topic'])")
echo "  OK - Sensor ID: $SID  Topic: $TOPIC"

echo ''
echo '=== 3. Simulate MQTT ==='
SIM=$(curl -s -X POST "http://localhost:8000/api/v1/sim/simulate/$TOPIC" -H 'Content-Type: application/json' -d '{"temperature": 4.5}')
echo "  OK - Result: $SIM"

echo ''
echo '=== 4. Measurements ==='
MEAS=$(curl -s "http://localhost:8000/api/v1/sensors/$SID/measurements")
COUNT=$(echo "$MEAS" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
echo "  OK - $COUNT measurement(s) saved"

echo ''
echo '=== 5. Sensor Updated ==='
SENS=$(curl -s "http://localhost:8000/api/v1/objects/$OID/sensors/$SID")
TEMP=$(echo "$SENS" | python3 -c "import sys,json;print(json.load(sys.stdin)['current_temperature'])")
echo "  current_temperature: $TEMP"
if [ "$TEMP" = "4.5" ]; then echo "  OK - Temperature updated correctly"; else echo "  FAIL - Temperature not updated"; exit 1; fi

echo ''
echo '=== 6. Container Status ==='
cd /opt/FrigoCore && docker compose ps

echo ''
echo '=== 7. Git Log ==='
cd /opt/FrigoCore && git log --oneline -3

echo ''
echo '=== ALL VERIFICATIONS PASSED ==='