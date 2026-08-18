import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.database import Base
from app.models import Notam, NotamRequest
from app.seed import SAMPLE_NOTAM_DRAFTS, _seed_sample_notam_drafts, _seed_users_and_reference_data


def test_sample_notam_drafts_are_backfilled_and_idempotent(tmp_path) -> None:
    """Every seeded NotamRequest that starts in REVIEW/CHANGES_REQUESTED must
    have a matching prepared Notam, otherwise a specialist opening it has
    nothing to review even though the workflow says one is pending. Also
    confirms _seed_sample_notam_drafts can safely re-run against an
    already-backfilled database (the real path for fixing a database that
    was seeded before this function existed)."""
    database = tmp_path / "seed.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await _seed_users_and_reference_data(session)
            await _seed_sample_notam_drafts(session)
            await session.commit()

        async with sessions() as session:
            for request_number in SAMPLE_NOTAM_DRAFTS:
                request = await session.scalar(
                    select(NotamRequest)
                    .where(NotamRequest.request_number == request_number)
                    .options(selectinload(NotamRequest.notam))
                )
                assert request is not None, request_number
                assert request.notam is not None, request_number
                assert request.notam.validation_result["valid"] is True, request_number
                assert request.notam.formatted_message

        # Re-running must not duplicate the Notam rows it already created.
        async with sessions() as session:
            await _seed_sample_notam_drafts(session)
            await session.commit()
        async with sessions() as session:
            count = await session.scalar(select(func.count()).select_from(Notam))
            assert count == len(SAMPLE_NOTAM_DRAFTS)

    asyncio.run(run())
