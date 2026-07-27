# MicroPython firmware for DS18B20 temperature sensor
# Publishes temperature readings via MQTT
#
# Hardware: ESP8266/ESP32 + DS18B20 on GPIO 4
# MQTT: publishes JSON to frigo/test/komora every 30s

import network
import time
import machine
import onewire
import ds18x20
import ubinascii
import json
from umqtt.simple import MQTTClient

# =====================================================
# KONFIGURACJA
# =====================================================

WIFI_SSID = "Orange_Swiatlowod_8AB2_2.4GHz"
WIFI_PASSWORD = "ASYNNVH5YU3L"

MQTT_HOST = "212.127.91.135"
MQTT_PORT = 1883
MQTT_USER = "firmware"
MQTT_PASSWORD = "firmware123"

MQTT_TOPIC = b"frigo/test/komora"

GPIO_DS18B20 = 4
SEND_INTERVAL = 30

# =====================================================

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

wdt = machine.WDT(timeout=30000)

ow = onewire.OneWire(machine.Pin(GPIO_DS18B20))
ds = ds18x20.DS18X20(ow)

roms = ds.scan()

if not roms:
    print("Nie znaleziono DS18B20")
    while True:
        time.sleep(1)

print("DS18B20 OK")

client = None


def wifi_connect():
    if wlan.isconnected():
        return

    print("Łączenie z WiFi...")

    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    while not wlan.isconnected():
        wdt.feed()
        time.sleep(1)

    print("WiFi OK:", wlan.ifconfig()[0])


def mqtt_connect():
    global client

    print("Łączenie z MQTT...")

    client = MQTTClient(
        client_id=ubinascii.hexlify(machine.unique_id()),
        server=MQTT_HOST,
        port=MQTT_PORT,
        user=MQTT_USER,
        password=MQTT_PASSWORD,
    )

    client.connect()

    print("MQTT OK")


wifi_connect()
mqtt_connect()

print("Start...")

while True:

    try:

        wdt.feed()

        if not wlan.isconnected():
            wifi_connect()
            mqtt_connect()

        ds.convert_temp()

        time.sleep_ms(750)

        temp = ds.read_temp(roms[0])

        payload = json.dumps({
            "temperature": round(temp, 2)
        })

        client.publish(MQTT_TOPIC, payload)

        print("Wysłano:", payload)

    except Exception as e:

        print("Błąd:", e)

        try:
            client.disconnect()
        except:
            pass

        time.sleep(5)

        wifi_connect()
        mqtt_connect()

    for _ in range(SEND_INTERVAL):
        wdt.feed()
        time.sleep(1)