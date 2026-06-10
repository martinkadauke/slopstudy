import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_register(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "alice", "password": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["username"] == "alice"


async def test_login(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "username": "bob", "password": "pass456"},
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "pass456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "bob@example.com"


async def test_duplicate_email(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "username": "user1", "password": "pw1"},
    )
    resp = await client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "username": "user2", "password": "pw2"},
    )
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]


async def test_bad_password(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "carol@example.com", "username": "carol", "password": "correct"},
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "carol@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_protected_route_without_token(client: AsyncClient):
    resp = await client.get("/api/users/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"
