"""Refresh tokens keep the phone app signed in past the access token's life."""

from __future__ import annotations

import pytest

from app.core.security import create_refresh_token, hash_password
from app.enums import UserRole


async def _login(client, user):
    resp = await client.post("/api/v1/auth/login", json={"username": user.username, "password": "pw12345"})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_login_returns_refresh_token_and_refresh_gives_new_pair(client, make_user):
    jan = await make_user(UserRole.USER)
    body = await _login(client, jan)
    assert body["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert resp.status_code == 200, resp.text
    pair = resp.json()
    assert pair["user"]["id"] == str(jan.id)
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_is_not_a_bearer_and_access_token_cannot_refresh(client, make_user):
    jan = await make_user(UserRole.USER)
    body = await _login(client, jan)
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['refresh_token']}"})
    assert me.status_code == 401
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": body["access_token"]})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_refused_after_password_change_or_deactivation(client, db_session, make_user):
    jan = await make_user(UserRole.USER)
    token = create_refresh_token(jan)
    jan.hashed_password = hash_password("nowe-haslo")
    await db_session.commit()
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401

    ola = await make_user(UserRole.USER)
    token = create_refresh_token(ola)
    ola.is_active = False
    await db_session.commit()
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401
