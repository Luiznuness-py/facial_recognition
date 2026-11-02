"""Configuração de logging para a execução manual da aplicação."""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

def configure_logging(log_file: Path | None = None) -> None:
    """Configura o logger raiz para saída no terminal e, opcionalmente, em arquivo.

    Usa DEBUG e arquivos de até 2 MB, mantendo cinco backups. Se já houver handlers, retorna
    sem criar outros; não grava mensagens de domínio por conta própria.

    Args:
        log_file: Caminho opcional do arquivo rotativo; None usa somente o terminal.

    Returns:
        None: Ajusta o nível do logger e instala handlers se ainda não existirem.

    Raises:
        OSError: Quando o arquivo de log não pode ser aberto.
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