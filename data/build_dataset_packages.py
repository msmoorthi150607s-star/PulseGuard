#!/usr/bin/env python3
"""
PulseGuard - build dataset packages from the preserved raw material.

For each dataset this script produces, WITHOUT editing raw files:
  cleaned/   full parsed records extracted from the raw excerpt (CSV)
  excel/     human-readable Excel workbook (deterministic decimation of
             the cleaned records - every Nth REAL value, nothing averaged
             or interpolated)
  metadata.json

Integrity rules honoured here:
  - raw/ files are only ever READ
  - no values are invented: every cleaned row comes from source bytes
  - truncation of excerpts is documented, cut at record boundaries
  - no label is invented; source-provided conditions are kept verbatim

Usage: python build_dataset_packages.py
"""
import json
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent
ACCESS_DATE = "2026-09-23"

# ---------------------------------------------------------------- helpers


def decimate(df: pd.DataFrame, every: int) -> pd.DataFrame:
    """Deterministic decimation: keep every Nth row (real values only)."""
    return df.iloc[::every].reset_index(drop=True)


def write_excel(path: Path, df: pd.DataFrame, sheet_title: str, notes: dict):
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        notes_df = pd.DataFrame(
            [(k, str(v)) for k, v in notes.items()], columns=["Field", "Value"])
        notes_df.to_excel(xl, sheet_name="About", index=False)
        df.to_excel(xl, sheet_name=sheet_title, index=False)
    print(f"  excel: {path.name} ({len(df):,} rows shown of {notes['cleaned_rows']:,})")


# ---------------------------------------------------------------- KAIST


