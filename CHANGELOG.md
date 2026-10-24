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
