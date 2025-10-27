from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, List, Optional

from parser_2gis.chrome.remote import ChromeRemote
from parser_2gis.chrome.options import ChromeOptions
from parser_2gis.logger import logger
from parser_2gis.exceptions import ChromeException

if TYPE_CHECKING:
    pass


class CompanyFinder:
    def __init__(self, chrome_options: ChromeOptions, response_patterns: List[str]):
        self._chrome_options = chrome_options
        self._response_patterns = response_patterns
        self._chrome_remote: Optional[ChromeRemote] = None
        self._base_url = "https://2gis.ru/"

    def _init_chrome_remote(self) -> None:
        if self._chrome_remote is None:
            self._chrome_remote = ChromeRemote(
                chrome_options=self._chrome_options,
                response_patterns=self._response_patterns
            )
            self._chrome_remote.start()

    def _find_urls(self, company_name: str, website: str) -> List[str]:
        if self._chrome_remote is None:
            self._init_chrome_remote()

        found_urls: List[str] = []

        try:
            logger.info(f"Navigating to 2GIS base URL: {self._base_url}")
            self._chrome_remote.navigate(self._base_url)

            search_input_selector = 'input[data-testid="search-input"], [aria-label="Поиск по названию, адресу, организации"]'
            if not self._chrome_remote.execute_script(
                    f"return document.querySelector('{search_input_selector}') !== null;"):
                raise ChromeException(
                    f"Main search input element not found with selector '{search_input_selector}'. Cannot proceed with search.")

            js_set_company_name = f"document.querySelector('{search_input_selector}').value = arguments[0];"
            self._chrome_remote.execute_script(js_set_company_name, company_name)
            logger.debug(f"Entered company name '{company_name}' into search field.")

            website_input_selector = 'input[data-testid="search-input-website"], [aria-label="Поиск по сайту"]'

            if self._chrome_remote.execute_script(
                    f"return document.querySelector('{website_input_selector}') !== null;"):
                logger.debug(f"Entering website '{website}' into website field.")
                js_set_website = f"document.querySelector('{website_input_selector}').value = arguments[0];"
                self._chrome_remote.execute_script(js_set_website, website)
            else:
                logger.debug("Website search field not found or not visible, proceeding without it.")

            logger.debug("Submitting search query.")

            search_button_selector = 'button[data-testid="search-button"], .button-search, [aria-label="Найти"]'

            button_found = False
            if self._chrome_remote.wait_for_selector(search_button_selector, timeout=5):
                js_click_button = f"""
                 var button = document.querySelector('{search_button_selector}');
                 if (button) {{
                     button.style.display = 'block'; 
                     button.style.visibility = 'visible';
                     button.scrollIntoView({{ block: "center", behavior: "instant" }});
                     button.click();
                     return true;
                 }}
                 return false;
                 """
                if self._chrome_remote.execute_script(js_click_button):
                    button_found = True
                    logger.debug("Clicked search button.")

            if not button_found:
                logger.debug("Search button not found or not clickable, simulating 'Enter' key press in search input.")
                js_enter_search = f"document.querySelector('{search_input_selector}').focus(); document.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter'}}));"
                self._chrome_remote.execute_script(js_enter_search)

            logger.info("Waiting for search results to load...")

            result_container_selector = 'div[data-testid="search-results-list"], .search-results-list, [data-qa="results-list"]'

            if not self._chrome_remote.wait_for_selector(result_container_selector, timeout=20):
                logger.warning(
                    f"Timeout waiting for search results container '{result_container_selector}'. Search might have yielded no results or DOM changed.")
                return []

            logger.info("Search results container found.")

            logger.info("Fetching search results DOM.")
            dom_tree = self._chrome_remote.get_document(full=True)

            company_card_elements = dom_tree.search(
                lambda node: node.name == 'div' and any(
                    class_name in node.attributes.get('class', '').split()
                    for class_name in ['company-card', 'search-result-card', 'item-card']
                )
            )

            if not company_card_elements:
                logger.warning(
                    "No elements identified as company cards found. DOM structure might have changed or search yielded no results.")

            found_matching_urls = []
            for card_element in company_card_elements:
                firm_link_node = card_element.search_first(
                    lambda node: node.name == 'a' and any(
                        class_name in node.attributes.get('class', '').split()
                        for class_name in ['firm-card__link', 'result-link', 'company-link']
                    )
                )

                url = None
                if firm_link_node and firm_link_node.attributes.get('href'):
                    url = firm_link_node.attributes['href']
                    if not url.startswith('http'):
                        url = self._base_url.rstrip('/') + url

                    company_name_node = card_element.search_first(
                        lambda node: node.name in ('span', 'div', 'a', 'h3', 'h4') and any(
                            class_name in node.attributes.get('class', '').split()
                            for class_name in ['company-name', 'org-name', 'title']
                        )
                    )
                    current_company_name = company_name_node.text.strip() if company_name_node else ''

                    website_node = card_element.search_first(
                        lambda node: node.name == 'a' and any(
                            class_name in node.attributes.get('class', '').split()
                            for class_name in ['company-website', 'website-link', 'link-site']
                        )
                    )
                    current_website = website_node.attributes.get('href', '') if website_node else ''

                    name_match = company_name.lower() in current_company_name.lower()
                    website_match = True
                    if website:
                        try:
                            current_domain_match = re.search(r'(?:https?:\/\/)?(?:www\.)?([^/]+)', current_website)
                            search_domain_match = re.search(r'(?:https?:\/\/)?(?:www\.)?([^/]+)', website)

                            if current_domain_match and search_domain_match:
                                website_match = current_domain_match.group(1).lower() == search_domain_match.group(
                                    1).lower()
                            else:
                                website_match = website.lower() in current_website.lower()
                        except Exception as e:
                            logger.warning(f"Error comparing websites '{current_website}' and '{website}': {e}",
                                           exc_info=True)
                            website_match = True

                    if name_match and website_match and url:
                        logger.debug(f"Found matching company: '{current_company_name}' ({current_website}) at {url}")
                        found_matching_urls.append(url)

            if not found_matching_urls:
                logger.warning(
                    f"No exact matches found for '{company_name}' (website: '{website}'). Found {len(company_card_elements)} potential company cards.")
            else:
                logger.info(f"Successfully found {len(found_matching_urls)} URLs matching the criteria.")

            return found_matching_urls

        except ChromeException as e:
            logger.error(f"Chrome interaction error during search: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred during the search process: {e}", exc_info=True)
            return []

    def find_company_cards(self, company_name: str, website: Optional[str] = None) -> List[str]:
        if not company_name:
            logger.error("Company name is required for searching.")
            return []

        try:
            urls = self._find_urls(company_name, website or "")
            return urls
        finally:
            if self._chrome_remote:
                logger.debug("Stopping ChromeRemote for CompanyFinder.")
                self._chrome_remote.stop()
                self._chrome_remote = None
                logger.debug("ChromeRemote stopped.")