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

def setup_logging(session_id=None, log_file=None, verbose=False):
    """
    Configures the root logger to write to JSONL file and console.
    
    Args:
        session_id (str): Optional ID to include in the filename (e.g. 'P01'). 
                          If None, a timestamp is used.
        log_file (str): Specific path to log file. If provided, overrides dynamic naming.
        verbose (bool): If True, enable DEBUG level and show logs on console.
    """
    root_logger = logging.getLogger()
    # If verbose, capture DEBUG+. If not, still capture INFO+ for FILE, but filter for CONSOLE.
    # We set root to DEBUG if verbose, INFO otherwise.
    root_logger.setLevel(logging.INFO if not verbose else logging.DEBUG)
    
    # clear existing handlers to avoid duplicates if re-initialized
    root_logger.handlers = []

    # Determine log filename
    if log_file is None:
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        if session_id:
            filename = f"session_{session_id}.jsonl"
        else:
            # Format: session_YYYY-MM-DD_HH-MM-SS.jsonl
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"session_{timestamp}.jsonl"
            
        log_file = os.path.join(log_dir, filename)
    else:
        # Operator provided specific path (e.g. for testing)
        if os.path.dirname(log_file):
            os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # 1. File Handler (JSONL)
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
    
    # if verbose=False, show WARNING/ERROR. If verbose=True, show everything
    console_handler.setLevel(logging.WARNING if not verbose else logging.DEBUG)
    
    root_logger.addHandler(console_handler)

    # 3. Silence Noisy Third-Party Libraries
    # These libraries are very chatty even at INFO level, especially during model loading
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("transformers").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

    logging.info("LoggingInitialized", {"log_file": log_file})

def get_logger(name):
    """
    Returns a logger instance with the given name.
    """
    return logging.getLogger(name)
