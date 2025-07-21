class BaseNotifier:
    """Base class for notification services."""

    def send_message(self, message, urgent=False):
        """Send a message through the notification service."""
        raise NotImplementedError("Subclasses must implement send_message")

    def test_connection(self):
        """Test the connection to the notification service."""
        raise NotImplementedError("Subclasses must implement test_connection")
