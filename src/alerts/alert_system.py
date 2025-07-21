import logging
from datetime import datetime, timedelta

logger = logging.getLogger('blockchain_monitor.alerts')

class AlertSystem:
    def __init__(self, config, notifiers):
        self.config = config
        self.notifiers = notifiers
        self.alert_history = {}  # To track alert cooldowns

    def process_alert(self, query_id, current_value, previous_value):
        """Process alerts for a query based on the current and previous values."""
        alerts = self.get_alerts_for_query(query_id)
        if not alerts:
            return

        for alert in alerts:
            alert_id = alert.get('id', f"{query_id}_alert")

            # Check if alert is in cooldown
            if not self.can_trigger_alert(alert_id, alert):
                continue

            # Process different alert types
            alert_type = alert.get('type', 'threshold')
            triggered = False

            if alert_type == 'threshold':
                triggered = self.check_change_alert(alert, current_value, previous_value)
            elif alert_type == 'percent_change':
                triggered = self.check_percent_change_alert(alert, current_value, previous_value)
            elif alert_type == 'ratio':
                triggered = self.check_ratio_alert(alert, current_value, previous_value)

            if triggered:
                self.trigger_alert(alert_id, alert, query_id, current_value, previous_value)

    def get_alerts_for_query(self, query_id):
        """Get all alerts configured for a specific query."""
        alerts = []

        # Check for alerts in the main config
        for alert in self.config.get('alerts', []):
            if alert.get('query_id') == query_id:
                alerts.append(alert)

        return alerts

    def can_trigger_alert(self, alert_id, alert):
        """Check if an alert can be triggered based on cooldown settings."""
        cooldown_minutes = alert.get('cooldown_minutes', 60)

        if alert_id in self.alert_history:
            last_triggered = self.alert_history[alert_id]
            cooldown_time = last_triggered + timedelta(minutes=cooldown_minutes)

            if datetime.now() < cooldown_time:
                logger.debug(f"Alert {alert_id} is in cooldown until {cooldown_time}")
                return False

        return True

    def check_change_alert(self, alert, current_value, previous_value):
        """Check if a change alert should be triggered."""
        try:
            threshold = float(alert.get('threshold', 0))

            # Convert current_value to float if it's a string
            if isinstance(current_value, str):
                current_value = float(current_value)
            if isinstance(previous_value, str):
                previous_value = float(previous_value)
            return abs(current_value - previous_value) > threshold 

        except (ValueError, TypeError) as e:
            logger.error(f"Error checking change alert: {e}")
            return False

    def check_threshold_alert(self, alert, current_value):
        """Check if a threshold alert should be triggered."""
        try:
            threshold = float(alert.get('threshold', 0))
            operator = alert.get('operator', '>')

            # Convert current_value to float if it's a string
            if isinstance(current_value, str):
                current_value = float(current_value)

            if operator == '>':
                return current_value > threshold
            elif operator == '<':
                return current_value < threshold
            elif operator == '>=':
                return current_value >= threshold
            elif operator == '<=':
                return current_value <= threshold
            elif operator == '==':
                return current_value == threshold
            elif operator == '!=':
                return current_value != threshold
            else:
                logger.error(f"Unknown operator {operator} for threshold alert")
                return False
        except (ValueError, TypeError) as e:
            logger.error(f"Error checking threshold alert: {e}")
            return False

    def check_percent_change_alert(self, alert, current_value, previous_value):
        """Check if a percent change alert should be triggered."""
        try:
            threshold = float(alert.get('threshold', 5.0))  # Default 5% change

            # Convert values to float if they're strings
            if isinstance(current_value, str):
                current_value = float(current_value)
            if isinstance(previous_value, str):
                previous_value = float(previous_value)

            if previous_value == 0:
                # Avoid division by zero
                return current_value != 0

            percent_change = abs((current_value - previous_value) / previous_value * 100)
            return percent_change >= threshold
        except (ValueError, TypeError) as e:
            logger.error(f"Error checking percent change alert: {e}")
            return False

    def check_ratio_alert(self, alert, current_value, previous_value):
        """Check if a ratio alert should be triggered."""
        try:
            threshold = float(alert.get('threshold', 1.0))

            # Convert values to float if they're strings
            if isinstance(current_value, str):
                current_value = float(current_value)
            if isinstance(previous_value, str):
                previous_value = float(previous_value)

            if previous_value == 0:
                # Avoid division by zero
                return False

            ratio = current_value / previous_value
            operator = alert.get('operator', '>')

            if operator == '>':
                return ratio > threshold
            elif operator == '<':
                return ratio < threshold
            elif operator == '>=':
                return ratio >= threshold
            elif operator == '<=':
                return ratio <= threshold
            else:
                logger.error(f"Unknown operator {operator} for ratio alert")
                return False
        except (ValueError, TypeError) as e:
            logger.error(f"Error checking ratio alert: {e}")
            return False

    def trigger_alert(self, alert_id, alert, query_id, current_value, previous_value):
        """Trigger an alert by sending notifications."""
        # Update alert history
        self.alert_history[alert_id] = datetime.now()

        # Get alert details
        name = alert.get('name', f"Alert for {query_id}")
        description = alert.get('description', '')
        urgency = alert.get('urgency', 'normal')

        # Format message
        message = f"*{name}*\n"
        if description:
            message += f"{description}\n\n"

        message += f"Query: `{query_id}`\n"
        message += f"Previous value: `{previous_value}`\n"
        message += f"Current value: `{current_value}`\n"
        message += f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"

        # Send notifications
        urgent = urgency.lower() == 'high'
        for notifier_name, notifier in self.notifiers.items():
            try:
                notifier.send_message(message, urgent=urgent)
            except Exception as e:
                logger.error(f"Failed to send {notifier_name} notification: {e}")