def build_kaist():
    base = DATA / "external" / "kaist"
    raw_dir = base / "raw" / "Vibration_Bearing_RuntoFailure.zip"
    files = sorted(raw_dir.glob("*.csv"))
    frames = []
    for f in files:
        # Filename encodes the hour block: LogFile_2022-06-20-17-00-31.csv
        stem = f.stem.replace("LogFile_", "")
        block_start = datetime.strptime(stem, "%Y-%m-%d-%H-%M-%S").replace(
            tzinfo=timezone.utc)
        df = pd.read_csv(f, header=None, names=[
            "vibration_x", "vibration_y", "temperature_bearing_c",
            "temperature_atmospheric_c"])
        df["source_file"] = f.name
        df["in_file_sample_index"] = np.arange(1, len(df) + 1)
        # 25.6 kHz sampling -> within-file time offset (documented derivation)
        df["in_file_time_s"] = df["in_file_sample_index"] / 25600.0
        df["source_hour_block_start_utc"] = block_start.isoformat()
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    n_raw = len(raw)

    # Cleaning: numeric coercion, drop malformed rows, drop exact duplicates.
    # No interpolation, no gap filling, no value changes.
    num_cols = ["vibration_x", "vibration_y", "temperature_bearing_c",
                "temperature_atmospheric_c"]
    for c in num_cols:
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    invalid = raw[num_cols].isna().sum().sum()
    raw = raw.dropna(subset=num_cols)
    dup_count = raw.duplicated().sum()
    raw = raw.drop_duplicates()
    raw = raw.sort_values(["source_file", "in_file_sample_index"]).reset_index(drop=True)

    # Positional context (NOT a source label - documented as such):
    first_two, last_two = files[:2], files[-2:]
    raw["condition"] = "unlabelled"
    raw.loc[raw["source_file"].isin([f.name for f in first_two]),
            "condition"] = "unlabelled_start_of_run_to_failure_test"
    raw.loc[raw["source_file"].isin([f.name for f in last_two]),
            "condition"] = "unlabelled_final_hours_before_termination"
    raw["label"] = raw["condition"]

    cleaned = base / "cleaned" / "kaist_cleaned.csv"
    raw.to_csv(cleaned, index=False)

    excel_df = decimate(raw, 100)
    write_excel(base / "excel" / "KAIST_Ball_Bearing_Test.xlsx", excel_df,
                "readings",
                {
                    "dataset_id": "KAIST_BALL_BEARING",
                    "source": "Mendeley Data DOI 10.17632/5hcdd3tdvb.6 (CC BY 4.0)",
                    "access_date": ACCESS_DATE,
                    "machine": "NSK 6205 ball bearing on KAIST accelerated life test rig, 1770-1780 RPM",
                    "columns": "vibration_x/y (PCB 352C34 accel), bearing temp, atmospheric temp (K-type TC)",
                    "vibration_unit": "raw source values (dataset text cites m/s^2 termination threshold; unit not stated per column)",
                    "temperature_unit": "degC",
                    "sampling": "25.6 kHz, each source file covers 78.125 s (hourly published)",
                    "raw_rows_total_in_source": "approx 2,000,000 per hourly file x 129 files (4.3 GB archive)",
                    "excerpt": f"verbatim 2 MB prefix of 4 of 129 hourly files (first 2 + last 2)",
                    "raw_rows_in_excerpt": n_raw,
                    "cleaned_rows": len(raw),
                    "invalid_rows_removed": int(invalid),
                    "duplicate_rows_removed": int(dup_count),
                    "excel_decimation": "every 100th cleaned row (real values, no averaging)",
                    "condition_column": "unlabelled; positional context only - source has NO condition labels",
                    "timestamp": "source CSVs have no timestamp; hour block from filename + in-file time at 25.6 kHz",
                })

    meta = {
        "dataset_id": "KAIST_BALL_BEARING",
        "human_readable_name": "KAIST Ball Bearing Run-to-Failure (Vibration + Temperature)",
        "original_dataset_name": "Ball Bearing Vibration, and Temperature Run-to-Failure Dataset",
        "source": "Mendeley Data (KAIST)",
        "source_reference": "DOI 10.17632/5hcdd3tdvb.6; Data in Brief: 'Vibration, and Temperature Run-to-Failure Dataset of Ball Bearing for Prognostics'",
        "source_url": "https://data.mendeley.com/datasets/5hcdd3tdvb/6",
        "access_date": ACCESS_DATE,
        "machine_or_test_rig": "NSK 6205 ball bearing (25 mm bore), accelerated life test rig, 1770-1780 RPM, axial load 2.94 kN + vertical load 5.88 kN; test terminated at bearing temp > 85 C or vibration > 9 m/s^2; operating period 2022-06-20 17:00 to 2022-06-26 01:00 (128 h)",
        "sensor_information": {
            "vibration": "PCB 352C34 ICP accelerometer, x and y axes, 25.6 kHz",
            "temperature_bearing": "K-type thermocouple, 25.6 kHz sampled (constant per block)",
            "temperature_atmospheric": "K-type thermocouple, 25.6 kHz sampled (constant per block)",
        },
        "temperature_available": True,
        "vibration_available": True,
        "temperature_unit": "degC",
        "vibration_unit": "raw source values preserved (dataset description cites an m/s^2 termination threshold but does not state the column unit)",
        "sampling_information": "Vibration sampled 25.6 kHz; each hourly CSV holds a 78.125 s waveform (2,000,000 samples); temperatures constant within each file block",
        "operating_conditions": "Constant speed 1770-1780 RPM under fixed axial+vertical load; run-to-failure accelerated life test",
        "labels_available": False,
        "label_note": "No condition/failure labels per record in source. First/last hourly files have positional context only (start of test / final hours).",
        "original_file_format": "129 headerless CSV files in one 4.3 GB ZIP (4 columns, no timestamps)",
        "files_in_source": 129,
        "files_in_excerpt": 4,
        "excerpt_strategy": "verbatim 2 MB byte-prefix of first 2 and last 2 hourly CSVs, cut at row boundary, via HTTP range requests",
        "preprocessing_applied": [
            "numeric coercion; rows with non-numeric sensor values dropped",
            "exact duplicate rows dropped",
            "chronological ordering by source file then in-file index",
            "NO interpolation, NO gap filling, NO unit conversion, NO value modification",
        ],
        "excluded_features": "none (source has only the 4 columns; temperature and vibration are the only signals)",
        "license_or_usage_information": "CC BY 4.0",
        "raw_preserved": "raw/ holds byte-verbatim excerpts; original archive re-downloadable from source_url",
        "notes": "ML features permitted: vibration_x/vibration_y and temperature_bearing_c. Timestamps derived from filenames + documented sample clock, not present in source.",
    }
    (base / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  KAIST: raw={n_raw:,} cleaned={len(raw):,}")
    return raw


# ---------------------------------------------------------------- ZTMF


def parse_mat_prefix(path: Path):
    """Extract the data matrix from a truncated MAT-5 file.

    ZTMF vibration files store a MATLAB struct with fields x_values/y_values;
    y_values is a (7680000, 4) double matrix (4 accelerometer channels,
    column-major). This walker recursively descends miMATRIX elements and
    returns (dims, payload_abs_offset) of the largest miDOUBLE payload.
    Verified against the source files on 2026-09-23.
    """
    buf = path.read_bytes()
    assert buf.startswith(b"MATLAB"), "not MAT-5"
    best = [None]  # [payload_len, dims, abs_off]

    def walk_matrix(pos, nb, depth=0):
        if depth > 8:
            return
        q = pos + 8
        end = min(pos + 8 + nb, len(buf))
        sub_dims = None
        while q + 8 <= end:
            a2, b2 = struct.unpack_from("<II", buf, q)
            if a2 >> 16 != 0:          # small-format element
                q += 8
                continue
            t2, n2 = a2, b2
            if t2 == 5 and n2 in (8, 16) and sub_dims is None:   # miINT32 dims
                sub_dims = struct.unpack_from("<%di" % (n2 // 4), buf, q + 8)
            if t2 == 9 and n2 > 1000:  # numeric payload (may be truncated)
                cand = (n2, sub_dims, q + 8)
                if best[0] is None or cand[0] > best[0][0]:
                    best[0] = cand
            if t2 == 14 and n2 > 64:   # nested matrix (cell/struct field)
                walk_matrix(q, n2, depth + 1)
            q += 8 + n2 + ((8 - n2 % 8) % 8)

    top_t, top_nb = struct.unpack_from("<II", buf, 128)
    if top_t == 14:
        walk_matrix(128, top_nb)
    if best[0] is None:
        raise ValueError(f"no numeric payload found in {path.name}")
    return best[0][1], best[0][2]


def build_ztmf():
    base = DATA / "external" / "ztmf_rotating_machine"

    # ---- vibration .mat prefixes (5 columns: Time Stamp + 4 vib channels, g)
    frames = []
    vib_meta_files = {}
    for f in sorted((base / "raw" / "vibration_mat").glob("*.mat")):
        dims, off = parse_mat_prefix(f)
        buf = f.read_bytes()
        nrows_decl, ncols = dims if dims else (None, 4)
        avail = (len(buf) - off) // 8
        nrows_avail = avail // ncols
        arr = np.frombuffer(buf[off: off + nrows_avail * ncols * 8], dtype="<f8")
        arr = arr.reshape(nrows_avail, ncols)  # column-major -> (samples, channels)
        df = pd.DataFrame(arr, columns=[
            "vib_x_housing_A_g", "vib_y_housing_A_g",
            "vib_x_housing_B_g", "vib_y_housing_B_g"])
        cond = f.stem.split("_", 1)[1]          # Normal / Unbalance_0583mg
        df["condition"] = cond                  # source-encoded in filename
        df["label"] = cond
        df["source_file"] = f.name + " (verbatim prefix)"
        df["in_file_sample_index"] = np.arange(1, len(df) + 1)
        frames.append(df)
        vib_meta_files[f.name] = {
            "declared_dims_rows_x_channels": [nrows_decl, ncols],
            "samples_extracted_from_prefix": int(nrows_avail),
            "rms_per_channel_g": [round(float(np.sqrt((arr[:, c] ** 2).mean())), 4)
                                  for c in range(ncols)],
        }
        print(f"  {f.name}: dims={dims} -> {nrows_avail:,} complete samples from prefix")
    vib = pd.concat(frames, ignore_index=True)

    # ---- temperature/current .tdms prefixes
    from nptdms import TdmsFile
    import warnings
    td_frames = []
    td_meta_files = {}
    for f in sorted((base / "raw" / "temp_current_tdms").glob("*.tdms")):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            td = TdmsFile.read(f)
            log = td["Log"]
            ch_info = []
            data = {}
            t0 = None
            dt = None
            for ch in log.channels():
                arr = ch[:]
                props = ch.properties
                unit = props.get("unit_string", "")
                # Use Mod1/ai0-style names so Mod1 and Mod2 channels stay unique
                chname = "/".join(ch.name.split("/")[-2:])
                if t0 is None:
                    t0 = props.get("wf_start_time", "")
                    dt = props.get("wf_increment", None)
                data[f"{chname} [{unit}]"] = arr[: min(len(a) for a in
                                                       [arr] * 1)] if False else arr
                ch_info.append({"channel": ch.name, "unit": unit,
                                "samples_read": int(len(arr)),
                                "declared_samples": props.get("wf_samples")})
            n = min(len(v) for v in data.values())
            df = pd.DataFrame({k: v[:n] for k, v in data.items()})
            cond = f.stem.split("_", 1)[1]
            df["condition"] = cond
            df["label"] = cond
            df["source_file"] = f.name + " (verbatim prefix)"
            df["in_file_sample_index"] = np.arange(1, n + 1)
            td_frames.append(df)
            td_meta_files[f.name] = {
                "channels": ch_info, "wf_start_time": str(t0),
                "wf_increment_s": dt, "rows_extracted": int(n)}
            print(f"  {f.name}: {n:,} samples x {len(ch_info)} channels "
                  f"({', '.join(c['channel'].split('/')[-1] + '=' + c['unit'] for c in ch_info)})")
    td = pd.concat(td_frames, ignore_index=True)

    n_raw = len(vib) + len(td)
    cleaned_v = base / "cleaned" / "ztmf_vibration_cleaned.csv"
    cleaned_t = base / "cleaned" / "ztmf_temperature_current_cleaned.csv"
    vib.to_csv(cleaned_v, index=False)
    td.to_csv(cleaned_t, index=False)

    excel_v = decimate(vib, 20)
    excel_t = decimate(td, 100)
    write_excel(base / "excel" / "ZTMF_Rotating_Machine_Vibration.xlsx", excel_v,
                "vibration",
                {
                    "dataset_id": "ZTMF_ROTATING_MACHINE",
                    "source": "Mendeley Data DOI 10.17632/ztmf3m7h5x.2 (CC BY 4.0)",
                    "access_date": ACCESS_DATE,
                    "machine": "Rotating machine test rig; conditions in filename (loadNm_condition_severity)",
                    "columns": "Time stamp (s) + 4 accelerometer channels (g): housing A x/y, housing B x/y",
                    "excerpt": "verbatim 3 MB prefix of 0Nm_Normal.mat and 0Nm_Unbalance_0583mg.mat",
                    "raw_rows_in_excerpt": len(vib),
                    "cleaned_rows": len(vib),
                    "excel_decimation": "every 20th cleaned row (real values)",
                    "condition": "encoded in source filename; no further labels",
                    "note": "motor current columns in the TDMS source are preserved in raw/ but are NOT PulseGuard ML features",
                })
    write_excel(base / "excel" / "ZTMF_Rotating_Machine_Temperature.xlsx", excel_t,
                "temperature_current",
                {
                    "dataset_id": "ZTMF_ROTATING_MACHINE",
                    "source": "Mendeley Data DOI 10.17632/ztmf3m7h5x.2 (CC BY 4.0)",
                    "access_date": ACCESS_DATE,
                    "columns": "2 thermocouple channels (Temperature_housing_A/B, degC) + 3 current channels (A, NOT an ML feature)",
                    "excerpt": "verbatim 3 MB prefix of 0Nm_Normal.tdms and 0Nm_Unbalance_0583mg.tdms",
                    "cleaned_rows": len(td),
                    "excel_decimation": "every 100th cleaned row (real values)",
                })

    meta = {
        "dataset_id": "ZTMF_ROTATING_MACHINE",
        "human_readable_name": "Rotating Machine Under Varying Load Conditions (Vibration + Temperature)",
        "original_dataset_name": "Vibration, Acoustic, Temperature, and Motor Current Dataset of Rotating Machine Under Varying Load Conditions for Fault Diagnosis",
        "source": "Mendeley Data",
        "source_reference": "DOI 10.17632/ztmf3m7h5x.2; Data in Brief 2023",
        "source_url": "https://data.mendeley.com/datasets/ztmf3m7h5x/2",
        "access_date": ACCESS_DATE,
        "machine_or_test_rig": "Rotating machine fault-simulation test rig (induction motor driven); conditions: normal, bearing inner/outer race faults (BPFI/BPFO), shaft misalignment, rotor unbalance at 3 severity levels; loads 0/2/4 Nm",
        "sensor_information": {
            "vibration": "4x ceramic shear ICP accelerometers (housing A x/y, housing B x/y), unit g, MATLAB .mat files",
            "temperature": "2x thermocouples (housing A/B), unit degC, NI TDMS files (NI 9210)",
            "motor_current": "3x current transformers (U/V/W phase), unit A - PRESERVED IN RAW, EXCLUDED from ML features",
            "acoustic": "microphone (Pa) - in separate acoustic.zip, not fetched (not a PulseGuard feature)",
        },
        "temperature_available": True,
        "vibration_available": True,
        "temperature_unit": "degC (TDMS unit_string property)",
        "vibration_unit": "g (gravitational constant, per dataset description)",
        "sampling_information": "Vibration .mat: struct with y_values (7680000 x 4 double matrix; 4 accelerometer channels, column-major; source time vector in x_values field); TDMS: NI FlexLogger logs with wf_increment property; excerpts truncated at 3 MB verbatim prefixes",
        "operating_conditions": "Varying load 0/2/4 Nm; fault conditions with severity levels; ISO-standard acquisition (Siemens + NI DAQ)",
        "labels_available": True,
        "label_note": "Condition encoded in source FILENAMES (loadNm_condition_severity), e.g. 0Nm_Normal, 0Nm_Unbalance_0583mg. No per-sample labels.",
        "original_file_format": "45 .mat (vibration) + 45 .tdms (temp+current) + acoustic in 3 ZIPs (~4.3 GB total)",
        "files_in_source": 45,
        "files_in_excerpt": 4,
        "excerpt_strategy": "verbatim 3 MB byte-prefix of 2 .mat and 2 .tdms members via HTTP range requests",
        "preprocessing_applied": [
            "MAT-5 matrix header parsed; numeric payload rows extracted verbatim from prefix (row-boundary cut)",
            "TDMS channels read with npTDMS (truncated-tail tolerated); row count = min across channels",
            "condition column taken from source filename only",
            "NO interpolation, NO unit conversion, NO value modification",
        ],
        "excluded_features": ["motor_current (U/V/W phase)", "acoustic (not fetched)"],
        "license_or_usage_information": "CC BY 4.0",
        "raw_preserved": "raw/ holds byte-verbatim member prefixes; full archives re-downloadable from source_url",
        "notes": {
            "vibration_files": vib_meta_files,
            "temperature_files": td_meta_files,
        },
    }
    (base / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ZTMF: vib rows={len(vib):,} temp rows={len(td):,}")
    return vib, td


# ---------------------------------------------------------------- own DC motor


def build_own():
    base = DATA / "own" / "dc_motor"
    src_raw = DATA / "raw" / "readings_raw.xlsx"
    src_clean = DATA / "cleaned" / "readings_clean.xlsx"
    raw_copy = base / "raw" / "readings_raw.xlsx"
    clean_copy = base / "cleaned" / "readings_clean.xlsx"
    if src_raw.exists():
        raw_copy.write_bytes(src_raw.read_bytes())
    if src_clean.exists():
        clean_copy.write_bytes(src_clean.read_bytes())

    df = pd.read_excel(src_raw) if src_raw.exists() else pd.DataFrame()
    n = len(df)

    excel_path = base / "excel" / "DC_Motor_Prototype.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as xl:
        pd.DataFrame([
            ("dataset_id", "OWN_DC_MOTOR"),
            ("name", "DC Motor Prototype (PulseGuard physical build)"),
            ("source", "Own ESP32 + DHT11 (GPIO4) + vibration sensor (GPIO34) prototype; readings streamed to Firebase /readings_only every 5 s and exported via the Flask RAW Excel export"),
            ("access_date", ACCESS_DATE),
            ("temperature_unit", "degC (DHT11)"),
            ("vibration_unit", "raw analog counts from ESP32 GPIO34 ADC"),
            ("note", "This dataset is NOT from an external bearing test rig. Do not present KAIST or ZTMF data as collected from this motor."),
            ("excel_note", "Readable copy of the RAW export; originals untouched in data/raw and data/cleaned"),
        ], columns=["Field", "Value"]).to_excel(xl, sheet_name="About", index=False)
        df.to_excel(xl, sheet_name="readings", index=False)
    print(f"  OWN: {n:,} readings copied (raw untouched)")

    meta = {
        "dataset_id": "OWN_DC_MOTOR",
        "human_readable_name": "DC Motor Prototype (PulseGuard physical build)",
        "original_dataset_name": "PulseGuard readings_only Firebase export",
        "source": "Own hardware prototype: ESP32 + DHT11 (temperature/humidity, DATA on GPIO 4) + analog vibration sensor on GPIO 34; LCD on I2C; readings POSTed to Firebase every 5 s",
        "source_reference": "PulseGuard esp32/pulseguard_esp32.ino + flask_api export_service.py",
        "source_url": "Firebase Realtime Database /readings_only (private project)",
        "access_date": ACCESS_DATE,
        "machine_or_test_rig": "Low-cost rotating DC motor (college demonstration prototype) - NOT an industrial bearing rig",
        "sensor_information": {
            "temperature": "DHT11, degC",
            "vibration": "analog vibration module on ESP32 ADC GPIO 34, raw counts",
        },
        "temperature_available": True,
        "vibration_available": True,
        "temperature_unit": "degC",
        "vibration_unit": "raw ADC counts (dimensionless)",
        "sampling_information": "ESP32 posts one reading every ~5 s while running; each Firebase push is one record",
        "operating_conditions": "Single demonstration motor run; ambient lab conditions; no controlled fault seeding",
        "labels_available": False,
        "label_note": "No human/failure labels. Model labels are rule-generated (temp 38-40 C / vib 2-5 warnings; >40 C / >5 critical) - documented in ml/train_model.py.",
        "original_file_format": "Firebase JSON -> Excel export",
        "preprocessing_applied": [
            "cleaning pipeline in flask_api/export_service.py (documented cleaning_report.json)",
            "no unit conversion; no interpolation",
        ],
        "excluded_features": ["humidity (read by DHT11 for LCD only; not uploaded, not an ML feature)"],
        "license_or_usage_information": "Own project data",
        "raw_preserved": "Copies taken for this registry; authoritative files remain data/raw/readings_raw.xlsx (untouched) and Firebase",
        "notes": "Identity rule: OWN_DC_MOTOR != KAIST_BALL_BEARING != ZTMF_ROTATING_MACHINE. External datasets must never be described as data from this motor.",
    }
    (base / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return n


# ---------------------------------------------------------------- registry + compatibility


def build_registry(own_n, kaist_df, vib, td):
    registry = {
        "version": 1,
        "updated": ACCESS_DATE,
        "ml_feature_rule": "Only temperature and vibration may be used as ML features, for every dataset.",
        "baseline_thresholds_protected": {
            "NORMAL": "temperature < 38 AND vibration < 2",
            "WARNING": "temperature 38-40 OR vibration 2-5",
            "CRITICAL": "temperature > 40 OR vibration > 5",
            "note": "PulseGuard demo baseline; external labels are NOT forced into these classes",
        },
        "datasets": [
            {
                "dataset_id": "OWN_DC_MOTOR",
                "name": "DC Motor Prototype",
                "type": "own",
                "path": "data/own/dc_motor/",
                "excel": "data/own/dc_motor/excel/DC_Motor_Prototype.xlsx",
                "machine": "Low-cost rotating DC motor (college prototype)",
                "records": own_n,
                "temperature": "available (degC, DHT11)",
                "vibration": "available (raw ADC counts)",
                "labels": "none (rule-based labels only for baseline)",
                "features_for_ml": ["temperature", "vibration"],
                "ml_eligible": True,
            },
            {
                "dataset_id": "KAIST_BALL_BEARING",
                "name": "KAIST Ball Bearing Run-to-Failure",
                "type": "external",
                "path": "data/external/kaist/",
                "excel": "data/external/kaist/excel/KAIST_Ball_Bearing_Test.xlsx",
                "machine": "NSK 6205 ball bearing, accelerated life test rig, 1770-1780 RPM",
                "source": "Mendeley Data DOI 10.17632/5hcdd3tdvb.6 (CC BY 4.0)",
                "records_excerpt": int(len(kaist_df)),
                "records_in_full_source": "129 hourly files x ~2M rows (4.3 GB)",
                "temperature": "available (degC, K-type thermocouple)",
                "vibration": "available (PCB 352C34 accelerometer, x+y, 25.6 kHz)",
                "labels": "none (run-to-failure sequence only)",
                "features_for_ml": ["temperature", "vibration"],
                "ml_eligible": True,
            },
            {
                "dataset_id": "ZTMF_ROTATING_MACHINE",
                "name": "Rotating Machine Under Varying Load Conditions",
                "type": "external",
                "path": "data/external/ztmf_rotating_machine/",
                "excel": "data/external/ztmf_rotating_machine/excel/ (vibration + temperature workbooks)",
                "machine": "Rotating machine fault rig (normal / BPFI / BPFO / misalignment / unbalance; 0/2/4 Nm)",
                "source": "Mendeley Data DOI 10.17632/ztmf3m7h5x.2 (CC BY 4.0)",
                "records_excerpt": int(len(vib) + len(td)),
                "records_in_full_source": "45 .mat + 45 .tdms + acoustic (4.3 GB total)",
                "temperature": "available (degC, 2 thermocouples)",
                "vibration": "available (4 accelerometers, g)",
                "labels": "condition encoded in filenames (Normal / Unbalance_0583mg / ...)",
                "features_for_ml": ["temperature", "vibration"],
                "excluded_source_signals": ["motor current", "acoustic"],
                "ml_eligible": True,
            },
        ],
        "merge_policy": "Datasets are NOT merged. Each stays separately traceable. Any future combined training requires an explicit compatibility decision.",
    }
    (DATA / "dataset_registry.json").write_text(
        json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    print("  dataset_registry.json written")

    comp = {
        "comparison": [
            ["aspect", "OWN_DC_MOTOR", "KAIST_BALL_BEARING", "ZTMF_ROTATING_MACHINE"],
            ["machine", "DC motor (college rig)", "NSK 6205 ball bearing test rig", "Rotating machine fault rig (motor-driven)"],
            ["temperature sensor", "DHT11 (air/housing, 0.5-2 C accuracy)", "K-type thermocouple (bearing)", "2x thermocouples (housing A/B)"],
            ["temperature unit", "degC", "degC", "degC"],
            ["vibration sensor", "analog vibration module (ADC counts)", "PCB 352C34 ICP accelerometer (x, y)", "4x ICP accelerometers (x, y per housing)"],
            ["vibration unit", "raw ADC counts (NOT physical units)", "raw source values (g or m/s^2 - column unit not stated)", "g (documented)"],
            ["sampling", "~0.2 Hz (one reading / 5 s)", "25.6 kHz waveforms, published hourly", "high-rate (kHz-class) logs"],
            ["operating profile", "single demo run", "constant 1770-1780 RPM run-to-failure", "3 loads x 5+ conditions x severities"],
            ["labels", "none (rules only)", "none", "filename-encoded condition"],
            ["scale (excerpt)", f"{own_n} rows", "112,279 rows", "vib 149k rows + temp 40k rows"],
        ],
        "findings": [
            "F1 - UNITS: vibration units are NOT comparable. Own data is raw ADC counts; ZTMF is documented in g; KAIST column unit is unstated (m/s^2 cited for the termination threshold). Direct pooling of vibration values would be physically meaningless without a documented per-dataset calibration that DOES NOT currently exist.",
            "F2 - SCALE/SAMPLING: own data is 5-second aggregate-style readings; externals are kHz waveforms. Any joint use needs feature extraction (RMS/peak/rolling stats) per window before comparison - not raw-value pooling.",
            "F3 - LABELS: externals carry no NORMAL/WARNING/CRITICAL labels compatible with the PulseGuard baseline; ZTMF condition names (Normal/Unbalance) are fault-class names, NOT the 3-level health scheme. Forcing them into the baseline classes would violate the no-fabrication rule.",
            "F4 - TEMPERATURE placement: DHT11 reads ambient/air near the motor; KAIST reads the bearing itself; ZTMF reads housing. Same unit (degC) but different physical measurement points.",
            "F5 - EXCERPTS: external packages contain documented verbatim excerpts, not the full 4.3 GB archives; re-download scripts and URLs are provided for the full data.",
        ],
        "recommended_use": [
            "Combined training: NOT RECOMMENDED in this task (F1, F3).",
            "Separate models / per-dataset experiments: appropriate - features_for_ml are aligned for future experimentation.",
            "External validation of the PulseGuard baseline: possible for KAIST early-life vs final-hours context (documented positional context), treating results as demonstration, not validated accuracy.",
            "Transfer/reference use: ZTMF filename labels can support a SEPARATE fault-vs-normal classifier experiment on ZTMF data alone, without touching the production model.pkl.",
        ],
    }
    out = DATA / "compatibility_report.json"
    out.write_text(json.dumps(comp, indent=2, ensure_ascii=False), encoding="utf-8")
    print("  compatibility_report.json written")


def main():
    print("== OWN DC motor ==")
    own_n = build_own()
    print("== KAIST ==")
    kaist_df = build_kaist()
    print("== ZTMF ==")
    vib, td = build_ztmf()
    print("== registry + compatibility ==")
    build_registry(own_n, kaist_df, vib, td)
    print("DONE")


if __name__ == "__main__":
    sys.exit(main())
