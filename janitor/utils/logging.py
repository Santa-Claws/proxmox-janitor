import logging

from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_logging(level: str = "INFO") -> None:
    handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
    )
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        handlers=[handler],
    )
