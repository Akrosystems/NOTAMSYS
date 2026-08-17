# Reference material (not in this repository)

This directory locally holds two kinds of source material used while building NOTAMSYS, neither of which is included in the public GitHub repository:

- **Controlled manuals**: ICAO Doc 8126 (Aeronautical Information Services Manual) and GCAA-AIS-753-MN01 (AIS Manual of Operations). Both are copyrighted/controlled documents supplied for this project — not ours to redistribute. The NOTAM Selection Criteria transcribed from Doc 8126 into `apps/api/app/data/nsc/` *is* included, since a structured dataset of Q-code/subject/condition mappings with citations is a derived fact table, not a copy of the source document.
- **Office photos**: reference photos of the physical GCAA-AIS-NTM-FR01 paper form and office environment, used to design the intake UI and OCR template. Excluded because they may show identifiable people or documents and were never intended for public distribution.

If you're extending NOTAMSYS and need the source manuals for reference, obtain your own copy through ICAO/GCAA's official channels and place it here — `.gitignore` already excludes `docs/reference/*.pdf` and `docs/reference/office-photos/` so it won't accidentally get committed.
