"""The unauthenticated simulation endpoint must never be served in production."""

from fastapi import FastAPI

from app.main import include_dev_routes


def _paths(environment: str) -> set[str]:
    app = FastAPI()
    include_dev_routes(app, environment)
    return {route.path for route in app.routes}


def test_simulation_endpoint_is_absent_in_production():
    assert not any(path.startswith("/api/v1/sim") for path in _paths("production"))


def test_simulation_endpoint_is_available_for_development():
    assert "/api/v1/sim/simulate/{mqtt_topic:path}" in _paths("development")
