"""AIP reference-data provider interface.

Return types are ORM rows scoped to a single active AipDataset -- callers
never need to know whether that dataset came from the interim seed JSON or
a real AIP/eAIP/AIXM import. `UnavailableAipProvider` is the placeholder
for the latter: it fails loudly rather than silently serving nothing, so a
misconfigured `aip_provider` setting is obvious rather than a quiet gap.
"""

from functools import lru_cache
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Aerodrome, AipDataset, Fir


class AipProvider(Protocol):
    async def dataset_metadata(self, session: AsyncSession) -> AipDataset | None: ...

    async def list_firs(self, session: AsyncSession) -> list[Fir]: ...

    async def list_aerodromes(
        self, session: AsyncSession, query: str | None = None
    ) -> list[Aerodrome]: ...

    async def get_aerodrome(self, session: AsyncSession, icao_code: str) -> Aerodrome | None: ...


class SeedAipProvider:
    """Reads whichever AipDataset is currently marked active."""

    async def dataset_metadata(self, session: AsyncSession) -> AipDataset | None:
        result: AipDataset | None = await session.scalar(
            select(AipDataset).where(AipDataset.active.is_(True))
        )
        return result

    async def list_firs(self, session: AsyncSession) -> list[Fir]:
        dataset = await self.dataset_metadata(session)
        if dataset is None:
            return []
        return list(await session.scalars(select(Fir).where(Fir.dataset_id == dataset.id)))

    async def list_aerodromes(
        self, session: AsyncSession, query: str | None = None
    ) -> list[Aerodrome]:
        dataset = await self.dataset_metadata(session)
        if dataset is None:
            return []
        statement = select(Aerodrome).where(Aerodrome.dataset_id == dataset.id)
        if query:
            term = f"%{query}%"
            statement = statement.where(
                Aerodrome.icao_code.ilike(term) | Aerodrome.name.ilike(term)
            )
        return list(await session.scalars(statement))

    async def get_aerodrome(self, session: AsyncSession, icao_code: str) -> Aerodrome | None:
        dataset = await self.dataset_metadata(session)
        if dataset is None:
            return None
        result: Aerodrome | None = await session.scalar(
            select(Aerodrome).where(
                Aerodrome.dataset_id == dataset.id, Aerodrome.icao_code == icao_code.upper()
            )
        )
        return result


class UnavailableAipProvider:
    """Placeholder for a real AIP/eAIP/AIXM-backed provider. Every method
    raises -- there is no live feed connected yet, and pretending otherwise
    by returning an empty list would be indistinguishable from "this dataset
    genuinely has no aerodromes", which is a dangerous ambiguity in a
    reference-data lookup."""

    def __init__(self, kind: str) -> None:
        self.kind = kind

    def _unavailable(self) -> NotImplementedError:
        return NotImplementedError(
            f"AIP provider '{self.kind}' is not connected yet. Configure "
            "settings.aip_provider='seed' until a real feed is available."
        )

    async def dataset_metadata(self, session: AsyncSession) -> AipDataset | None:
        raise self._unavailable()

    async def list_firs(self, session: AsyncSession) -> list[Fir]:
        raise self._unavailable()

    async def list_aerodromes(
        self, session: AsyncSession, query: str | None = None
    ) -> list[Aerodrome]:
        raise self._unavailable()

    async def get_aerodrome(self, session: AsyncSession, icao_code: str) -> Aerodrome | None:
        raise self._unavailable()


def build_provider(provider_name: str) -> AipProvider:
    if provider_name == "seed":
        return SeedAipProvider()
    if provider_name in {"eaip", "aixm"}:
        return UnavailableAipProvider(provider_name)
    raise ValueError(f"Unknown AIP provider '{provider_name}'")


@lru_cache
def default_provider() -> AipProvider:
    """The single process-wide provider, selected by settings.aip_provider.
    Both api/router.py and services/workflow.py use this rather than each
    constructing their own, so activating/rotating datasets behaves
    consistently everywhere."""
    return build_provider(settings.aip_provider)
