"""
Export & Data Cleaning Service for PulseGuard

Pipeline (required by project spec):

    Firebase /readings_only
        -> RAW EXCEL          (data/raw/readings_raw.xlsx  - untouched original)
        -> DATA CLEANING      (documented, conservative)
        -> CLEAN EXCEL        (data/cleaned/readings_clean.xlsx)

The raw Excel is written FIRST and is never modified afterwards. Cleaning
produces a separate file plus a machine-readable cleaning report so every
removed/changed row is auditable.

Cleaning rules (conservative, documented):
- Drop rows where temperature/vibration are missing or non-numeric
- Drop duplicates (same record_id, or identical temp+vib+timestamp)
- Flag but PRESERVE physically-impossible values (out of DHT11/ADC range)
  in an 'excluded_out_of_range' column instead of deleting them
- Normalize timestamps to epoch milliseconds and ISO datetime
- Sort chronologically
- NO interpolation / gap filling (documented: not used)

Only real sensor inputs are used: temperature, vibration, timestamp.
No humidity or other fabricated columns are added.
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Project root: PulseGuard/
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "cleaned"
EXPORTS_DIR = DATA_DIR / "exports"

# Physically plausible ranges for this hardware:
# - DHT11 measures 0-50 C (spec), allow small margin
# - Vibration from 12-bit ADC normalized to 0-20 by the ESP32 sketch
TEMP_MIN, TEMP_MAX = -10.0, 60.0
VIB_MIN, VIB_MAX = 0.0, 20.0


class ExportService:
    """Firebase readings -> raw Excel -> clean Excel with cleaning report."""

    def __init__(self, firebase_service=None):
        from firebase_service import get_firebase_service
        self.firebase = firebase_service or get_firebase_service()
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        CLEAN_DIR.mkdir(parents=True, exist_ok=True)
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # DataFrame builders
    # ------------------------------------------------------------
    def readings_to_dataframe(self, readings: Optional[List[Dict]] = None) -> pd.DataFrame:
        """
        Build the RAW dataframe from Firebase readings.

        RAW = exactly what the device sent (temperature, vibration,
        timestamp as sent) plus the Firebase record_id/push key for
        traceability. Values are NOT modified.
        """
        if readings is None:
            readings = self.firebase.get_all_readings()

        rows = []
        for r in readings:
            rows.append({
                'record_id': r.get('record_id') or r.get('_key'),
                'firebase_key': r.get('_key'),
                'temperature': r.get('temperature'),
                'vibration': r.get('vibration'),
                'timestamp': r.get('timestamp'),  # raw device value
                'sensor_ts_raw': r.get('sensor_ts_raw'),
                'push_key_time_ms': r.get('timestamp') if r.get('sensor_ts_raw') is not None else None,
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------
    # RAW Excel export
    # ------------------------------------------------------------
    def export_raw_excel(self, output_path: Path = None) -> Dict[str, Any]:
        """
        Export ALL Firebase readings to the RAW Excel file (untouched).
        """
        df = self.readings_to_dataframe()
        output_path = Path(output_path) if output_path else RAW_DIR / "readings_raw.xlsx"

        df.to_excel(output_path, index=False, engine='openpyxl')

        result = {
            'file': str(output_path),
            'rows': len(df),
            'exported_at': datetime.now().isoformat(),
            'source': f"{self.firebase.base_url}readings_only.json",
            'note': 'RAW export - values preserved exactly as received from device'
        }
        logger.info(f"RAW Excel exported: {result['rows']} rows -> {output_path}")
        return result

    # ------------------------------------------------------------
    # Cleaning pipeline
    # ------------------------------------------------------------
    def clean_dataframe(self, raw_df: pd.DataFrame) -> tuple:
        """
        Clean the raw dataframe. Returns (clean_df, report_dict).

        Every action is counted and documented in the report.
        """
        report: Dict[str, Any] = {
            'input_rows': len(raw_df),
            'removed_missing_sensor_values': 0,
            'removed_duplicates': 0,
            'flagged_out_of_range': 0,
            'interpolated_values': 0,  # always 0 - no interpolation by design
            'timestamp_fixed_to_epoch_ms': 0,
            'output_rows': 0,
            'rules_applied': [
                'Drop rows with missing/non-numeric temperature or vibration',
                'Drop duplicate records (same record_id, or same temp+vibration+timestamp)',
                'Flag out-of-range values in excluded_out_of_range column (preserved, not deleted)',
                f'Valid ranges: temperature {TEMP_MIN}..{TEMP_MAX} C, vibration {VIB_MIN}..{VIB_MAX}',
                'Timestamps normalized to epoch milliseconds (device uptime values replaced by Firebase push-key time)',
                'No interpolation or gap-filling performed',
            ],
            'performed_at': datetime.now().isoformat(),
        }

        if raw_df.empty:
            report['output_rows'] = 0
            return pd.DataFrame(), report

        df = raw_df.copy()

        # 1. Numeric coercion - drop rows where sensors are not numeric
        df['temperature'] = pd.to_numeric(df['temperature'], errors='coerce')
        df['vibration'] = pd.to_numeric(df['vibration'], errors='coerce')
        missing_mask = df['temperature'].isna() | df['vibration'].isna()
        report['removed_missing_sensor_values'] = int(missing_mask.sum())
        df = df[~missing_mask]

        # 2. Duplicates - by record_id first, then by sensor signature
        before = len(df)
        df = df.drop_duplicates(subset=['record_id'], keep='first')
        df = df.drop_duplicates(
            subset=['temperature', 'vibration', 'timestamp'], keep='first'
        )
        report['removed_duplicates'] = int(before - len(df))

        # 3. Timestamp normalization to epoch ms
        #    Firebase push-key time is the reliable arrival time.
        if 'firebase_key' in df.columns:
            from firebase_service import normalize_timestamp_ms
            fixed = df.apply(
                lambda row: normalize_timestamp_ms(
                    row.get('sensor_ts_raw') if pd.notna(row.get('sensor_ts_raw')) else row.get('timestamp'),
                    row.get('firebase_key') or ''
                ),
                axis=1
            )
            report['timestamp_fixed_to_epoch_ms'] = int((fixed != df['timestamp']).sum())
            df['timestamp'] = fixed
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce')

        # 4. Out-of-range flagging (PRESERVED, not deleted)
        def out_of_range(row):
            flags = []
            if not (TEMP_MIN <= row['temperature'] <= TEMP_MAX):
                flags.append('temperature')
            if not (VIB_MIN <= row['vibration'] <= VIB_MAX):
                flags.append('vibration')
            return ','.join(flags)

        flags = df.apply(out_of_range, axis=1)
        df['excluded_out_of_range'] = flags.where(flags != '', '')
        report['flagged_out_of_range'] = int((df['excluded_out_of_range'] != '').sum())

        # 5. Chronological sort
        df = df.sort_values('timestamp').reset_index(drop=True)

        report['output_rows'] = len(df)
        return df, report

    def export_clean_excel(self, output_path: Path = None) -> Dict[str, Any]:
        """
        Run the full pipeline: raw export -> clean -> CLEAN Excel + report.
        The raw file is (re)generated first, then left untouched.
        """
        raw_result = self.export_raw_excel()

        raw_df = self.readings_to_dataframe()
        clean_df, report = self.clean_dataframe(raw_df)

        clean_path = Path(output_path) if output_path else CLEAN_DIR / "readings_clean.xlsx"
        clean_df.to_excel(clean_path, index=False, engine='openpyxl')

        # Machine-readable cleaning report alongside the clean file
        import json
        report_path = CLEAN_DIR / "cleaning_report.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(
            f"CLEAN Excel exported: {report['output_rows']} rows "
            f"(removed {report['removed_missing_sensor_values']} invalid, "
            f"{report['removed_duplicates']} duplicates, "
            f"flagged {report['flagged_out_of_range']} out-of-range) -> {clean_path}"
        )

        return {
            'raw': raw_result,
            'clean': {
                'file': str(clean_path),
                'rows': report['output_rows'],
            },
            'report': report,
            'report_file': str(report_path),
        }


# Singleton instance
_export_service = None


def get_export_service() -> ExportService:
    """Get or create singleton export service instance."""
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service
