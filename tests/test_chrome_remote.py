import sys
import pathlib
import time
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

project_root = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from parser_2gis.chrome.remote import ChromeRemote
    from parser_2gis.chrome.options import ChromeOptions
    from parser_2gis.chrome.browser import ChromeBrowser
    from parser_2gis.exceptions import ChromeException

except ImportError as e:
    logger.error(f"Failed to import necessary modules. Ensure your project structure is correct and dependencies are installed. Error: {e}")
    sys.exit(1)


def test_chrome_remote_basic():
    """Basic test for ChromeRemote functionality."""
    logger.info("Starting basic ChromeRemote test...")

    try:
        # Используем headless=False, чтобы видеть, что происходит
        # disable_images=False, чтобы контент страницы загружался полностью
        chrome_options = ChromeOptions(headless=False, disable_images=False, start_maximized=True)

        # Пример паттерна для перехвата ответов (можно использовать более специфичные)
        response_patterns = ["*://*.google.com/*"]

        logger.info("Initializing ChromeRemote with options...")
        # Используем контекстный менеджер for __enter__/__exit__
        with ChromeRemote(chrome_options=chrome_options, response_patterns=response_patterns) as remote:
            logger.info("ChromeRemote initialized and started.")

            # Проверка навигации
            target_url = "https://www.google.com"
            logger.info(f"Navigating to {target_url}...")
            remote.navigate(target_url)
            logger.info("Navigation initiated.")

            # Даем время для загрузки страницы
            time.sleep(5)

            # Проверка выполнения JS
            logger.info("Executing JavaScript to get page title...")
            page_title = remote.execute_script("return document.title;")
            logger.info(f"Page title retrieved: '{page_title}'")
            assert "Google" in page_title, "Page title does not contain 'Google'"

            # Проверка получения DOM
            logger.info("Getting DOM document...")
            dom_node = remote.get_document(full=True)
            logger.info(f"DOM document obtained. Root node name: '{dom_node.name}'")
            assert dom_node.name == 'html', "DOM root node is not 'html'"

            # Проверка ожидания ответа (если какой-то запрос соответствует паттерну)
            logger.info("Waiting for specific response...")
            response = remote.wait_response("*://*.google.com/images/branding/*")  # Пример ожидания конкретного ответа
            if response:
                logger.info(
                    f"Specific response received: URL='{response.get('url')}', Status='{response.get('status')}'")
            else:
                logger.warning("Specific response not received within timeout.")

            # Проверка get_response_body
            if response and 'body' not in response:  # Если получили ответ, но тело еще не загружено
                logger.info("Fetching response body...")
                body = remote.get_response_body(response)
                logger.info(f"Response body length: {len(body)} characters.")

            logger.info("ChromeRemote operations completed.")

        logger.info("ChromeRemote stopped successfully via context manager.")

    except ImportError:
        logger.error("Required modules not found. Please install dependencies (pychrome, requests, psutil).")
    except ChromeException as e:
        logger.error(f"Chrome interaction error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred during the test: {e}", exc_info=True)
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

    test_chrome_remote_basic()
    logger.info("Basic ChromeRemote test finished.")