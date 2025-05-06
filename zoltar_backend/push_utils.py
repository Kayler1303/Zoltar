import logging
import os # Import os
from apns2.client import APNsClient
from apns2.payload import Payload
from dotenv import load_dotenv # Import load_dotenv

# Load environment variables from .env file (especially for local dev)
load_dotenv()

logger = logging.getLogger(__name__)

# --- Load APNs config from environment variables --- 
APNS_TEAM_ID = os.getenv("APNS_TEAM_ID")
APNS_AUTH_KEY_PATH = os.getenv("APNS_AUTH_KEY_PATH") # Path to the .p8 file
APNS_KEY_ID = os.getenv("APNS_KEY_ID")
APNS_TOPIC = os.getenv("APNS_TOPIC") # Your app's bundle ID
APNS_USE_SANDBOX_STR = os.getenv("APNS_USE_SANDBOX", "True") # Default to Sandbox
APNS_USE_SANDBOX = APNS_USE_SANDBOX_STR.lower() in ['true', '1', 'yes']
# --- End Load --- 

# Initialize APNs client globally
apns_client = None
if all([APNS_TEAM_ID, APNS_AUTH_KEY_PATH, APNS_KEY_ID, APNS_TOPIC]):
    try:
        apns_client = APNsClient(
            team_id=APNS_TEAM_ID,
            auth_key_path=APNS_AUTH_KEY_PATH,
            auth_key_id=APNS_KEY_ID,
            use_sandbox=APNS_USE_SANDBOX
        )
        logger.info(f"APNsClient initialized successfully (Sandbox: {APNS_USE_SANDBOX}).")
    except Exception as e:
        logger.error(f"Failed to initialize APNsClient from env vars: {e}", exc_info=True)
else:
    missing_vars = [var for var, val in {
        "APNS_TEAM_ID": APNS_TEAM_ID, 
        "APNS_AUTH_KEY_PATH": APNS_AUTH_KEY_PATH, 
        "APNS_KEY_ID": APNS_KEY_ID, 
        "APNS_TOPIC": APNS_TOPIC
    }.items() if not val]
    logger.warning(f"APNs client NOT initialized. Missing environment variables: {missing_vars}")


def send_apns_notification(device_token: str, alert_body: str, badge_count: int = 1, custom_data: dict = None):
    """Sends a push notification to a specific iOS device via APNs."""
    if not apns_client:
        logger.error("APNs client not initialized. Cannot send push notification.")
        return False

    if not device_token:
        logger.warning("No device token provided. Cannot send push notification.")
        return False

    # Basic alert payload
    payload = Payload(alert=alert_body, sound="default", badge=badge_count, mutable_content=True)

    # Add custom data if provided
    if custom_data:
        payload.custom = custom_data

    # Topic is now loaded from environment variable
    topic = APNS_TOPIC 

    try:
        logger.info(f"Sending APNs notification to token ending ...{device_token[-6:]} with body: '{alert_body}', topic: {topic}, sandbox: {APNS_USE_SANDBOX}")
        # Send the notification
        response = apns_client.send_notification(
            token_hex=device_token,
            notification_payload=payload,
            topic=topic
        )
        logger.info(f"APNs notification sent (or attempted). Response: {response}")
        return True 

    except Exception as e:
        logger.error(f"Failed to send APNs notification to token ending ...{device_token[-6:]}: {e}", exc_info=True)
        return False

# --- Example Usage Removed --- 