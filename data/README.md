# PulseGuard Data Directory

This directory holds the data pipeline outputs. Sensor data itself lives in
Firebase (`/readings_only`) — this is where exports land.

```
data/
├── raw/       readings_raw.xlsx     - UNTOUCHED export of every Firebase reading
├── cleaned/   readings_clean.xlsx   - output of the documented cleaning pipeline
│              cleaning_report.json  - machine-readable log of every cleaning action
└── exports/   generated PDF / Excel reports (admin + technical)
```

## Integrity rules

- The RAW export is written first and is **never modified** afterwards.
- Cleaning produces a **separate** file; nothing is written back to Firebase.
- Every cleaning action is counted in `cleaning_report.json`
  (rows removed, duplicates dropped, out-of-range flagged — preserved, not
  deleted, and interpolation is always 0 because no gap-filling is done).
- Reports (PDF/Excel) in `exports/` are generated snapshots, separate from
  the RAW sensor export.

## Regenerating

From the Technical dashboard ("Data Pipeline" panel), or:

```cmd
cd flask_api
python -c "from export_service import get_export_service as g; print(g().export_clean_excel())"
```

`.xlsx` files are git-ignored to keep the repository light; the pipeline
recreates them from live Firebase data in a few seconds.
