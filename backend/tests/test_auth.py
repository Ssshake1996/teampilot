"""Tests for authentication endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    """Test user registration."""
    res = await client.post("/api/v1/auth/register", json={
        "username": "newuser",
        "email": "new@example.com",
        "password": "securepass",
        "full_name": "New User",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "newuser"
    assert data["email"] == "new@example.com"
    assert data["full_name"] == "New User"
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    """Test that duplicate username returns 400."""
    payload = {
        "username": "dupeuser",
        "email": "dupe1@example.com",
        "password": "pass",
        "full_name": "Dupe",
    }
    await client.post("/api/v1/auth/register", json=payload)
    res = await client.post("/api/v1/auth/register", json={
        **payload,
        "email": "dupe2@example.com",
    })
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Test successful login returns access token."""
    await client.post("/api/v1/auth/register", json={
        "username": "loginuser",
        "email": "login@example.com",
        "password": "mypassword",
        "full_name": "Login User",
    })
    res = await client.post("/api/v1/auth/login", json={
        "username": "loginuser",
        "password": "mypassword",
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Test login with wrong password returns 401."""
    await client.post("/api/v1/auth/register", json={
        "username": "wrongpass",
        "email": "wrong@example.com",
        "password": "correct",
        "full_name": "Wrong",
    })
    res = await client.post("/api/v1/auth/login", json={
        "username": "wrongpass",
        "password": "incorrect",
    })
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient, auth_headers):
    """Test /auth/me returns current user info."""
    res = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    """Test /auth/me without token returns 401 or 403."""
    res = await client.get("/api/v1/auth/me")
    assert res.status_code in (401, 403)
