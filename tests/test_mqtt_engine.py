"""Unit tests for the MQTT Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.mqtt.client import MQTTEngine


# ---------------------------------------------------------------------------
# Topic parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("object-slug/sensor-slug", ("object-slug", "sensor-slug")),
        ("frigo/komora-1", ("frigo", "komora-1")),
        ("intermarche-szczytno/komora-2", ("intermarche-szczytno", "komora-2")),
        ("/leading-slash/sensor", ("leading-slash", "sensor")),
        ("object/trailing-slash/", ("object", "trailing-slash")),
    ],
)
def test_parse_topic_valid(topic: str, expected: tuple[str, str]) -> None:
    result = MQTTEngine._parse_topic(topic)
    assert result == expected


@pytest.mark.parametrize(
    "topic",
    [
        "",          # empty
        "no-slash",  # single segment
        "/",         # just a slash
    ],
)
def test_parse_topic_invalid(topic: str) -> None:
    with pytest.raises(ValueError, match="Invalid topic format"):
        MQTTEngine._parse_topic(topic)


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