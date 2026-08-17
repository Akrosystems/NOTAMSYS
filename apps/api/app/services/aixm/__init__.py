"""Real AIXM 5.1.1 / Digital NOTAM XML output, replacing the hand-built
summary dict that used to be the only "AIXM" artifact this system produced.

Scope is deliberately an event-only profile: an `Event` feature with a
`validTime`, geodesic circle geometry, and the NOTAM's Q-code/text as
NOTAMSYS-namespaced extension elements, not full AIXM Digital NOTAM Event
Specification feature modelling (RunwayElement, AirspaceStatus, etc). Doc
8126 Part IV ("Digital Aeronautical Information Products") is marked
"under development" in the 7th edition, so there is no local spec to derive
fuller coverage from -- expand additively, per subject, once there's a
concrete downstream consumer to validate against.
"""
