"""
Email Service for PulseGuard

Handles email notifications for critical machine conditions.
Uses environment variables for SMTP configuration.
Includes cooldown/debounce mechanism to prevent spam.
"""

import os
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Email configuration from environment variables
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
MAIL_RECIPIENT = os.getenv('MAIL_RECIPIENT', '')
MAIL_SENDER = os.getenv('MAIL_SENDER', MAIL_USERNAME)

# Cooldown configuration (in seconds)
ALERT_COOLDOWN_SECONDS = int(os.getenv('ALERT_COOLDOWN_SECONDS', '3600'))  # 1 hour default

# Track last sent email
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
        self.sender = MAIL_SENDER
        self.cooldown_seconds = ALERT_COOLDOWN_SECONDS
        
        logger.info(f"Email service initialized")
        logger.info(f"SMTP Server: {self.smtp_server}:{self.smtp_port}")
        logger.info(f"Sender: {self.sender}")
        logger.info(f"Recipient: {self.recipient}")
        logger.info(f"Cooldown: {self.cooldown_seconds} seconds")
        
        # Check if email is properly configured
        if not self.username or not self.password or not self.recipient:
            logger.warning("Email not fully configured. Set MAIL_USERNAME, MAIL_PASSWORD, and MAIL_RECIPIENT.")
    
    def can_send_alert(self, status: str) -> bool:
        """
        Check if an alert can be sent (cooldown check).
        
        Args:
            status: Current machine status
            
        Returns:
            True if alert can be sent, False otherwise
        """
        global _last_alert_time, _last_alert_status
        
        # Only send for critical status
        if status != 'critical':
            return False
        
        # Check if cooldown has passed
        if _last_alert_time is not None:
            elapsed = datetime.now() - _last_alert_time
            if elapsed.total_seconds() < self.cooldown_seconds:
                logger.info(
                    f"Alert cooldown active. Last alert: {_last_alert_status} "
                    f"at {_last_alert_time}. Wait time remaining: "
                    f"{self.cooldown_seconds - elapsed.total_seconds():.0f}s"
                )
                return False
        
        return True
    
    def send_critical_alert(self, temperature: float, vibration: float, 
                           status: str = 'critical') -> Dict[str, Any]:
        """
        Send email alert for critical machine condition.
        
        Args:
            temperature: Current temperature
            vibration: Current vibration level
            status: Machine status (should be 'critical')
            
        Returns:
            Dictionary with send status and details
        """
        global _last_alert_time, _last_alert_status
        
        # Check cooldown
        if not self.can_send_alert(status):
            return {
                'success': False,
                'error': 'Alert cooldown active',
                'message': f'Alert already sent within last {self.cooldown_seconds} seconds'
            }
        
        # Validate configuration
        if not all([self.username, self.password, self.recipient]):
            return {
                'success': False,
                'error': 'Email not configured',
                'message': 'Set MAIL_USERNAME, MAIL_PASSWORD, and MAIL_RECIPIENT environment variables'
            }
        
        try:
            # Create email content
            subject = "[PULSEGUARD] Critical Machine Condition Detected"
            
            body = f"""
PulseGuard has detected a potentially abnormal machine condition.

Temperature: {temperature:.1f} °C
Vibration: {vibration:.2f}
Status: {status.upper()}

Please inspect the machine and consider contacting the maintenance team.

---
This is an automated message from PulseGuard Machine Health Monitoring System.
"""
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.sender
            msg['To'] = self.recipient
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            logger.info(f"Sending critical alert email to {self.recipient}")
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            # Update tracking
            _last_alert_time = datetime.now()
            _last_alert_status = status
            
            logger.info("Critical alert email sent successfully")
            
            return {
                'success': True,
                'message': 'Critical alert email sent successfully',
                'recipient': self.recipient,
                'subject': subject,
                'timestamp': datetime.now().isoformat()
            }
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return {
                'success': False,
                'error': 'Authentication failed',
                'message': f'SMTP authentication failed: {str(e)}'
            }
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return {
                'success': False,
                'error': 'SMTP error',
                'message': f'SMTP error occurred: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {
                'success': False,
                'error': 'Email send failed',
                'message': f'Failed to send email: {str(e)}'
            }
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test email connection without sending an actual email.
        
        Returns:
            Dictionary with connection status
        """
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
                'error': 'Connection test failed',
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
