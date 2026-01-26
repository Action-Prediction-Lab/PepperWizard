import csv
import time
import os

class CSVTelemetryLogger:
    def __init__(self, filename="motion_control.csv"):
        self.filename = filename
        self.file = None
        self.writer = None
        self.start_time = time.time()
        self.enabled = True

    def log(self, **kwargs):
        if not self.enabled:
            return
            
        if self.file is None:
            # Open file and write header
            self.file = open(self.filename, "w", newline='')
            self.writer = csv.writer(self.file)
            headers = ["time"] + list(kwargs.keys())
            self.writer.writerow(headers)
            
        # Write Data
        t = time.time() - self.start_time
        row = [f"{t:.4f}"] + [f"{v:.4f}" if isinstance(v, float) else v for v in kwargs.values()]
        self.writer.writerow(row)
        self.file.flush() # Ensure data is written

    def close(self):
        if self.file:
            self.file.close()
            self.file = None
