import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import Aerodrome, AipDataset, Fir
from app.services.aip.loader import canonical_checksum, load_dataset_payload
from app.services.aip.provider import SeedAipProvider, UnavailableAipProvider


def test_seed_dataset_payload_is_well_formed_and_honest_about_gaps() -> None:
    payload = load_dataset_payload()
    assert payload["firs"]
    assert payload["aerodromes"]
    for fir in payload["firs"]:
        assert fir["icao_code"] and fir["name"] and fir["provenance"]
    for aerodrome in payload["aerodromes"]:
        assert aerodrome["icao_code"] and aerodrome["name"] and aerodrome["provenance"]
        # "Null over invented": the interim seed must never fabricate
        # coordinates it doesn't actually have.
        assert "arp_latitude" not in aerodrome
        assert "arp_longitude" not in aerodrome
        assert aerodrome["fir_code"] in {fir["icao_code"] for fir in payload["firs"]}


def test_checksum_is_deterministic() -> None:
    payload = load_dataset_payload()
    assert canonical_checksum(payload) == canonical_checksum(payload)


def test_seed_provider_reads_the_active_dataset(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'aip.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            dataset = AipDataset(version="test-1", source="seed", checksum="abc", active=True)
            session.add(dataset)
            await session.flush()
            fir = Fir(
                dataset_id=dataset.id, icao_code="DGAC", name="Accra FIR", provenance="test"
            )
            session.add(fir)
            await session.flush()
            session.add(
                Aerodrome(
                    dataset_id=dataset.id,
                    icao_code="DGAA",
                    name="Kotoka International Airport",
                    fir_id=fir.id,
                    provenance="test",
                )
            )
            await session.commit()

            provider = SeedAipProvider()
            metadata = await provider.dataset_metadata(session)
            assert metadata is not None
            assert metadata.version == "test-1"

            firs = await provider.list_firs(session)
            assert [f.icao_code for f in firs] == ["DGAC"]

            aerodromes = await provider.list_aerodromes(session)
            assert [a.icao_code for a in aerodromes] == ["DGAA"]

            found = await provider.get_aerodrome(session, "dgaa")
            assert found is not None
            assert found.name.startswith("Kotoka")

            assert await provider.get_aerodrome(session, "ZZZZ") is None
            assert len(await provider.list_aerodromes(session, query="kotoka")) == 1
            assert len(await provider.list_aerodromes(session, query="nonexistent")) == 0

        await engine.dispose()

    asyncio.run(scenario())


def test_seed_provider_returns_empty_without_an_active_dataset(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'aip_empty.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            provider = SeedAipProvider()
            assert await provider.dataset_metadata(session) is None
            assert await provider.list_firs(session) == []
            assert await provider.list_aerodromes(session) == []
        await engine.dispose()

    asyncio.run(scenario())


def test_unavailable_provider_raises_rather_than_silently_returning_nothing() -> None:
    provider = UnavailableAipProvider("eaip")

    async def call() -> None:
        await provider.list_firs(session=None)  # type: ignore[arg-type]

    with pytest.raises(NotImplementedError):
        asyncio.run(call())
