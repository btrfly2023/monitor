import requests
import logging
import time
from .base import BaseNotifier

logger = logging.getLogger('blockchain_monitor.telegram')

class TelegramNotifier(BaseNotifier):
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    def send_message(self, message, urgent=False):
        """Send a message to the Telegram chat."""
        if not self.token or not self.chat_id:
            logger.error("Telegram token or chat_id not configured")
            return False

        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_notification": False  # Ensure sound notification
        }

        # Add emoji for urgent messages
        if urgent:
            data["text"] = "🚨 *URGENT ALERT* 🚨\n\n" + data["text"]

        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, data=data, timeout=30)
                response.raise_for_status()
                logger.info(f"Telegram message sent successfully")
                return True
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to send Telegram message (attempt {attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    return False

        return False

    def test_connection(self):
        """Test the connection to the Telegram API."""
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('ok'):
                logger.info(f"Telegram connection successful: {data.get('result', {}).get('username')}")
                return True
            else:
                logger.error(f"Telegram connection failed: {data.get('description')}")
                return False
        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False
