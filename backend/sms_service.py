# backend/services/sms_service.py
"""
SMS service for OTP delivery using Twilio.
Supports both direct SMS and Twilio Verify service.
"""
import structlog
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from config import get_settings

settings = get_settings()
logger = structlog.get_logger(__name__)


class SMSService:
    """Handles OTP delivery via Twilio SMS."""

    def __init__(self):
        if settings.twilio_account_sid and settings.twilio_auth_token:
            self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            self.enabled = True
        else:
            self.client = None
            self.enabled = False
            logger.warning("Twilio not configured - SMS disabled, using console mode")

    async def send_otp(self, phone_number: str, otp: str) -> bool:
        """
        Send OTP via SMS.
        Falls back to console logging in development mode.
        """
        message = (
            f"Your OTP Device Manager verification code is: {otp}\n"
            f"This code expires in {settings.otp_expiry_minutes} minutes.\n"
            f"Never share this code with anyone."
        )

        if not self.enabled or settings.app_env == "development":
            # Development mode: print to console instead of sending SMS
            logger.info(
                "DEV MODE - OTP (not sent via SMS)",
                phone=phone_number[-4:],  # Log only last 4 digits
                otp=otp,
            )
            return True

        try:
            msg = self.client.messages.create(
                body=message,
                from_=settings.twilio_phone_number,
                to=phone_number,
            )
            logger.info("OTP SMS sent", sid=msg.sid, phone=phone_number[-4:])
            return True

        except TwilioRestException as e:
            logger.error("Failed to send OTP SMS", error=str(e), phone=phone_number[-4:])
            return False

    async def send_verification_via_twilio_verify(
        self, phone_number: str
    ) -> tuple[bool, str]:
        """
        Alternative: Use Twilio Verify service (handles OTP generation internally).
        Returns (success, verification_sid)
        """
        if not self.enabled or not settings.twilio_verify_service_sid:
            return False, "Twilio Verify not configured"

        try:
            verification = self.client.verify.v2.services(
                settings.twilio_verify_service_sid
            ).verifications.create(to=phone_number, channel="sms")

            return True, verification.sid

        except TwilioRestException as e:
            logger.error("Twilio Verify failed", error=str(e))
            return False, str(e)

    async def check_twilio_verify(
        self, phone_number: str, code: str
    ) -> tuple[bool, str]:
        """Check a Twilio Verify OTP."""
        try:
            check = self.client.verify.v2.services(
                settings.twilio_verify_service_sid
            ).verification_checks.create(to=phone_number, code=code)

            if check.status == "approved":
                return True, "Verified"
            return False, "Invalid or expired code"

        except TwilioRestException as e:
            return False, str(e)


# Singleton instance
sms_service = SMSService()