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

def setup_logging(log_file="logs/experiment_log.jsonl", verbose=False):
    """
    Configures the root logger to write to JSONL file and console.
    """
    root_logger = logging.getLogger()
    # If verbose, capture DEBUG+. If not, still capture INFO+ for FILE, but filter for CONSOLE.
    # We set root to DEBUG if verbose, INFO otherwise.
    root_logger.setLevel(logging.INFO if not verbose else logging.DEBUG)
    
    # clear existing handlers to avoid duplicates if re-initialized
    root_logger.handlers = []

    # 1. File Handler (JSONL)
    # Ensure directory exists if path has one
    if os.path.dirname(log_file):
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(JSONFormatter())
    # File always gets at least INFO, or DEBUG if verbose
    file_handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    root_logger.addHandler(file_handler)

    # 2. Console Handler (Human Readable)
    console_handler = logging.StreamHandler(sys.stdout)
    # Simple format for console: [TIME] [LEVEL] [COMPONENT] Message {Data}
    console_format = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
    )
    console_handler.setFormatter(console_format)
    
    # User Request: "if the flag is not present the logs are not visable on the console"
    # So if verbose=False, we only show WARNING/ERROR. If verbose=True, we show everything.
    console_handler.setLevel(logging.WARNING if not verbose else logging.DEBUG)
    
    root_logger.addHandler(console_handler)

    logging.info("LoggingInitialized", {"log_file": log_file})

def get_logger(name):
    """
    Returns a logger instance with the given name.
    """
    return logging.getLogger(name)
