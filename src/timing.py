import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("pipeline")


class timed_step:
    """Context manager that logs the wall-clock duration of a named step."""
    def __init__(self, label):
        self.label = label

    def __enter__(self):
        self.start = time.perf_counter()
        logger.info(f"▶ Starting: {self.label}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.perf_counter() - self.start
        status = "failed" if exc_type else "completed"
        logger.info(f"■ {status.capitalize()}: {self.label} ({elapsed:.3f}s)")
        return False  # don't suppress exceptions