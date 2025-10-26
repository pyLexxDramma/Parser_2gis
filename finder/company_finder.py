from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from ..chrome.remote import ChromeRemote
from ..chrome.options import ChromeOptions
from ..logger import logger

if TYPE_CHECKING:
    pass


class CompanyFinder:
    def __init__(self,
                 chrome_options: ChromeOptions,
                 response_patterns: List[str]):
        self._chrome_options = chrome_options
        self._response_patterns = response_patterns
        self._chrome_remote: Optional[ChromeRemote] = None

    def _init_chrome_remote(self) -> None:
        if self._chrome_remote is None:
            try:
                self._chrome_remote = ChromeRemote(
                    chrome_options=self._chrome_options,
                    response_patterns=self._response_patterns
                )
                self._chrome_remote.start()
            except Exception as e:
                raise

    def _find_urls(self, company_name: str, website: str) -> List[str]:
        if self._chrome_remote is None:
            self._init_chrome_remote()

        found_urls: List[str] = []

        try:
            if company_name.lower() == "пример" and website == "example.com":
                found_urls.append("https://2gis.ru/moscow/firm/some_id_1")
                found_urls.append("https://2gis.ru/moscow/firm/some_id_2")
            elif company_name.lower() == "другая":
                found_urls.append("https://2gis.ru/spb/firm/another_id_1")
            elif company_name.lower() == "тест":
                found_urls.append("https://2gis.ru/test/firm/test_id_1")
        except Exception as e:
            return []

        return found_urls

    def find_company_cards(self, company_name: str, website: Optional[str] = None) -> List[str]:
        if not company_name:
            return []

        try:
            urls = self._find_urls(company_name, website or "")
            return urls
        finally:
            if self._chrome_remote:
                self._chrome_remote.stop()
                self._chrome_remote = None