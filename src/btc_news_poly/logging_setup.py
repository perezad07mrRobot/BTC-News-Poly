import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    root = logging.getLogger()
    if root.handlers:
        return logging.getLogger("btc_news_poly")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level.upper())
    return logging.getLogger("btc_news_poly")
