"""
Email Service for PulseGuard

Handles email notifications:
- CRITICAL machine-condition alerts (with cooldown to prevent spam)
- Service-request acceptance notifications to the Admin/Owner
  (includes a tracking link)

Recipients: MAIL_RECIPIENT (admin/owner) and MAIL_TECH_RECIPIENT
(technical team). Credentials come from environment variables only -
never hard-coded.
"""

import os
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Email configuration from environment variables
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
MAIL_RECIPIENT = os.getenv('MAIL_RECIPIENT', '')
MAIL_TECH_RECIPIENT = os.getenv('MAIL_TECH_RECIPIENT', '')
MAIL_SENDER = os.getenv('MAIL_SENDER', MAIL_USERNAME)

# Dashboard base URL used in tracking links
DASHBOARD_URL = os.getenv('DASHBOARD_URL', 'http://localhost:8000')

# Cooldown configuration (in seconds)
ALERT_COOLDOWN_SECONDS = int(os.getenv('ALERT_COOLDOWN_SECONDS', '3600'))  # 1 hour default

# Track last sent alert (per status)
_last_alert_time: Optional[datetime] = None
_last_alert_status: Optional[str] = None


class EmailService:
    """Service class for email notifications."""

    def __init__(self):
        """Initialize email service."""
        self.smtp_server = SMTP_SERVER
        self.smtp_port = SMTP_PORT
        self.username = MAIL_USERNAME
        self.password = MAIL_PASSWORD
        self.recipient = MAIL_RECIPIENT
        self.tech_recipient = MAIL_TECH_RECIPIENT
        self.sender = MAIL_SENDER
        self.cooldown_seconds = ALERT_COOLDOWN_SECONDS
        self.dashboard_url = DASHBOARD_URL

        logger.info("Email service initialized")
        logger.info(f"SMTP Server: {self.smtp_server}:{self.smtp_port}")
        logger.info(f"Sender: {self.sender}")
        logger.info(f"Recipient (admin): {self.recipient}")
        logger.info(f"Recipient (technical): {self.tech_recipient}")
        logger.info(f"Cooldown: {self.cooldown_seconds} seconds")

        if not self.username or not self.password or not self.recipient:
            logger.warning(
                "Email not fully configured. Set MAIL_USERNAME, "
                "MAIL_PASSWORD, and MAIL_RECIPIENT."
            )

    # ------------------------------------------------------------
    # Internal send helper
    # ------------------------------------------------------------
    def _send(self, subject: str, body: str,
              recipients: List[str]) -> Dict[str, Any]:
        """Send an email to one or more recipients."""
        recipients = [r for r in recipients if r]
        if not recipients:
            return {
                'success': False,
                'error': 'no_recipient',
                'message': 'No recipient email configured'
            }

        if not all([self.username, self.password]):
            return {
                'success': False,
                'error': 'not_configured',
                'message': 'Set MAIL_USERNAME and MAIL_PASSWORD environment variables'
            }

        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            logger.info(f"Sending email '{subject}' to {recipients}")

            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=20) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info("Email sent successfully")
            return {
                'success': True,
                'message': 'Email sent successfully',
                'recipients': recipients,
                'subject': subject,
                'timestamp': datetime.now().isoformat()
            }

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return {
                'success': False,
                'error': 'authentication_failed',
                'message': (
                    'SMTP authentication failed. For Gmail, use a 16-char '
                    'App Password (Google Account > Security > App passwords).'
                )
            }
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return {
                'success': False,
                'error': 'smtp_error',
                'message': f'SMTP error occurred: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {
                'success': False,
                'error': 'send_failed',
                'message': f'Failed to send email: {str(e)}'
            }

    # ------------------------------------------------------------
    # Critical alert (with cooldown)
    # ------------------------------------------------------------
    def can_send_alert(self, status: str) -> bool:
        """Check whether the cooldown allows another CRITICAL alert."""
        global _last_alert_time

        if status != 'critical':
            return False

        if _last_alert_time is not None:
            elapsed = (datetime.now() - _last_alert_time).total_seconds()
            if elapsed < self.cooldown_seconds:
                logger.info(
                    f"Alert cooldown active. Remaining: "
                    f"{self.cooldown_seconds - elapsed:.0f}s"
                )
                return False
        return True

    def send_critical_alert(self, temperature: float, vibration: float,
                            status: str = 'critical',
                            machine_id: str = None) -> Dict[str, Any]:
        """Send a CRITICAL condition alert to admin + technical team."""
        global _last_alert_time, _last_alert_status

        if not self.can_send_alert(status):
            return {
                'success': False,
                'error': 'cooldown_active',
                'message': f'Alert already sent within last {self.cooldown_seconds} seconds'
            }

        machine_line = f"Machine: {machine_id}\n" if machine_id else ""
        subject = "[PULSEGUARD] Critical Machine Condition Detected"
        body = f"""PulseGuard has detected a potentially abnormal machine condition.

{machine_line}Temperature: {temperature:.1f} C
Vibration: {vibration:.2f}
Status: {status.upper()}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please inspect the machine and consider contacting the maintenance team.

Dashboard: {self.dashboard_url}

---
This is an automated message from PulseGuard Machine Health Monitoring System.
"""

        result = self._send(
            subject, body, [self.recipient, self.tech_recipient]
        )

        if result.get('success'):
            _last_alert_time = datetime.now()
            _last_alert_status = status

        return result

    # ------------------------------------------------------------
    # Service acceptance notification
    # ------------------------------------------------------------
    def send_service_accepted(self, request: Dict[str, Any],
                              accepted_by: str = '') -> Dict[str, Any]:
        """
        Notify the Admin/Owner that the Technical Team accepted their
        service request. Includes a tracking link.
        """
        request_id = request.get('request_id', '')
        machine_id = request.get('machine_id', 'Unknown machine')
        issue = request.get('issue', 'Not specified')

        subject = f"[PULSEGUARD] Service Request Accepted - {machine_id}"
        body = """Good news - your service request has been accepted.

Request ID: {req}
Machine: {machine}
Issue: {issue}
Accepted by: {tech}
Accepted at: {ts}

You can track the status of this request on the PulseGuard dashboard:
{dashboard}

---
This is an automated message from PulseGuard Machine Health Monitoring System.
""".format(
            req=request_id,
            machine=machine_id,
            issue=issue,
            tech=accepted_by or 'Technical Team',
            ts=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            dashboard=f"{self.dashboard_url}/admin/"
        )

        # Owner notification only (technical team already knows)
        return self._send(subject, body, [self.recipient])

    # ------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------
    def test_connection(self) -> Dict[str, Any]:
        """Test SMTP configuration without sending an email."""
        if not all([self.username, self.password]):
            return {
                'success': False,
                'error': 'not_configured',
                'message': 'Set MAIL_USERNAME and MAIL_PASSWORD in flask_api/.env'
            }
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.username, self.password)
                return {
                    'success': True,
                    'message': 'Email connection test successful',
                    'server': self.smtp_server,
                    'port': self.smtp_port
                }
        except Exception as e:
            return {
                'success': False,
                'error': 'connection_test_failed',
                'message': str(e)
            }


# Singleton instance
_email_service = None


def get_email_service() -> EmailService:
    """Get or create singleton email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


# For backward compatibility
email_service = get_email_service()
