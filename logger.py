import logging
from datetime import datetime
import os

def setup_logger(name):
    """Set up and return a logger with minimal output"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # Console handler - only show INFO and above
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler for errors only
        error_handler = logging.FileHandler('error.log')
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        error_handler.setFormatter(error_formatter)
        logger.addHandler(error_handler)

    return logger

def write_to_log(msg, log_file='received.log'):
    """Write message to log file silently"""
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{msg}\n")
    except Exception:
        pass

def print_status(msg, msg_type="INFO"):
    """Print only important status messages"""
    if msg_type in ["ERROR", "SUCCESS"]:
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_msg = f"[{timestamp}] {msg}"
        print(formatted_msg)
    
    # Always log errors to error.log
    if msg_type == "ERROR":
        write_to_log(msg, 'error.log')
