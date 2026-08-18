# What to request: email and AFTN integration

Two things NOTAMSYS needs from other teams before it can stop simulating
the Email and AFTN channels. Everything below is written to be handed to
the person who owns each piece -- copy the relevant section into a ticket
or email as-is.

Neither integration is required for NOTAMSYS to keep working today --
`simulated_sync` mode (the current Render default) keeps every channel
behaving exactly as before until you supply the credentials below.

---

## For whoever administers aisnotam@caa.gov.gh (IT / mail admin)

NOTAMSYS needs to **send** NOTAM distributions through this mailbox and
**read** incoming NOTAM request emails sent to it. Two separate credential
sets -- most mail providers issue them differently.

### 1. Outbound sending (SMTP)

| What we need | Used for |
|---|---|
| SMTP server hostname | `NOTAMSYS_SMTP_HOST` |
| SMTP port (587 for STARTTLS, 465 for implicit TLS, 25 unencrypted) | `NOTAMSYS_SMTP_PORT` |
| A username NOTAMSYS can authenticate as | `NOTAMSYS_SMTP_USERNAME` |
| Its password or app-specific password | `NOTAMSYS_SMTP_PASSWORD` |
| The "From" address NOTAM distributions should appear to come from | `NOTAMSYS_SMTP_FROM_ADDRESS` |

If the mailbox is Microsoft 365 or Google Workspace, ask specifically for
an **app password** or **SMTP AUTH client credential** -- not the mailbox
owner's normal login, which typically won't work for SMTP AUTH and
shouldn't be shared as a shared secret anyway.

### 2. Inbound reading (IMAP)

| What we need | Used for |
|---|---|
| IMAP server hostname | `NOTAMSYS_IMAP_HOST` |
| IMAP port (993 for TLS, the default) | `NOTAMSYS_IMAP_PORT` |
| Username/password (can reuse the SMTP credential if the provider allows it) | `NOTAMSYS_IMAP_USERNAME` / `NOTAMSYS_IMAP_PASSWORD` |
| Confirmation NOTAMSYS may mark messages read (`\Seen`) in this mailbox | -- |

**Ask specifically:** can this account read the mailbox that
aisnotam@caa.gov.gh actually receives mail at, or does mail need to be
forwarded/aliased to a dedicated intake address instead? A shared
operational mailbox with humans also reading it is fine -- NOTAMSYS only
acts on messages still marked unread, and marks them read once ingested,
the same as any other email client would.

### What happens once we have these

- Every NOTAM published gets emailed to the distribution list for real,
  instead of the current simulated always-succeed placeholder.
- Every NOTAM request emailed to the mailbox becomes a real request in the
  AIS Officer's queue automatically (as "Received", ready for triage) --
  any PDF/document attached becomes evidence eligible for the same
  extraction the upload path already has. It does not attempt to read or
  understand the email's content beyond that; an officer still triages and
  prepares it like any other request.
- Nothing changes about the manual path (an officer reading an email
  themselves and typing the request in) -- both can run side by side.

---

## For ATSEP (the Comsoft/CADAS AFTN terminal)

NOTAMSYS is hosted on Render, off-site from the Comsoft terminal, so it
can't write directly to whatever folder the terminal watches -- there's no
shared filesystem or network path between the two, and Render's own local
storage doesn't persist anyway. Full detail and setup steps: `docs/AFTN_BRIDGE.md`.

**What we need confirmed:**

1. **A directory on the Comsoft Linux box that the terminal actually
   watches for incoming AFTN envelope files.** If none exists today, what
   would need to be configured on the Comsoft side to add one, and in what
   format/encoding does it expect the file (`scripts/aftn_bridge.py`
   currently writes plain ITA-2-validated text files named
   `<timestamp>-<id>.aftn.txt`).
2. **Permission to run a small script continuously on that box** (or a box
   with network access to it) -- `scripts/aftn_bridge.py`, pure Python 3
   standard library, no installation required, ~100 lines, reviewable
   before it runs. It only ever reads from NOTAMSYS's API and writes files
   to the one directory above; it never touches the Comsoft application
   itself.
3. Whether ATSEP wants to run it under `systemd` (a unit file is provided
   in `docs/AFTN_BRIDGE.md`) or has an existing process-supervision
   convention we should match instead.

**What we'll provide once the above is confirmed:** the generated
`NOTAMSYS_AFTN_BRIDGE_API_KEY` value the script needs to authenticate --
nothing else is required from us to set this up.

**What this integration will not do:** confirm that Comsoft actually
transmitted a NOTAM over AFTN. It confirms the envelope reached the watched
directory. Whether Comsoft's own workflow then puts it on the wire is
outside anything NOTAMSYS (or this bridge) can observe, unless ATSEP knows
of an existing Comsoft-side confirmation signal worth integrating later.
