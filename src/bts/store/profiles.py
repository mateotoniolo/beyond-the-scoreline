"""User profiles: in memory for local runs and tests, Azure Cosmos DB when configured."""

from __future__ import annotations

import logging
from typing import Protocol

from pydantic import BaseModel

from bts.config import Settings
from bts.insights.schemas import Lang, Profile

log = logging.getLogger(__name__)

CONTAINER = "profiles"
PARTITION_KEY = "/user_id"


class UserProfile(BaseModel):
    user_id: str
    profile: Profile = "fan"
    lang: Lang = "en"
    favorite_team: str | None = None
    favorite_player: str | None = None


class ProfileStore(Protocol):
    async def get(self, user_id: str) -> UserProfile | None: ...
    async def put(self, profile: UserProfile) -> None: ...


class InMemoryProfileStore:
    def __init__(self) -> None:
        self._items: dict[str, UserProfile] = {}

    async def get(self, user_id: str) -> UserProfile | None:
        return self._items.get(user_id)

    async def put(self, profile: UserProfile) -> None:
        self._items[profile.user_id] = profile


class CosmosProfileStore:
    """Profiles in an Azure Cosmos DB (NoSQL) container partitioned by user id."""

    def __init__(self, settings: Settings) -> None:
        if not settings.cosmos_endpoint or not settings.cosmos_key:
            raise ValueError("BTS_COSMOS_ENDPOINT and BTS_COSMOS_KEY are required")
        from azure.cosmos.aio import CosmosClient

        self._client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
        self._database = settings.cosmos_database
        self._container = None

    async def _get_container(self):
        if self._container is None:
            from azure.cosmos import PartitionKey

            database = await self._client.create_database_if_not_exists(id=self._database)
            self._container = await database.create_container_if_not_exists(
                id=CONTAINER, partition_key=PartitionKey(path=PARTITION_KEY)
            )
        return self._container

    async def get(self, user_id: str) -> UserProfile | None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        try:
            item = await container.read_item(item=user_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            return None
        return UserProfile.model_validate({k: v for k, v in item.items() if not k.startswith("_")})

    async def put(self, profile: UserProfile) -> None:
        container = await self._get_container()
        await container.upsert_item({"id": profile.user_id, **profile.model_dump()})


def make_store(settings: Settings) -> ProfileStore:
    if settings.cosmos_endpoint and settings.cosmos_key:
        log.info("profiles: Azure Cosmos DB database %s", settings.cosmos_database)
        return CosmosProfileStore(settings)
    log.info("profiles: in-memory store (no BTS_COSMOS_ENDPOINT)")
    return InMemoryProfileStore()
