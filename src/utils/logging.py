import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(log_dir, log_name='blockchain_monitor.log', max_size_mb=10, backup_count=5):
    """Set up logging with rotation to prevent excessive log growth."""
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, log_name)

    # Configure rotating file handler
    handler = RotatingFileHandler(
        log_file, 
        maxBytes=max_size_mb*1024*1024,  # Convert MB to bytes
        backupCount=backup_count
    )

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            handler,
            logging.StreamHandler()  # Also log to console
        ]
    )

    return logging.getLogger('blockchain_monitor')
