# Connecting to the real AFTN/Comsoft terminal

## Why this exists

NOTAMSYS is hosted on Render (cloud). The Comsoft/CADAS AFTN terminal ATSEP
operates is an on-prem Linux box. Those two machines don't share a
filesystem, and Render's own local disk is wiped on every redeploy anyway
(`docs/DEPLOYMENT.md`) -- so the obvious approach ("just write the AFTN
envelope to a folder") doesn't reach the terminal at all.

`scripts/aftn_bridge.py` bridges the gap the other direction: instead of
NOTAMSYS pushing a file somewhere, ATSEP's own Linux box **pulls** pending
envelopes from NOTAMSYS's API on an interval, writes each one into whatever
directory the Comsoft terminal actually watches, and tells NOTAMSYS it did.

```
NOTAMSYS (Render)  <--- polls GET /aftn/outbox --->  aftn_bridge.py (ATSEP's Linux box)
                                                              |
                                                              v
                                                    directory Comsoft watches
```

## What NOTAMSYS needs from you (one-time)

1. **Generate a bridge API key.** Any long random string works -- e.g.:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. **Set it on the API service.** On Render (or wherever `notamsys-api` runs):
   `NOTAMSYS_AFTN_BRIDGE_API_KEY=<the key from step 1>`. The `/aftn/outbox`
   endpoints reject every request with a 503 until this is set, and reject
   any request whose `X-API-Key` header doesn't match it with a 401 --
   there is no way to reach this data without the key.
3. Make sure the API service is running with a channel mode that actually
   uses the pull queue for AFTN -- either set `NOTAMSYS_AFTN_MODE=async_adapters`
   (AFTN goes real, other channels keep whatever `NOTAMSYS_PUBLICATION_MODE`
   already says), or set the global `NOTAMSYS_PUBLICATION_MODE=async_adapters`
   if you want everything real at once. `PullQueueAftnAdapter` is selected
   automatically once `NOTAMSYS_AFTN_BRIDGE_API_KEY` is set (see
   `app/services/publication/registry.py`) -- you don't need a separate
   toggle for pull-vs-file-drop.

## What to run on the Comsoft Linux box

`scripts/aftn_bridge.py` -- copy it to the box. It's pure Python 3 standard
library, nothing to install.

```bash
export NOTAMSYS_API_URL=https://notamsys-api.onrender.com/api/v1
export NOTAMSYS_AFTN_API_KEY=<the same key from step 1 above>
export AFTN_WATCH_DIR=/path/the/comsoft/terminal/actually/watches
python3 aftn_bridge.py
```

It polls every 30 seconds (`POLL_INTERVAL_SECONDS` to change that), writes
`<timestamp>-<id>.aftn.txt` files containing the real, ITA-2-validated AFTN
envelope, and acknowledges each one back to NOTAMSYS so the request can
progress out of "Publishing".

### Running it continuously

A one-off `python3 aftn_bridge.py` run exits if the terminal closes. For
production, run it as a systemd service:

```ini
# /etc/systemd/system/notamsys-aftn-bridge.service
[Unit]
Description=NOTAMSYS AFTN bridge
After=network.target

[Service]
Type=simple
Environment=NOTAMSYS_API_URL=https://notamsys-api.onrender.com/api/v1
Environment=NOTAMSYS_AFTN_API_KEY=REPLACE_ME
Environment=AFTN_WATCH_DIR=/path/the/comsoft/terminal/actually/watches
ExecStart=/usr/bin/python3 /opt/notamsys/aftn_bridge.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now notamsys-aftn-bridge
sudo journalctl -u notamsys-aftn-bridge -f   # watch it work
```

## What this does and doesn't confirm

The bridge acknowledging a delivery means the envelope reached the watched
directory -- **not** that Comsoft's own workflow put it on the wire. That
confirmation loop doesn't exist (no Comsoft API or spec is available to
build one against -- see `docs/OPERATIONAL_BOUNDARY.md`). A delivery stays
"sent" in NOTAMSYS right up until the bridge's ack call, at which point it
becomes "acknowledged" -- read as "delivered to Comsoft for onward
transmission," not "transmitted."

## Rotating or revoking the key

Change `NOTAMSYS_AFTN_BRIDGE_API_KEY` on the API service and update the
`NOTAMSYS_AFTN_API_KEY` environment variable on the bridge box to match.
There's no separate revocation list -- changing the one value invalidates
the old key immediately.
