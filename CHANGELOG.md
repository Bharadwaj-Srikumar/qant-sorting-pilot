# 7 October 2026: one complete current thesis report

- Consolidated the supplied presentations, research papers, previous reports and
  current repository evidence into the German complete thesis documentation.
- Included foundations, all five architectures, lower/tight/upper bounds,
  derivations, code paths, quality metrics, common-noise controls, CPU baseline,
  reproducibility boundaries and the remaining hardware measurement plan.
- Retained only `reports/Masterarbeit_Hybride_Photonische_Sortierung.pdf` in
  `reports/`; removed eight obsolete reports, presentation/HTML copies and figures.
- Added an editable narrative, annotated bibliography and source/evidence hashes.
  The new report builder reads saved evidence without rerunning experiments.
- Moved the historical builder to `tools/build_legacy_reports.py` and redirected
  its output to `tmp/legacy_reports/` so obsolete reports cannot reappear in the
  current report folder. Updated active documentation links.
- Preserved scientific source code, inputs and recorded results. Missing
  historical periodic archives and five unavailable output configurations remain
  explicit; no hardware, GPU or energy measurements are invented.

# 5 October 2026: nonlinearity evidence correction

- Corrected the distinction between native periodic tcos and host CPU ReLU,
  based on the pinned official SDK source and its driver declarations.
- Documented exact C&E math and why the sign-only clipped difference cannot
  reconstruct exact min/max magnitudes.
- Added a commented, CPU-guarded `check_sdk_nonlinearity.py` and its saved
  exhaustive 4/8-bit arithmetic checks. This is separate from full sorting.
- Updated README, method, hardware boundary, result interpretation, slides and
  reports. Primary-source locators and unresolved hardware questions are explicit.
- Preserved the saved inputs, all baseline numerical outputs, eta values,
  quantizer, tie handling, record routing and original result provenance.
- No physical Q.ANT run, nonlinear optical sorter, cascade, new physical noise
  assumption, measured latency or energy claim was added.

Base project: last verified repository commit
`22ef167477fdce45b44bf0357445a419a75d4a0a`.
This update was prepared from that snapshot. Repository access was restored
on 5 October 2026 after the connector was installed on the repository owner's
account. Earlier 404 notices in the exported presentation and PDF describe
their export-time status; the GitHub commit history records publication.
