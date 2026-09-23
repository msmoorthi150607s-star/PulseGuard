# ML Preprocessing & Feature-Extraction Strategy — External Datasets

**Status:** DESIGN REPORT for mentor review — **no feature-extraction code, no new model, no retraining, no production changes.**
**Prepared:** 2026-09-23 · Grounded in byte-level inspection of the preserved raw excerpts (verification pass `1995b34`).

---

## 1. KAIST data structure (as stored and as observed)

| Property | Verified fact (from stored excerpts) |
|---|---|
| Source files | Headerless CSV, one per hour of the 128 h run; 4 numeric columns: `vibration_x`, `vibration_y`, `temperature_bearing_c`, `temperature_atmospheric_c` |
| Vibration | Two orthogonal axes (x, y), sampled **25.6 kHz**, 78.125 s waveform per hourly file (2,000,000 samples) |
| Vibration unit | Preserved as raw source values; dataset text cites a 9 m/s² termination threshold but does not state the column unit — **documented as unstated, never converted** |
| Temperature | K-type thermocouple at the bearing + atmospheric channel; values **block-constant** within a file (~6–7 distinct quantised values per ~28k rows) — it is a slow, per-hour state variable, not a waveform |
| Temp behaviour observed | Bearing 41.6 °C (h 1) → 31.2 °C (h 2, cooldown dip) → 88.7 °C (h ~127) → **99.1 °C (final file, near the 85 °C termination criterion)** |
| Vibration behaviour observed | x-axis RMS 0.371 g-equiv (h 1) → 0.389 (h 2) → **1.376 → 1.403** (final files); peak grows −1.9…1.9 → −6.0…5.4 — a genuine degradation trend |
| Timestamps | **Not present in source.** Derived: hour-block start from filename (`LogFile_2022-06-20-17-00-31`) + in-file index ÷ 25 600 Hz. Documented derivation only |
| Labels | None. Run-to-failure ordering is the only legitimate structure |

## 2. ZTMF data structure (as stored and as observed)

| Property | Verified fact (from stored excerpts) |
|---|---|
| Vibration files | MATLAB v5 `.mat`, struct `Signal` with `x_values` (time-axis object) and `y_values` = **(7 680 000 × 4) double matrix**: 4 accelerometer channels — housing A x/y, housing B x/y — column-major |
| Vibration sample rate | Decoded from `x_values`: `start_value` 0, `increment` **3.90625e-05 s = 1/25 600 Hz**, 7 680 000 values → **300 s (5 min) recording @ 25.6 kHz** |
| Vibration unit | **g** (documented by source); observed RMS ≈ 0.98 g per channel in the Normal excerpt |
| Condition labels | Encoded **in filenames only**: `0Nm_Normal.mat`, `0Nm_Unbalance_0583mg.mat` (loadNm_condition_severity). Excerpted: Normal + Unbalance (milimetre-equivalent severity 0.583) at 0 Nm |
| Temperature files | NI TDMS (FlexLogger): `Mod1/ai0`, `Mod1/ai1` = two housing thermocouples, `unit_string = °C`, `wf_increment = 3.905e-05 s` (25.6 kHz clock, block-constant values); `Mod2/ai0, ai2, ai3` = three motor-current channels (A) — **stored, excluded from ML features** |
| Temp behaviour observed | Housing A ≈ 25.0 °C, Housing B ≈ 25.25 °C (Normal) — block-constant state variable |
| Timestamps | `wf_start_time` property per channel (NI absolute time); within-file axis from `wf_increment` |
| Sampling asymmetry | Temp+current logged at 25.6 kHz *clock* but constant in value; vib waveform genuinely 25.6 kHz |

**Shared discovery with cross-dataset value:** KAIST and ZTMF vibration are both **exactly 25.6 kHz** — identical sampling clocks, though different sensors, sensitivities, machines, and value scales.

## 3. Temperature/vibration alignment

