import logging
import json
import datetime
import sys
import os

class JSONFormatter(logging.Formatter):
    """
    Formatter to output logs in JSON Lines format.
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "event": record.msg,  # treating the main message as the 'event' name
            "data": record.args if isinstance(record.args, dict) else {}
        }
        # add exception info
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_record)

def setup_logging(log_file="experiment_log.jsonl", verbose=False):
    """
    Configures the root logger to write to JSONL file and console.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO if not verbose else logging.DEBUG)
    
    # clear existing handlers to avoid duplicates if re-initialized
    root_logger.handlers = []

    # 1. File Handler (JSONL)
    # Ensure directory exists if path has one
    if os.path.dirname(log_file):
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)

    # 2. Console Handler (Human Readable)
    console_handler = logging.StreamHandler(sys.stdout)
    # Simple format for console: [TIME] [LEVEL] [COMPONENT] Message {Data}
    console_format = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
    )
    console_handler.setFormatter(console_format)
    # Only show INFO+ on console unless verbose is strictly requested
    # But root level controls what gets passed.
    console_handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    root_logger.addHandler(console_handler)

    logging.info("LoggingInitialized", {"log_file": log_file})

def get_logger(name):
    """
    Returns a logger instance with the given name.
    """
    return logging.getLogger(name)
