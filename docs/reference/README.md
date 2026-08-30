# Reference material (not in this repository)

This directory locally holds source manuals and reference materials used while building NOTAMSYS, which are not distributed in the public GitHub repository:

- **Controlled manuals and standards**:
  - **ICAO Doc 8126** (Aeronautical Information Services Manual): source for the 1,250 NOTAM Selection Criteria rules transcribed into `apps/api/app/data/nsc/8126-2022.2.json`.
  - **Ghana AIP 7th Edition (21 May 2026)**: source for authentic Ghana aerodrome ARP coordinates, elevations, runway designators, and Navaids structured in `apps/api/app/data/aip/ghana_aip_2026.json`.
  - **ASECNA eAIP (aim.asecna.aero)**: source for authentic Togo (effective 06 AUG 2026, e.g. DXXX Lomé, DXNG Niamtougou) and Benin (effective 09 JUL 2026, e.g. DBBB Cotonou, DBBP Parakou) aerodrome data, ARP coordinates, elevations, runways, and Navaids within the shared Accra FIR (`DGAC`).
  - **EUROCONTROL OPADD Ed 4.1** (Operating Procedures for AIS Dynamic Data): source for standard aeronautical phraseology, expanded ICAO Doc 8400 abbreviations, and Q-line validation logic.
  - **ICAO Doc 10066** (PANS-AIM): source for NOTAM format specifications (Items A to G), aeronautical data quality standards, and AIXM compatibility.
  - **GCAA-AIS-753-MN01** (GCAA AIS Manual of Operations): local procedure rules and intake practices.
- **Office photos**: reference photos of the physical GCAA-AIS-NTM-FR01 paper form and office environment, used to design the intake UI and OCR template. Excluded because they may show identifiable people or documents and were never intended for public distribution.

If you're extending NOTAMSYS and need the source manuals for reference, obtain your own copy through official ICAO/GCAA/EUROCONTROL channels and place it here — `.gitignore` already excludes `docs/reference/*.pdf` and `docs/reference/office-photos/` so they won't accidentally get committed.