**Principle: both signals are reduced to the same window-level table before any model work. Alignment happens at the *window* level, never at the raw-sample level.**

- **KAIST:** each hourly CSV *is* the natural alignment unit. Temperature (one block value) + vibration (78.125 s waveform) → **one aligned record per hour**, plus the mean atmospheric temperature. No resampling needed — no cross-rate conflict exists.
- **ZTMF:** a `.mat` and its condition-paired `.tdms` cover the same test condition; temperature is block-constant. Each `condition × load` pair → **one aligned record per recording** (temperature = housing A/B block values; vibration = window features of the 5-min waveform). The vib and temp files are condition-paired, not sample-paired — this is stated as a pairing assumption in the metadata, not silently assumed.
- **Own DC motor:** already naturally aligned — one row = one (temperature, vibration) instant at ~0.2 Hz. Windows would be defined over rows (~5 s each), e.g. 12 rows ≈ 1 min.

## 4. Proposed windowing

| Dataset | Window | Hop | Windows/file | Rationale |
|---|---|---|---|---|
| KAIST | **5 s** (128 000 samples) | 5 s non-overlap | ~15 per hourly file (~39 000 max in full archive; ~60 in excerpts) | Long enough for stable RMS/kurtosis/band features at 25.6 kHz; short enough to keep temporal resolution within an hour; matches own-data 1-min scale after aggregation |
| ZTMF | **5 s** (128 000 samples) | 5 s non-overlap | 60 per 5-min recording | Same window length → **statistically comparable features across both external datasets**; non-overlap prevents leakage (§8) |
| Own DC motor (context only — production untouched) | 1 min (12 rows) | 1 min | — | Only if a future experiment ever compares against external window tables |

Overlapping windows are excluded by design for training sets (leakage), except where explicitly documented for smoothing plots (never for train/test rows).

## 5. Candidate features (both permitted physical inputs only)

**Vibration waveform features (per axis; applied to each 5 s window):**

| # | Name | Source signal | Calculation | Physical meaning | Why it helps classification | Cross-dataset compatible? |
|---|---|---|---|---|---|---|
| V1 | `vib_rms` | vibration axis | sqrt(mean(x²)) | Energy of the vibration | Classic severity indicator; rises with fault growth (observed 0.37→1.40 in KAIST) | Yes — dimensionless given per-dataset calibration caveat (F1) |
| V2 | `vib_peak` | vibration axis | max(\|x\|) | Largest instantaneous amplitude | Impulsive damage produces high peaks | Yes |
| V3 | `vib_crest_factor` | vibration axis | peak / rms | Impulsiveness ratio | Distinguishes impulsive bearing faults from broadband noise | Yes |
| V4 | `vib_kurtosis` | vibration axis | 4th standardised moment | "Peakedness"/spikiness of distribution | Bearing defects give heavy-tailed signals (kurtosis ≫ 3) | Yes |
| V5 | `vib_std` | vibration axis | std(x) | Dispersion (= rms for zero-mean signals) | Redundant-but-cheap with V1; kept only if multicollinearity check passes | Yes |
| V6 | `vib_clearence` | vibration axis | (mean(sqrt(\|x\|)))² | Peak-sensitive, rms-normalised | Sensitive to early impulsive damage | Yes |
| V7 | `vib_zerocross_rate` | vibration axis | sign-change rate / (2·window) | Dominant frequency content proxy | Cheap spectral surrogate without FFT machinery | Yes |
| V8 | `vib_bandpower_ratio` (optional) | vibration axis | Power in 1–5 kHz ÷ total 0–12.8 kHz (FFT-based) | Where fault energy sits in spectrum | Bearing fault frequencies live in specific bands | Yes — same sample rate (25.6 kHz) in both external sets |

**Temperature features (per window / per aligned record):**

