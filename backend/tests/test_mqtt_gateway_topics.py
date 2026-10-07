"""Gateway liveness/status messages share the frigo/# tree with sensor
telemetry but are not measurements — they must be skipped, not logged as
failed measurement parses."""

from __future__ import annotations

import pytest

from app.mqtt.client import is_gateway_topic


@pytest.mark.parametrize(
    "topic",
    [
        "frigo/kotlety-biskupiec/gateway/heartbeat",
        "frigo/kotlety-biskupiec/gateway/status",
        "frigo/kotlety-biskupiec/gateway/config-ack",
    ],
)
def test_gateway_topics_are_recognized(topic):
    assert is_gateway_topic(topic)


@pytest.mark.parametrize(
    "topic",
    [
        "frigo/kotlety-biskupiec/pego-1/temperature",
        "frigo/warmia/chlodnia",
        "frigo/site/gateways-room/temp",
    ],
)
def test_sensor_topics_are_not_gateway_topics(topic):
    assert not is_gateway_topic(topic)
