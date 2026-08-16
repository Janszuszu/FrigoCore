"""Device token (FCM) registration, update, removal, multi-device support."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.enums import UserRole
from app.models.device_token import DeviceToken

from .conftest import auth_headers


@pytest.mark.asyncio
async def test_register_device(client, make_user):
    jan = await make_user(UserRole.SERWISANT)
    resp = await client.post(
        "/api/v1/devices/register",
        json={"fcm_token": "token-abc", "platform": "android"},
        headers=auth_headers(jan),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_id"] == str(jan.id)
    assert body["platform"] == "android"
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_register_same_token_updates_in_place(client, make_user):
    jan = await make_user(UserRole.SERWISANT)
    first = await client.post(
        "/api/v1/devices/register",
        json={"fcm_token": "token-shared", "platform": "android"},
        headers=auth_headers(jan),
    )
    second = await client.post(
        "/api/v1/devices/register",
        json={"fcm_token": "token-shared", "platform": "ios"},
        headers=auth_headers(jan),
    )
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["platform"] == "ios"


@pytest.mark.asyncio
async def test_multiple_devices_per_user(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    await client.post(
        "/api/v1/devices/register", json={"fcm_token": "phone-1", "platform": "android"}, headers=auth_headers(jan)
    )
    await client.post(
        "/api/v1/devices/register", json={"fcm_token": "tablet-1", "platform": "android"}, headers=auth_headers(jan)
    )
    result = await db_session.execute(select(DeviceToken).where(DeviceToken.user_id == jan.id))
    tokens = result.scalars().all()
    assert len(tokens) == 2
    assert {t.fcm_token for t in tokens} == {"phone-1", "tablet-1"}


@pytest.mark.asyncio
async def test_serwisant_cannot_manage_escalation_policies(client, make_user):
    jan = await make_user(UserRole.SERWISANT)
    resp = await client.get("/api/v1/escalation-policies", headers=auth_headers(jan))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_own_device(client, make_user):
    jan = await make_user(UserRole.SERWISANT)
    reg = await client.post(
        "/api/v1/devices/register", json={"fcm_token": "to-delete", "platform": "android"}, headers=auth_headers(jan)
    )
    device_id = reg.json()["id"]
    resp = await client.delete(f"/api/v1/devices/{device_id}", headers=auth_headers(jan))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_delete_others_device(client, make_user):
    jan = await make_user(UserRole.SERWISANT)
    piotr = await make_user(UserRole.SERWISANT)
    reg = await client.post(
        "/api/v1/devices/register", json={"fcm_token": "jans-device", "platform": "android"}, headers=auth_headers(jan)
    )
    device_id = reg.json()["id"]
    resp = await client.delete(f"/api/v1/devices/{device_id}", headers=auth_headers(piotr))
    assert resp.status_code == 403
