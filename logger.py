import logging
import sys

from constants import LOG_LEVEL


class CustomFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = ("%(asctime)s - %(name)s - %(levelname)s - %(message)s "
              "(%(filename)s:%(lineno)d)")

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def run_logger(module_name):
    logger = logging.getLogger(module_name)
    logger.setLevel(getattr(logging, LOG_LEVEL))
    handler = logging.StreamHandler(stream=sys.stdout)
    logger.setLevel(getattr(logging, LOG_LEVEL))
    handler.setFormatter(CustomFormatter())
    logger.addHandler(handler)

    return logger


if __name__ == '__main__':
    run_logger(__name__)
