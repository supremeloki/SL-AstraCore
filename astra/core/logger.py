import logging
import sys


def get_logger(name="astra", level=None):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    lvl = level or logging.INFO
    logger.setLevel(lvl)
    return logger
