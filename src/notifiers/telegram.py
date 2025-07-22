import requests
import logging
import time
from .base import BaseNotifier

logger = logging.getLogger('blockchain_monitor.telegram')

class TelegramNotifier(BaseNotifier):
    def __init__(self, token, chat_id, second_token=None, second_chat_id=None):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        
        # Second bot configuration
        self.second_token = second_token
        self.second_chat_id = second_chat_id
        self.second_base_url = f"https://api.telegram.org/bot{second_token}" if second_token else None
        
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
    
    def send_message_second_bot(self, message):
        """Send a message using the second Telegram bot."""
        if not self.second_token or not self.second_chat_id:
            logger.error("Second Telegram bot not configured")
            return False

        url = f"{self.second_base_url}/sendMessage"
        data = {
            "chat_id": self.second_chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_notification": False
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, data=data, timeout=30)
                response.raise_for_status()
                logger.info(f"Second bot message sent successfully")
                return True
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to send second bot message (attempt {attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    return False

        return False
    
    def send_blockchain_update(self, query_results):
        """Send blockchain query results via the second bot."""
        # Format the query results
        message = "🔄 *Blockchain Query Results*\n\n"
        logger.info(f"{query_results}")
        
        for kv in query_results:

            # # Adapt this formatting to match your actual data structure
            # name = result.get("name", "Unknown")
            # value = result.get("value", "N/A")
            message += f"• *{kv}*: `{query_results[kv]}`\n"
        
        return self.send_message_second_bot(message)

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
    
    def test_second_bot_connection(self):
        """Test the connection to the second Telegram bot API."""
        if not self.second_token:
            logger.warning("Second Telegram bot not configured")
            return False
            
        try:
            url = f"{self.second_base_url}/getMe"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('ok'):
                logger.info(f"Second Telegram bot connection successful: {data.get('result', {}).get('username')}")
                return True
            else:
                logger.error(f"Second Telegram bot connection failed: {data.get('description')}")
                return False
        except Exception as e:
            logger.error(f"Second Telegram bot connection test failed: {e}")
            return False