| # | Name | Source signal | Calculation | Physical meaning | Why it helps | Compatible? |
|---|---|---|---|---|---|---|
| T1 | `temp_value` | bearing/housing TC | block value (°C) | Thermal state of the machine | Direct severity evidence (41.6→99.1 °C in KAIST) | Yes (same unit °C; different measurement *point* — F4) |
| T2 | `temp_delta_t` | temperature | value − value at previous window/record | Thermal *trend* | Rising temp precedes/parallels degradation | KAIST yes (hourly); ZTMF limited (constant per file) |
| T3 | `temp_ambient_offset` | temperature | `temp_value` − atmospheric/second-TC | Machine self-heating above environment | Removes ambient drift; KAIST has the atmospheric channel, ZTMF has a 2nd housing TC (approximation, documented) | Partially — semantics differ per dataset |
| T4 | `temp_rolling_slope` | temperature | linear-fit slope over last k windows | Sustained heating rate | Strong precursor signal in run-to-failure data | KAIST yes; ZTMF no (needs longer series than a 5-min file) |

**Explicitly excluded (not derived from the two permitted inputs):** motor current, acoustic, RPM, torque, pressure, and every other source signal. RPM/speed appears in dataset *metadata* (operating conditions) only — never as a feature.

## 6. Label strategy

### Own DC motor (unchanged)
- Existing rule-generated NORMAL/WARNING/CRITICAL labels and the production feature contract (raw 5 s temperature+vibration rows) stay **exactly as they are**. No new labels, no relabelling. The production Random Forest is not touched.

### KAIST — no invented 3-class labels
- **Source information:** ordering (hour index), the two documented termination criteria (>85 °C bearing temp; >9 m/s² vibration), first/last-file positional context. That is all.
- **Legitimate derived experimental targets** (clearly marked `derived_experimental`, never published as ground truth):
  - **L-K1 "relative progression":** normalise hour index to [0,1] → *early-life* vs *late-life* (e.g. <20% / >80%) regression or 2-class framing. Honest framing: "position in run-to-failure sequence", **not** health classes.
  - **L-K2 "distance to termination" regression:** target = observed bearing temperature or RMS (documented source quantities) — framed as *signal-trajectory modelling*, not RUL. **No "days remaining" claims** — the dataset has no true RUL labels.
  - **L-K3 (excluded):** mapping into NORMAL/WARNING/CRITICAL would be inventing labels — **rejected**.
- Any KAIST experiment reports metrics **only against its derived target**, with the derivation rule printed alongside every result.

### ZTMF — filename provenance preserved verbatim
- Source condition = **substring of the original filename**, parsed mechanically: `{load}Nm_{condition}_{severity}.mat` → columns `source_load_nm` (0/2/4), `source_condition` (Normal/BPFI/BPFO/Misalign/Unbalance), `source_severity` (03/10/30/0583mg/…).
- The experimental label is the *raw condition string itself* (`Normal`, `Unbalance_0583mg`, …) — **never renamed, never merged into NORMAL/WARNING/CRITICAL**. Each row keeps `source_file` so every label traces back to its file, byte-for-byte.
- Optional experimental binarisation (`Normal` vs `Faulted`) may be *derived* as an extra column `derived_binary` while `source_condition` stays immutable.

## 7. Three experimental approaches

| | A1: temperature + one vibration representation | A2: temperature + multiple derived vibration features | A3: separate dataset-specific experimental models |
|---|---|---|---|
| Definition | e.g. `temp_value` + `vib_rms` per window — the minimal common table | `temp_value` + V1–V7 (+T2/T3) per window | One experimental pipeline per dataset (KAIST progression model; ZTMF condition classifier), never pooled |
| Advantages | Closest analogue to the production model's 2-input contract → cleanest conceptual comparison; simplest; least overfitting risk with few labels | Captures impulsiveness (kurtosis, crest, clearance) that single RMS misses — the actual fault signatures in bearing data; still strictly 2-sensor-derived | Maximum validity: no cross-dataset unit/scale questions at all; each model answers its own question |
| Disadvantages | Discards most of the discriminative signal; kurtosis-class information lost | Needs enough windows per class; more overfitting surface; adds compatibility burden (F1 scale issue remains) | Three results that cannot be averaged into one headline number; more code to maintain |
| Compatibility issues | Only via per-dataset calibration caveat (units differ) | Same, multiplied by feature count | None (by construction) |
| Fair comparison with production model? | **Yes** — same feature *style* (instantaneous temp+vibration level); differs only in window granularity. State this difference explicitly | Partial — richer features than production; any comparison must be labelled "experimental feature set" | **No** — different datasets/targets entirely; explicitly not comparable |

