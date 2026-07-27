"""Unit tests for the MQTT Engine."""

from __future__ import annotations

import json

import paho.mqtt.client as mqtt
import pytest

from app.config import Settings
from app.mqtt.client import MQTTEngine


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------

def test_parse_payload_valid() -> None:
    payload = json.dumps({"temperature": 4.2}).encode()
    assert MQTTEngine._parse_payload(payload) == 4.2


def test_parse_payload_negative_temperature() -> None:
    payload = json.dumps({"temperature": -18.5}).encode()
    assert MQTTEngine._parse_payload(payload) == -18.5


def test_parse_payload_integer_temperature() -> None:
    payload = json.dumps({"temperature": 8}).encode()
    result = MQTTEngine._parse_payload(payload)
    assert isinstance(result, float)
    assert result == 8.0


def test_parse_payload_invalid_json() -> None:
    with pytest.raises(ValueError, match="Invalid JSON payload"):
        MQTTEngine._parse_payload(b"not json")


def test_parse_payload_missing_temperature() -> None:
    payload = json.dumps({"other": 123}).encode()
    with pytest.raises(ValueError, match="Missing 'temperature' field"):
        MQTTEngine._parse_payload(payload)


def test_parse_payload_temperature_not_numeric() -> None:
    payload = json.dumps({"temperature": "cold"}).encode()
    with pytest.raises(ValueError, match="Invalid temperature value"):
        MQTTEngine._parse_payload(payload)


# ---------------------------------------------------------------------------
# Callback API version
# ---------------------------------------------------------------------------

def test_client_uses_fixed_arity_callback_api() -> None:
    """paho-mqtt defaults to CallbackAPIVersion.VERSION1, whose on_disconnect
    dispatch has variable arity depending on protocol/packet source — it
    passes only 4 positional args on an unsolicited disconnect over MQTTv5,
    which crashes _on_disconnect's fixed 5-arg signature and kills the
    background network thread permanently. VERSION2 has fixed arity for
    every callback, so the engine must request it explicitly.
    """
    engine = MQTTEngine(Settings(), session_factory=lambda: None)
    assert engine._client._callback_api_version == mqtt.CallbackAPIVersion.VERSION2


def test_on_disconnect_accepts_unsolicited_disconnect_signature() -> None:
    """Simulates the exact call paho makes for a client-detected (non-broker)
    disconnect under CallbackAPIVersion.VERSION2 — must not raise."""
    engine = MQTTEngine(Settings(), session_factory=lambda: None)
    disconnect_flags = mqtt.DisconnectFlags(is_disconnect_packet_from_server=False)
    reason_code = mqtt.ReasonCode(mqtt.PacketTypes.DISCONNECT, "Unspecified error")
    properties = mqtt.Properties(mqtt.PacketTypes.DISCONNECT)
    engine._on_disconnect(
        engine._client, None, disconnect_flags, reason_code, properties
    )