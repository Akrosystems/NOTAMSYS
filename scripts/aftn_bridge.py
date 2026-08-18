#!/usr/bin/env python3
"""AFTN bridge -- run this ON THE COMSOFT/CADAS LINUX BOX, not on the
NOTAMSYS server. NOTAMSYS is hosted on Render (cloud); this terminal is
on-prem and can never see Render's filesystem, and Render wipes local disk
on every redeploy regardless. This script is how the two actually connect:
it polls NOTAMSYS for pending AFTN envelopes, writes each one into the
directory Comsoft's terminal watches, then tells NOTAMSYS it did.

Pure standard library on purpose -- nothing to `pip install` on a box that
may have no internet access or package manager reach. Needs only Python 3.

Setup (see docs/AFTN_BRIDGE.md for the full walkthrough):
    export NOTAMSYS_API_URL=https://notamsys-api.onrender.com/api/v1
    export NOTAMSYS_AFTN_API_KEY=<the key NOTAMSYS_AFTN_BRIDGE_API_KEY was set to>
    export AFTN_WATCH_DIR=/path/Comsoft/actually/watches
    python3 aftn_bridge.py

Still "sent", not "transmitted": this only confirms the envelope reached
the watched directory, never that Comsoft's own workflow actually put it on
the wire. That confirmation loop doesn't exist yet -- see
docs/OPERATIONAL_BOUNDARY.md.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

API_URL = os.environ.get("NOTAMSYS_API_URL", "").rstrip("/")
API_KEY = os.environ.get("NOTAMSYS_AFTN_API_KEY", "")
WATCH_DIR = Path(os.environ.get("AFTN_WATCH_DIR", "./aftn-outbox"))
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))


def _call(method: str, path: str, body: dict | None = None):
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - trusted, operator-configured URL
        return json.loads(response.read().decode("utf-8"))


def poll_once() -> int:
    items = _call("GET", "/aftn/outbox")
    if items:
        WATCH_DIR.mkdir(parents=True, exist_ok=True)
    for item in items:
        filename = f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{item['id'][:8]}.aftn.txt"
        (WATCH_DIR / filename).write_text(item["outbound_body"], encoding="utf-8")
        _call("POST", f"/aftn/outbox/{item['id']}/ack", {"external_reference": filename})
        print(f"aftn_bridge: wrote {filename}", flush=True)
    return len(items)


def main() -> None:
    if not API_URL or not API_KEY:
        sys.exit(
            "Set NOTAMSYS_API_URL and NOTAMSYS_AFTN_API_KEY before running. "
            "See docs/AFTN_BRIDGE.md."
        )
    print(f"aftn_bridge: polling {API_URL}/aftn/outbox every {POLL_INTERVAL_SECONDS}s, "
          f"writing to {WATCH_DIR.resolve()}", flush=True)
    while True:
        try:
            processed = poll_once()
            if processed:
                print(f"aftn_bridge: processed {processed} envelope(s)", flush=True)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"aftn_bridge: poll failed, will retry -- {exc}", file=sys.stderr, flush=True)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
