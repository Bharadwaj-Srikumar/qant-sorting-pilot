# 9 October 2026: repository structure cleanup

- Moved the 28 root Python files into a current `qant_sorting` package and an
  isolated `legacy` folder. Added `python -m qant_sorting COMMAND` as the common
  entry point; old root script commands and imports use the documented new paths.
- Centralized CSV serialization, streamed file hashing, repository paths and
  current source inventory. Sweep settings no longer require importing a runner.
- Made periodic-summary imports passive and its output explicit. Pair and
  periodic reproductions default to separate output paths. SDK installation
  exposes help and can preserve a separately installed dependency environment.
- Shortened README and code guide, grouped environment files under requirements,
  and merged identical analysis dependencies. Preserved mathematical comments,
  scientific kernels, seeds and stored results. Updated the current report.
- Historical metadata and source hashes remain historical; the source-layout
  inventory records moved paths. Numerical reproductions and structural checks
  are recorded in `validation/structure_cleanup_20261009.json`.

# 9 October 2026: affine periodic feasibility control

- Audited the pinned SDK's public MVM/periodic boundary and CPU product rounding.
- Added a documented, CPU-guarded affine candidate with exhaustive 4/8-bit pair
  checks, two independent mapping controls and 3,600 selected complete sorts.
- Recorded 40 false 8-bit ties caused by BF16 products; retained every output
  and the negative result without changing the existing comparison algorithms.
- Updated the single current thesis report and the unsent Q.ANT inquiry draft.
- Preserved all earlier scientific code, inputs and result evidence. No hardware
  run, host-free cascade, physical transfer, latency or energy claim was added.

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
