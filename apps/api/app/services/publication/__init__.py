"""Publication adapter boundary: turns an approved NOTAM into a delivery
attempt on a specific channel (AFTN, the GCAA website, email distribution,
AIXM/Digital NOTAM). No adapter here speaks real AMHS/AFTN -- there are no
credentials or a spec for that (per the user's explicit direction). What's
real: AFTN envelope construction and ITA-2 character-set validation
(services/publication/aftn.py, fully testable offline), a file-drop adapter
an air-gapped Comsoft/CADAS terminal can actually pick up from, and genuine
AIXM XML publication into evidence storage. See registry.py for how a
channel resolves to simulated vs. real behaviour.
"""
