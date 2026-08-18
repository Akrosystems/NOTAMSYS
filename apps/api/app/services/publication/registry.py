"""Channel -> adapter resolution.

AFTN and AIXM always run their real (non-simulated) logic -- envelope
construction/ITA-2 validation and actual XML publication respectively --
because both are safe and self-contained; there's no reason to fake them.
GCAA_WEB and EMAIL have no live backend at all yet, so they're simulated
(always-ack) in dev/test and honestly fail in `async_adapters` mode until
a real CMS/SMTP integration exists.
"""

from pathlib import Path

from app.core.config import settings
from app.services.publication.adapters import (
    AixmPublishAdapter,
    FileDropAftnAdapter,
    PullQueueAftnAdapter,
    SimulatedAftnAdapter,
    SimulatedChannelAdapter,
    SmtpEmailAdapter,
    UnconfiguredAdapter,
)
from app.services.publication.base import PublicationAdapter

CHANNELS: tuple[tuple[str, str], ...] = (
    ("AFTN", "DGAANOTA/DGAANOTB/DGAANOTC"),
    ("GCAA_WEB", "gcaa.com.gh/notam"),
    ("EMAIL", "Accra NOF distribution list"),
    ("AIXM", "Digital NOTAM service"),
)


def build_adapter(channel: str, destination: str, *, simulated: bool) -> PublicationAdapter:
    if channel == "AFTN":
        if not simulated:
            # File-drop only makes sense when this process and the Comsoft
            # terminal share a filesystem (an on-prem deployment). The pull
            # queue is the default for the real path otherwise -- see
            # PullQueueAftnAdapter's docstring for why.
            if settings.aftn_bridge_api_key:
                return PullQueueAftnAdapter()
            return FileDropAftnAdapter(Path(settings.aftn_drop_dir))
        return SimulatedAftnAdapter()
    if channel == "AIXM":
        return AixmPublishAdapter()
    if channel == "EMAIL":
        if simulated:
            return SimulatedChannelAdapter(channel, destination)
        if settings.smtp_host:
            return SmtpEmailAdapter(destination)
        return UnconfiguredAdapter(channel, destination)
    if channel == "GCAA_WEB":
        if simulated:
            return SimulatedChannelAdapter(channel, destination)
        return UnconfiguredAdapter(channel, destination)
    raise ValueError(f"Unknown publication channel '{channel}'")
