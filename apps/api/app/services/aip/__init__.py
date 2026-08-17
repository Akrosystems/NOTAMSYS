"""GCAA AIP (Aeronautical Information Publication) reference-data boundary.

Provides FIR/aerodrome lookups behind a provider interface so intake forms
and the Q-line editor can offer real autocomplete and existence checks
instead of free-text guessing. `SeedAipProvider` is backed by whatever
`AipDataset` is currently active in the database (see loader.py); it works
identically whether that dataset came from the interim seed JSON or a real
AIP import later.
"""
