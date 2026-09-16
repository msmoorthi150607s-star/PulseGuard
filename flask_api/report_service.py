"""
Report Service for PulseGuard

Generates PDF and Excel reports for Admin (simple) and Technical Team
(detailed), plus maintenance report documents.

Formats (per project spec):
- PDF    = human-readable report
- Excel  = structured / filterable data
- RAW Excel is a separate untouched sensor export (see export_service)

Libraries: reportlab (PDF), openpyxl (Excel).
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
EXPORTS_DIR = PROJECT_ROOT / "data" / "exports"

# Try to import reportlab - degrade gracefully if unavailable
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not installed - PDF export disabled")

STATUS_COLORS = {
    'NORMAL': colors.HexColor('#3D9970'),
    'WARNING': colors.HexColor('#F0A030'),
    'CRITICAL': colors.HexColor('#E74C3C'),
    'REQUESTED': colors.HexColor('#F0A030'),
    'ACCEPTED': colors.HexColor('#4FC3D9'),
    'VISITED': colors.HexColor('#4FC3D9'),
    'IN_PROGRESS': colors.HexColor('#4FC3D9'),
    'FIXED': colors.HexColor('#3D9970'),
    'COMPLETED': colors.HexColor('#3D9970'),
}


class ReportService:
    """Builds PDF and Excel reports from Firebase data."""

    # Whether PDF generation is possible on this machine
    REPORTLAB_AVAILABLE = REPORTLAB_AVAILABLE

    def __init__(self, firebase_service=None):
        from firebase_service import get_firebase_service
        self.firebase = firebase_service or get_firebase_service()
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # Data assembly
    # ------------------------------------------------------------
    def _machine_name(self, machine_id: str, machines: List[Dict]) -> str:
        for m in machines:
            if m.get('machine_id') == machine_id:
                return m.get('machine_name', machine_id)
        return machine_id or 'Unregistered'

    def _ts(self, ms) -> str:
        if not ms:
            return '-'
        try:
            return datetime.fromtimestamp(int(ms) / 1000).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(ms)

    def build_admin_data(self) -> Dict[str, Any]:
        """Simple, owner-oriented summary data."""
        machines = self.firebase.get_machines()
        requests = self.firebase.get_service_requests(limit=200)
        reports = self.firebase.get_maintenance_reports(limit=200)

        # Monthly / 6-month summaries of completed maintenance
        now = datetime.now()
        monthly, six_month = [], []
        for r in reports:
            completed = r.get('completed_at')
            if not completed:
                continue
            try:
                dt = datetime.fromtimestamp(int(completed) / 1000)
            except Exception:
                continue
            if dt.year == now.year and dt.month == now.month:
                monthly.append(r)
            if (now - dt).days <= 183:
                six_month.append(r)

        return {
            'machines': machines,
            'service_requests': requests,
            'maintenance_reports': reports,
            'monthly_summary': monthly,
            'six_month_summary': six_month,
            'generated_at': datetime.now().isoformat(),
        }

    def build_technical_data(self, machine_id: Optional[str] = None) -> Dict[str, Any]:
        """Detailed, technician-oriented data including readings + predictions."""
        machines = self.firebase.get_machines()
        if machine_id:
            machines = [m for m in machines if m.get('machine_id') == machine_id]

        readings = self.firebase.get_readings(limit=100)
        predictions = self.firebase.get_predictions(limit=100)
        requests = self.firebase.get_service_requests(limit=200)
        reports = self.firebase.get_maintenance_reports(limit=200)

        return {
            'machines': machines,
            'readings': readings,
            'predictions': predictions,
            'service_requests': requests,
            'maintenance_reports': reports,
            'generated_at': datetime.now().isoformat(),
        }

    # ------------------------------------------------------------
    # PDF generation
    # ------------------------------------------------------------
    def _pdf_header(self, story, title: str, subtitle: str):
        styles = getSampleStyleSheet()
        h = ParagraphStyle(
            'PGHeader', parent=styles['Title'], fontSize=20,
            textColor=colors.HexColor('#1A2024'), spaceAfter=2
        )
        sub = ParagraphStyle(
            'PGSub', parent=styles['Normal'], fontSize=10,
            textColor=colors.HexColor('#7A848D'), spaceAfter=12
        )
        story.append(Paragraph(title, h))
        story.append(Paragraph(subtitle, sub))

    def _table(self, headers: List[str], rows: List[List[str]]) -> Table:
        data = [headers] + rows
        t = Table(data, colWidths=[None] * len(headers))
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A2024')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#C8D0D6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#F4F6F8')]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return t

    def generate_admin_pdf(self, output_path: Path = None) -> Dict[str, Any]:
        """Simple maintenance report for the Admin/Owner."""
        if not REPORTLAB_AVAILABLE:
            return {'success': False, 'message': 'reportlab not installed'}

        data = self.build_admin_data()
        output_path = Path(output_path) if output_path else (
            EXPORTS_DIR / f"pulseguard_admin_report_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        )

        doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                                title="PulseGuard Admin Report")
        story = []
        styles = getSampleStyleSheet()
        self._pdf_header(
            story, "PulseGuard - Maintenance Summary",
            f"Owner report | Generated {self._ts(datetime.now().timestamp()*1000)}"
        )

        # Machines overview
        story.append(Paragraph("Registered Machines", styles['Heading2']))
        if data['machines']:
            rows = [[m.get('machine_id'), m.get('machine_name'),
                     m.get('machine_type'), m.get('location'),
                     str(m.get('current_health', '-')),
                     str(m.get('status', '-'))]
                    for m in data['machines']]
            story.append(self._table(
                ['ID', 'Name', 'Type', 'Location', 'Health', 'Status'], rows))
        else:
            story.append(Paragraph(
                "No machines registered yet.", styles['Normal']))
        story.append(Spacer(1, 0.5 * cm))

        # Service requests
        story.append(Paragraph("Service Requests", styles['Heading2']))
        if data['service_requests']:
            rows = [[r.get('request_id', '')[:12], r.get('machine_id'),
                     str(r.get('issue', ''))[:30], str(r.get('status')),
                     self._ts(r.get('requested_at'))]
                    for r in data['service_requests'][:15]]
            story.append(self._table(
                ['Request', 'Machine', 'Issue', 'Status', 'Requested'], rows))
        else:
            story.append(Paragraph("No service requests.", styles['Normal']))
        story.append(Spacer(1, 0.5 * cm))

        # Maintenance summary
        story.append(Paragraph("Maintenance History", styles['Heading2']))
        if data['maintenance_reports']:
            rows = [[r.get('machine_id'),
                     str(r.get('problem_found', ''))[:35],
                     str(r.get('action_taken', ''))[:35],
                     self._ts(r.get('completed_at'))]
                    for r in data['maintenance_reports'][:15]]
            story.append(self._table(
                ['Machine', 'Problem Found', 'Action Taken', 'Completed'], rows))
        else:
            story.append(Paragraph("No maintenance reports.", styles['Normal']))
        story.append(Spacer(1, 0.5 * cm))

        story.append(Paragraph(
            f"This month: {len(data['monthly_summary'])} maintenance tasks | "
            f"Last 6 months: {len(data['six_month_summary'])}",
            styles['Normal']))

        doc.build(story)
        return {'success': True, 'file': str(output_path),
                'format': 'pdf', 'type': 'admin'}

    def generate_technical_pdf(self, machine_id: Optional[str] = None,
                               output_path: Path = None) -> Dict[str, Any]:
        """Detailed technical report including readings and predictions."""
        if not REPORTLAB_AVAILABLE:
            return {'success': False, 'message': 'reportlab not installed'}

        data = self.build_technical_data(machine_id)
        scope = machine_id or 'ALL-MACHINES'
        output_path = Path(output_path) if output_path else (
            EXPORTS_DIR /
            f"pulseguard_technical_report_{scope}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        )

        doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                                title="PulseGuard Technical Report")
        story = []
        styles = getSampleStyleSheet()
        self._pdf_header(
            story, "PulseGuard - Technical Report",
            f"Scope: {scope} | Generated {self._ts(datetime.now().timestamp()*1000)}"
        )

        # Readings
        story.append(Paragraph("Recent Sensor Readings (last 100)", styles['Heading2']))
        if data['readings']:
            rows = [[self._ts(r.get('timestamp')),
                     f"{r.get('temperature', 0):.1f}",
                     f"{r.get('vibration', 0):.2f}"]
                    for r in data['readings'][:25]]
            story.append(self._table(
                ['Timestamp', 'Temp (C)', 'Vibration'], rows))
        else:
            story.append(Paragraph("No readings available.", styles['Normal']))
        story.append(Spacer(1, 0.5 * cm))

        # Predictions
        story.append(Paragraph("Prediction History (last 100)", styles['Heading2']))
        if data['predictions']:
            rows = [[self._ts(p.get('timestamp')), p.get('record_id', '')[:16],
                     str(p.get('prediction', '')).upper()]
                    for p in data['predictions'][:25]]
            story.append(self._table(
                ['Timestamp', 'Record', 'Prediction'], rows))
        else:
            story.append(Paragraph("No predictions available.", styles['Normal']))
        story.append(Spacer(1, 0.5 * cm))

        # Service timeline
        story.append(Paragraph("Service Request Timeline", styles['Heading2']))
        if data['service_requests']:
            rows = [[r.get('request_id', '')[:12], r.get('machine_id'),
                     self._ts(r.get('requested_at')),
                     self._ts(r.get('accepted_at')),
                     self._ts(r.get('visited_at')),
                     self._ts(r.get('completed_at')),
                     str(r.get('status'))]
                    for r in data['service_requests'][:15]]
            story.append(self._table(
                ['Request', 'Machine', 'Requested', 'Accepted',
                 'Visited', 'Completed', 'Status'], rows))
        else:
            story.append(Paragraph("No service requests.", styles['Normal']))
        story.append(Spacer(1, 0.5 * cm))

        # Maintenance details
        story.append(Paragraph("Maintenance Details", styles['Heading2']))
        if data['maintenance_reports']:
            rows = [[r.get('machine_id'),
                     str(r.get('problem_found', ''))[:30],
                     str(r.get('action_taken', ''))[:30],
                     str(r.get('parts_replaced', ''))[:20],
                     str(r.get('technician_notes', ''))[:30],
                     self._ts(r.get('completed_at'))]
                    for r in data['maintenance_reports'][:15]]
            story.append(self._table(
                ['Machine', 'Problem', 'Action', 'Parts', 'Notes', 'Completed'], rows))
        else:
            story.append(Paragraph("No maintenance reports.", styles['Normal']))

        doc.build(story)
        return {'success': True, 'file': str(output_path),
                'format': 'pdf', 'type': 'technical'}

    # ------------------------------------------------------------
    # Excel reports (structured data - NOT the raw sensor export)
    # ------------------------------------------------------------
    def generate_admin_excel(self, output_path: Path = None) -> Dict[str, Any]:
        """Simple maintenance workbook for the Admin/Owner."""
        data = self.build_admin_data()
        output_path = Path(output_path) if output_path else (
            EXPORTS_DIR / f"pulseguard_admin_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        )

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            pd.DataFrame([{
                'machine_id': m.get('machine_id'),
                'machine_name': m.get('machine_name'),
                'machine_type': m.get('machine_type'),
                'location': m.get('location'),
                'health': m.get('current_health'),
                'status': m.get('status'),
            } for m in data['machines']]).to_excel(
                writer, sheet_name='Machines', index=False)

            pd.DataFrame([{
                'request_id': r.get('request_id'),
                'machine_id': r.get('machine_id'),
                'issue': r.get('issue'),
                'status': r.get('status'),
                'requested_at': self._ts(r.get('requested_at')),
                'completed_at': self._ts(r.get('completed_at')),
            } for r in data['service_requests']]).to_excel(
                writer, sheet_name='Service Requests', index=False)

            pd.DataFrame([{
                'machine_id': r.get('machine_id'),
                'problem_found': r.get('problem_found'),
                'action_taken': r.get('action_taken'),
                'parts_replaced': r.get('parts_replaced'),
                'completed_at': self._ts(r.get('completed_at')),
            } for r in data['maintenance_reports']]).to_excel(
                writer, sheet_name='Maintenance', index=False)

            pd.DataFrame([{
                'report_id': r.get('report_id'),
                'machine_id': r.get('machine_id'),
                'problem_found': r.get('problem_found'),
                'action_taken': r.get('action_taken'),
                'completed_at': self._ts(r.get('completed_at')),
            } for r in data['monthly_summary']]).to_excel(
                writer, sheet_name='This Month', index=False)

            pd.DataFrame([{
                'report_id': r.get('report_id'),
                'machine_id': r.get('machine_id'),
                'problem_found': r.get('problem_found'),
                'action_taken': r.get('action_taken'),
                'completed_at': self._ts(r.get('completed_at')),
            } for r in data['six_month_summary']]).to_excel(
                writer, sheet_name='Last 6 Months', index=False)

        return {'success': True, 'file': str(output_path),
                'format': 'excel', 'type': 'admin'}

    def generate_technical_excel(self, machine_id: Optional[str] = None,
                                 output_path: Path = None) -> Dict[str, Any]:
        """Detailed technical workbook: readings, predictions, services, maintenance."""
        data = self.build_technical_data(machine_id)
        scope = machine_id or 'ALL'
        output_path = Path(output_path) if output_path else (
            EXPORTS_DIR /
            f"pulseguard_technical_report_{scope}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        )

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            pd.DataFrame([{
                'timestamp': self._ts(r.get('timestamp')),
                'epoch_ms': r.get('timestamp'),
                'record_id': r.get('record_id'),
                'temperature': r.get('temperature'),
                'vibration': r.get('vibration'),
            } for r in data['readings']]).to_excel(
                writer, sheet_name='Readings', index=False)

            pd.DataFrame([{
                'prediction_id': p.get('prediction_id'),
                'record_id': p.get('record_id'),
                'prediction': p.get('prediction'),
                'timestamp': self._ts(p.get('timestamp')),
            } for p in data['predictions']]).to_excel(
                writer, sheet_name='Predictions', index=False)

            pd.DataFrame([{
                'request_id': r.get('request_id'),
                'machine_id': r.get('machine_id'),
                'issue': r.get('issue'),
                'prediction': r.get('prediction'),
                'status': r.get('status'),
                'requested_at': self._ts(r.get('requested_at')),
                'accepted_at': self._ts(r.get('accepted_at')),
                'visited_at': self._ts(r.get('visited_at')),
                'completed_at': self._ts(r.get('completed_at')),
            } for r in data['service_requests']]).to_excel(
                writer, sheet_name='Service Requests', index=False)

            pd.DataFrame([{
                'report_id': r.get('report_id'),
                'machine_id': r.get('machine_id'),
                'problem_found': r.get('problem_found'),
                'action_taken': r.get('action_taken'),
                'parts_replaced': r.get('parts_replaced'),
                'technician_notes': r.get('technician_notes'),
                'completed_at': self._ts(r.get('completed_at')),
            } for r in data['maintenance_reports']]).to_excel(
                writer, sheet_name='Maintenance', index=False)

        return {'success': True, 'file': str(output_path),
                'format': 'excel', 'type': 'technical'}


# Singleton instance
_report_service = None


def get_report_service() -> ReportService:
    """Get or create singleton report service instance."""
    global _report_service
    if _report_service is None:
        _report_service = ReportService()
    return _report_service
