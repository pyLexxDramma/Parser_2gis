from __future__ import annotations

from typing import Optional, List

from ..chrome.options import ChromeOptions
from ..chrome.remote import ChromeRemote
from ..exceptions import ChromeRuntimeException, ChromeUserAbortException
from ..finder.company_finder import CompanyFinder
from ..logger import logger
from ..parser import get_parser
from ..writer import get_writer
from .runner import AbstractRunner


class CLIRunner(AbstractRunner):
    def __init__(
            self,
            urls: Optional[list[str]],
            output_path: Optional[str],
            format: Optional[str],
            config: 'Configuration',
            company_name: Optional[str] = None,
            website: Optional[str] = None
    ) -> None:
        super().__init__(urls or [], output_path, format, config)
        self._company_name = company_name
        self._website = website

        if not self._urls and not (self._company_name or self._website):
            raise ValueError("Either URLs or company name/website must be provided for CLI execution.")

        if (self._company_name or self._website) and (not self._output_path or not self._format):
            raise ValueError("Output path and format are required when searching by company name/website.")

        self._target_urls: List[str] = []

    def _find_target_urls(self) -> None:
        if self._company_name or self._website:
            try:
                finder_response_patterns = ['*.2gis.ru/api/*']
                finder = CompanyFinder(
                    chrome_options=self._config.chrome,
                    response_patterns=finder_response_patterns
                )

                self._target_urls = finder.find_company_cards(
                    company_name=self._company_name or "",
                    website=self._website
                )

                if not self._target_urls:
                    logger.warning("No company cards found matching the search criteria.")

            except Exception as e:
                logger.error(f"Error during company search: {e}", exc_info=True)
                self._target_urls = []
        else:
            self._target_urls = self._urls

    def start(self):
        if not self._target_urls:
            self._find_target_urls()

        if not self._target_urls:
            logger.warning("No URLs available for parsing. Exiting.")
            return

        logger.info(f"Starting parsing for {len(self._target_urls)} URLs.")

        try:
            if self._output_path and self._format:
                writer = get_writer(self._output_path, self._format, self._config.writer)
            else:
                writer = None

            with writer:
                for url in self._target_urls:
                    try:
                        with get_parser(url,
                                        chrome_options=self._config.chrome,
                                        parser_options=self._config.parser) as parser:
                            parser.parse(writer)

                    except pychrome.RuntimeException as e:
                        logger.error(f"Chrome Runtime Error during parsing of {url}: {e}", exc_info=True)
                        continue
                    except ChromeException as e:
                        logger.error(f"Chrome interaction error during parsing of {url}: {e}", exc_info=True)
                        continue
                    except Exception as parse_error:
                        logger.error(f"Error parsing {url}: {parse_error}", exc_info=True)
                        continue
                    finally:
                        logger.info(f'Finished parsing URL: {url}')
        except (KeyboardInterrupt, ChromeUserAbortException):
            logger.error('Parser operation interrupted by user.')
        except Exception as e:
            if isinstance(e, ChromeRuntimeException) and str(e) == 'Tab has been stopped':
                logger.error('Browser tab was closed unexpectedly during initialization or parsing.')
            else:
                logger.error('An unexpected error occurred during parser operation.', exc_info=True)
        finally:
            logger.info('Parsing process finished.')

    def stop(self):
        pass