"""Standalone process: polls the configured mailbox on an interval and
ingests unseen messages as NotamRequests. Mirrors app/seed.py's pattern --
run directly, not imported by the API process.

    python -m app.email_poller

Off by default: exits immediately with a clear error if IMAP settings
aren't configured, rather than looping forever doing nothing. See
docs/INTEGRATION_REQUIREMENTS.md for what to request from whoever
administers the mailbox, and docs/DEPLOYMENT.md for how to actually run
this continuously (it needs its own long-running process -- a Render
Background Worker service or an external cron hitting a wrapper)."""

import asyncio

from app.core.database import SessionFactory
from app.services.intake.email_poller import poll_once

POLL_INTERVAL_SECONDS = 120


async def run_forever() -> None:
    while True:
        async with SessionFactory() as session:
            created = await poll_once(session)
            if created:
                print(f"email_poller: ingested {created} request(s)")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_forever())
