from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Any

from ..logger import setup_cli_logger, logger
from ..runner import CLIRunner

if TYPE_CHECKING:
    from ..config import Configuration

def cli_app(
    urls: Optional[list[str]],
    output_path: Optional[str],
    format: Optional[str],
    config: 'Configuration',
    company_name: Optional[str] = None,
    website: Optional[str] = None
) -> None:
    setup_cli_logger(config.log)
    logger.info("CLI application started.")

    if not urls and not (company_name or website):
        logger.error("Either URLs or company name/website must be provided for CLI execution.")
        return

    runner = CLIRunner(
        urls=urls,
        output_path=output_path,
        format=format,
        config=config,
        company_name=company_name,
        website=website
    )
    runner.start()