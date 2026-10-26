# 26 October 2026 - English thesis documentation

- Translated the remaining technical guides, inquiry draft, complete report,
  reference notes, and generated tables, diagrams, captions, and PDF metadata.
- Replaced the report and inquiry filenames with English names and updated links.
- Used English decimal and thousands separators throughout the report.
- Preserved the mathematical model, algorithms, saved results, source identities,
  and evidence hashes. The current PDF retains all 24 tables and both charts.

# 24 October 2026 — one canonical rank architecture

- Moved shared rank validation and placement (`place_ranks`) beside `rank_sort`
  in `sorting_schedules.py`, so the operational sorter can be read in one file.
  The equation-level reference imports that helper and retains its own
  `quantize_difference`; numerical algorithms and saved results are unchanged.
- Adopted Louri's full N×N matrix as the sole thesis rank implementation, including
  separately evaluated directions, measured diagonal, normalized unit bias,
  threshold, column ranks and validated electronic placement.
- Connected the same matrix schedule to the official Q.ANT CPU linear adapter.
- Recomputed the complete noise reference, ranking metrics, SDK integration,
  common-noise controls, source-equation validation and N² resource accounting.
- Retained the relevant CPU baseline, literature, source audits and negative affine
  pair result. Periodic scores are a separate feasibility study.
- Removed reduced-pair implementation/results, obsolete prototypes, duplicate
  inputs, unmatched historical noise scenarios, archive-recovery code and old
  report assets. Earlier versions remain accessible through Git history.
- Updated the reading guides and the sole current complete thesis report.
