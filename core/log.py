import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

def configure_logging(log_file: Path | None = None) -> None:
    """
    Inicializa a configuração de log.

    Args:
        log_file (Path, None): Nome base para o arquivo de log. Padrão None.
    """

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if root_logger.handlers:
        return

    formatter = logging.Formatter(
        "[%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
    )

    terminal_handler = logging.StreamHandler(sys.stdout)
    terminal_handler.setLevel(logging.DEBUG)
    terminal_handler.setFormatter(formatter)
    root_logger.addHandler(terminal_handler)

    if log_file is not None:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)