## 8. Risks / data-leakage concerns

1. **Temporal autocorrelation → the dominant leakage risk.** Consecutive 5 s windows are nearly identical. All splits for KAIST must be **by hour-block** (GroupShuffleSplit on `source_file`), never random-by-window. ZTMF splits by `source_file` (condition severity variants of the same run must stay on one side).
2. **Overlapping windows** — excluded from training by design (§4).
3. **Normalization leakage** — scalers (if any) fitted on train hours only, saved inside the experimental pipeline.
4. **Unit non-comparability (F1)** — any cross-dataset table must never be pooled without a documented per-dataset calibration; currently none exists → pooling is out of scope.
5. **Temperature block-constancy** — in KAIST/ZTMF temperature is constant within a window; models must not be presented as "using temperature dynamics" for those datasets (only T2/T4 across windows do, and only KAIST supports them).
6. **Class sparsity in excerpts** — ZTMF excerpts hold 2 conditions; KAIST 4 hours. Excerpt-level experiments are **method pilots**, not conclusions; full archives are re-downloadable via the fetch script when needed.
7. **Survivorship bias in KAIST** — excerpt only covers healthy start and failure end; mid-life hours missing → any "progression" model trained on excerpts is a demonstration, not a lifecycle model.
8. **No RUL claims** — prohibited unless genuine RUL labels exist; they do not.

## 9. Recommended experiment sequence (pending mentor approval)

1. **Exp-0 (sanity):** reproduce the verified numbers — per-file RMS/temp table for KAIST, per-condition RMS table for ZTMF. No model. Confirms feature code correctness before any modelling.
2. **Exp-1 (ZTMF pilot, A3 flavour):** windows from the two excerpted conditions, features V1–V7 + T1; source-condition labels verbatim; leave-one-file-out; report metrics as *pilot on 2 of 45+45 files*.
3. **Exp-2 (KAIST pilot, A3 flavour):** L-K1 early/late progression target on the 4 excerpted hours; grouped split by file; metrics reported against the derived target only.
4. **Exp-3 (A2 evaluation):** feature-importance comparison (RMS-only vs full V1–V7) on the ZTMF pilot → evidence for/against richer features.
5. **Exp-4 (optional, only with mentor sign-off):** expand excerpts to more source files via the re-download script before any stronger claims.
6. **Explicitly not in this sequence:** pooling datasets, retraining/replacing the production Random Forest, any RUL claim, any new production feature contract.

## 10. What must remain unchanged in the production system

- `ml/model.pkl` and `flask_api/model.pkl` (checksum `b118b86dd59aa98d0a8467749b41d553` recorded before any future work)
- `ml/train_model.py` — production training script
- Production feature contract: raw 5 s temperature+vibration rows from Firebase `/readings_only`
- Baseline thresholds: NORMAL < 38 °C & < 2; WARNING 38–40 °C or 2–5; CRITICAL > 40 °C or > 5
- Firebase structure (`readings_only` input-only, `prediction` output-only), Flask inference, dashboards, ESP32/IoT code
- Dataset packages: raw excerpts immutable; own package frozen at 693 readings
- All experimental work stays in clearly separated locations (proposed: `ml/experiments/` + `data/external/*/windows/`) with no import path into the Flask API

---

*End of design report. Implementation awaits mentor approval.*
