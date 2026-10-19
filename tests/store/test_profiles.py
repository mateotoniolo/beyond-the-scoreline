import os

import pytest

from bts.config import Settings, get_settings
from bts.store.profiles import CosmosProfileStore, InMemoryProfileStore, UserProfile, make_store


async def test_put_then_get_roundtrip():
    store = InMemoryProfileStore()
    await store.put(UserProfile(user_id="u1", profile="analyst", lang="es", favorite_team="t2"))
    got = await store.get("u1")
    assert got is not None and got.lang == "es" and got.favorite_team == "t2"


async def test_get_unknown_returns_none():
    assert await InMemoryProfileStore().get("nobody") is None


def test_make_store_defaults_to_memory(monkeypatch):
    for name in ("BTS_COSMOS_ENDPOINT", "BTS_COSMOS_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(make_store(Settings(_env_file=None)), InMemoryProfileStore)


async def test_profiles_api_roundtrip(client):
    r = await client.put("/api/profiles/u1", json={"profile": "analyst", "lang": "es"})
    assert r.status_code == 200 and r.json()["user_id"] == "u1"
    got = await client.get("/api/profiles/u1")
    assert got.status_code == 200 and got.json()["lang"] == "es"
    assert (await client.get("/api/profiles/nobody")).status_code == 404
    bad = await client.put("/api/profiles/u1", json={"profile": "coach"})
    assert bad.status_code == 422


@pytest.mark.skipif(not os.getenv("BTS_COSMOS_ENDPOINT"), reason="needs a Cosmos DB account")
async def test_cosmos_roundtrip():
    store = CosmosProfileStore(get_settings())
    try:
        await store.put(UserProfile(user_id="test-user", profile="fan", lang="en"))
        got = await store.get("test-user")
        assert got is not None and got.profile == "fan"
    finally:
        await store.close()
