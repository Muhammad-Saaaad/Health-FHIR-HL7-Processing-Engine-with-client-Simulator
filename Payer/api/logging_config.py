import logging
from logging.handlers import RotatingFileHandler
import os

def get_logger(name: str, logfile: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

    if logfile:
        os.makedirs(os.path.dirname(logfile), exist_ok=True)
        handler = RotatingFileHandler(logfile, maxBytes=2000000, backupCount=3)
    else:
        handler = logging.StreamHandler()

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
