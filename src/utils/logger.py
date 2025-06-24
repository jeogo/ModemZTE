import logging
from datetime import datetime
import os

class LogFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.last_poll_log = 0  # Timestamp of last poll log
        self.poll_log_interval = 300  # Only show poll logs every 5 minutes
        self.last_error_count = 0  # Track number of errors to show summary
        self.error_threshold = 5  # Show error summary after this many errors
    
    def filter(self, record):
        # Always show errors and critical messages
        if record.levelno >= logging.ERROR:
            return True
        
        # Filter poll-related messages
        is_poll_msg = any(x in record.msg.lower() for x in ['polling', 'checking messages', 'no new messages'])
        if is_poll_msg:
            current_time = datetime.now().timestamp()
            if current_time - self.last_poll_log > self.poll_log_interval:
                self.last_poll_log = current_time
                return True
            return False
            
        # Always show non-poll messages
        return True

def setup_logger(name):
    """Set up and return a logger with console output and filtered verbose messages"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # Console handler - show filtered messages in terminal
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        
        # Add filter to suppress frequent polling messages
        log_filter = LogFilter()
        console_handler.addFilter(log_filter)
        
        logger.addHandler(console_handler)

    return logger

def print_status(msg, msg_type="INFO"):
    """Print filtered status messages to terminal"""
    # Skip DEBUG and poll-related messages unless requested
    if msg_type == "DEBUG":
        if os.getenv('SMS_DEBUG') != 'true':
            return
        if any(x in msg.lower() for x in ['polling', 'checking messages', 'no new messages']):
            if os.getenv('SMS_POLL_DEBUG') != 'true':
                return
        
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    # Determine message type and color
    type_config = {
        "SUCCESS": {"icon": "[✓]", "prefix": "\033[92m"},  # Green
        "ERROR": {"icon": "[✗]", "prefix": "\033[91m"},    # Red
        "WARNING": {"icon": "[!]", "prefix": "\033[93m"},  # Yellow
        "INFO": {"icon": "[i]", "prefix": ""},
        "DEBUG": {"icon": "[D]", "prefix": "\033[90m"}     # Gray
    }.get(msg_type, {"icon": "[·]", "prefix": ""})
    
    formatted_msg = f"[{timestamp}] {type_config['icon']} {type_config['prefix']}{msg}\033[0m"
    
    # Handle Unicode encoding issues on Windows
    try:
        print(formatted_msg)
    except UnicodeEncodeError:
        # Fallback to safe ASCII encoding without colors
        safe_msg = f"[{timestamp}] {type_config['icon']} {msg}"
        print(safe_msg.encode('ascii', 'replace').decode('ascii'))
