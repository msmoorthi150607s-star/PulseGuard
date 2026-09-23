# PulseGuard Data Directory

This directory holds the data pipeline outputs, the organised datasets and the
dataset registry. Live sensor data itself lives in Firebase
(`/readings_only`) — exports land here.

```
data/
├── raw/       readings_raw.xlsx          - UNTOUCHED export of every Firebase reading
├── cleaned/   readings_clean.xlsx        - output of the documented cleaning pipeline
│              cleaning_report.json       - machine-readable log of every cleaning action
├── exports/   generated PDF / Excel reports (admin + technical)
│
├── own/dc_motor/                          - OWN_DC_MOTOR (the physical prototype)
│   ├── raw/  copied from data/raw (originals untouched)
│   ├── cleaned/  copied from data/cleaned
│   ├── excel/  DC_Motor_Prototype.xlsx
│   └── metadata.json
│
├── external/                              - public research datasets (CC BY 4.0)
│   ├── fetch_external_datasets.py         - re-download script (HTTP range requests)
│   ├── kaist/        KAIST_BALL_BEARING   - run-to-failure bearing (vib + temp)
│   │   ├── raw/       verbatim CSV excerpts
│   │   ├── cleaned/   full parsed records (CSV)
│   │   ├── excel/     KAIST_Ball_Bearing_Test.xlsx
│   │   └── metadata.json
│   └── ztmf_rotating_machine/  ZTMF_ROTATING_MACHINE
│       ├── raw/       verbatim .mat (vibration) + .tdms (temp/current) prefixes
│       ├── cleaned/   full parsed records (CSV)
│       ├── excel/     ZTMF_Rotating_Machine_Vibration.xlsx + _Temperature.xlsx
│       └── metadata.json
│
├── dataset_registry.json                  - registry of all accepted datasets
├── compatibility_report.json              - unit/scale/label compatibility findings
└── build_dataset_packages.py              - rebuilds cleaned/excel/metadata/registry
```

## Dataset identity rule

`OWN_DC_MOTOR` ≠ `KAIST_BALL_BEARING` ≠ `ZTMF_ROTATING_MACHINE`.

The own dataset comes from the physical DC-motor prototype. The external
datasets are public research test rigs — they must never be presented as data
collected from the prototype. Each package keeps its own `metadata.json` with
source, license, units and sampling details.

## ML feature rule

Only `temperature` and `vibration` may be used as ML features for any
dataset. External signals preserved in raw form (e.g. ZTMF motor current,
acoustic) are explicitly excluded from the feature space. External condition
names (e.g. `Normal`, `Unbalance_0583mg`) are source labels and are NOT
forced into the PulseGuard NORMAL/WARNING/CRITICAL classes.

## Excerpts, not full archives

The complete external archives total ~8.6 GB. The `raw/` folders hold
**byte-verbatim excerpts** (prefixes of selected members, cut only at record
boundaries) fetched via HTTP range requests — original bytes, nothing
synthesised. `data/external/fetch_external_datasets.py` documents every
source URL and re-downloads everything.

## Integrity rules (live pipeline, unchanged)

- The RAW export is written first and is **never modified** afterwards.
- Cleaning produces a **separate** file; nothing is written back to Firebase.
- Every cleaning action is counted in `cleaning_report.json`
  (rows removed, duplicates dropped, out-of-range flagged — preserved, not
  deleted, and interpolation is always 0 because no gap-filling is done).
- Reports (PDF/Excel) in `exports/` are generated snapshots, separate from
  the RAW sensor export.
- External raw files are only ever read; cleaning writes to `cleaned/`.

## Regenerating

From the Technical dashboard ("Data Pipeline" panel), or:

```cmd
cd flask_api
python -c "from export_service import get_export_service as g; print(g().export_clean_excel())"
```

Rebuild the dataset packages (cleaned copies, Excel, metadata, registry):

```cmd
cd data
python build_dataset_packages.py
```

`.xlsx` files are git-ignored to keep the repository light; pipelines
recreate them from Firebase or from the preserved raw material in seconds.
