from pathlib import Path
import logging
logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    path = Path(__file__).parent.parent.parent
    logger.log(5, f'fetched project root: {path}')
    return path
