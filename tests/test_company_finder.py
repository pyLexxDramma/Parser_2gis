import sys
import pathlib
import time
import logging

logger = logging.getLogger(__name__)

project_root = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from parser_2gis.chrome.remote import ChromeRemote
    from parser_2gis.chrome.options import ChromeOptions
    from parser_2gis.chrome.browser import ChromeBrowser
    from parser_2gis.finder.company_finder import CompanyFinder
    from parser_2gis.exceptions import ChromeException
    from parser_2gis.common import set_project_root  # Если используется

except ImportError as e:
    logger.error(f"Failed to import necessary modules. Error: {e}")
    sys.exit(1)



def test_company_finder_basic():
    """Basic test for CompanyFinder functionality."""
    logger.info("Starting basic CompanyFinder test...")

    try:
        # Используем headless=False, чтобы видеть, что происходит
        # disable_images=False, чтобы контент страницы загружался полностью
        chrome_options = ChromeOptions(headless=False, disable_images=False, start_maximized=True)

        # Паттерны для отслеживания ответов. Могут быть полезны для отладки поиска.
        response_patterns = ["*://*.2gis.ru/*", "*://*.2gis.ru/api/*"]

        logger.info("Initializing CompanyFinder...")
        # CompanyFinder использует ChromeRemote внутри себя, поэтому ChromeRemote будет запущен
        finder = CompanyFinder(chrome_options=chrome_options, response_patterns=response_patterns)

        # Тестируем поиск с тестовыми данными, которые мы добавили в CompanyFinder
        # Эти данные не реальные, а имитация
        test_company_name = "Пример"
        test_website = "example.com"

        logger.info(f"Searching for company: '{test_company_name}', website: '{test_website}'...")

        found_urls = finder.find_company_cards(company_name=test_company_name, website=test_website)

        logger.info(f"CompanyFinder returned {len(found_urls)} URLs.")

        for url in found_urls:
            logger.info(f"- Found URL: {url}")

        # Проверяем, что нашлись ожидаемые тестовые URL
        expected_url_part = "some_id_1"
        assert any(expected_url_part in url for url in
                   found_urls), f"Expected URL containing '{expected_url_part}' was not found."

        logger.info("CompanyFinder basic test completed successfully.")

    except ImportError:
        logger.error("Required modules not found. Please install dependencies.")
    except ChromeException as e:
        logger.error(f"Chrome interaction error during CompanyFinder test: {e}", exc_info=True)
    except AssertionError as e:
        logger.error(f"Test assertion failed: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during the CompanyFinder test: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        from parser_2gis.chrome.browser import ChromeBrowser
    except ImportError as e:
        logger.error(f"ChromeBrowser class not found. This test requires ChromeBrowser implementation. Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during ChromeBrowser setup: {e}", exc_info=True)
        sys.exit(1)

    test_company_finder_basic()
    logger.info("Basic CompanyFinder test finished.")
