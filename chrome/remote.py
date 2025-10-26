from __future__ import annotations

import base64
import queue
import re
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, List

import pychrome
import requests
from requests.exceptions import RequestException
from websocket import WebSocketException

from ..common import wait_until_finished, floor_to_hundreds
from .browser import ChromeBrowser
from .dom import DOMNode
from .exceptions import ChromeException, ChromeRuntimeException
from .options import ChromeOptions
from .patches import patch_all

if TYPE_CHECKING:
    Request = Dict[str, Any]
    Response = Dict[str, Any]

patch_all()


class ChromeRemote:

    def __init__(self, chrome_options: ChromeOptions, response_patterns: list[str]) -> None:
        self._chrome_options: ChromeOptions = chrome_options
        self._chrome_browser: Optional[ChromeBrowser] = None
        self._dev_url: Optional[str] = None
        self._chrome_interface: Optional[pychrome.Browser] = None
        self._chrome_tab: Optional[pychrome.Tab] = None
        self._response_patterns: list[str] = response_patterns
        self._response_queues: dict[str, queue.Queue[Response]] = {x: queue.Queue() for x in response_patterns}
        self._requests: dict[str, Request] = {}
        self._requests_lock = threading.Lock()
        self._ping_thread: Optional[threading.Thread] = None
        self._tab_detached = False

    @wait_until_finished(timeout=60)
    def _connect_interface(self) -> bool:
        if not self._dev_url:
            logger.error("Chrome DevTools URL is not set. Cannot connect.")
            return False

        try:
            self._chrome_interface = pychrome.Browser(url=self._dev_url)
            self._chrome_tab = self._create_tab()
            self._chrome_tab.start()
            return True
        except (RequestException, WebSocketException, pychrome.CallMethodException) as e:
            logger.error(f"Failed to connect to Chrome interface: {e}", exc_info=True)
            return False

    def start(self) -> None:
        if self._chrome_browser is not None:
            logger.warning("Chrome browser is already started.")
            return

        logger.debug("Starting Chrome browser.")
        # Open browser
        self._chrome_browser = ChromeBrowser(self._chrome_options)
        self._dev_url = f'http://127.0.0.1:{self._chrome_browser.remote_port}'
        logger.debug(f"Chrome DevTools URL: {self._dev_url}")

        # Connect browser with CDP
        if not self._connect_interface():
            logger.error("Failed to establish CDP connection. Stopping browser.")
            if self._chrome_browser:
                self._chrome_browser.close()
                self._chrome_browser = None
            return

        self._setup_tab()
        self._init_tab_monitor()
        logger.debug("Chrome tab setup complete.")

    def _create_tab(self) -> pychrome.Tab:
        if not self._dev_url:
            raise ChromeException("Chrome DevTools URL not set.")
        try:
            resp = requests.put('%s/json/new' % (self._dev_url), json=True)
            resp.raise_for_status()
            return pychrome.Tab(**resp.json())
        except (RequestException, pychrome.CallMethodException) as e:
            logger.error(f"Failed to create new tab: {e}", exc_info=True)
            raise ChromeException(f"Could not create new tab: {e}") from e

    def _close_tab(self, tab: pychrome.Tab) -> None:
        if tab.status == pychrome.Tab.status_started:
            tab.stop()

        if not self._dev_url:
            logger.warning("Chrome DevTools URL not set. Cannot close tab.")
            return

        try:
            requests.put('%s/json/close/%s' % (self._dev_url, tab.id))
        except RequestException as e:
            logger.warning(f"Failed to close tab {tab.id}: {e}", exc_info=True)

    def _setup_tab(self) -> None:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        try:
            original_useragent = self.execute_script('navigator.userAgent')
            fixed_useragent = original_useragent.replace(' HeadlessChrome/', ' Chrome/')
            self._chrome_tab.Network.setUserAgentOverride(userAgent=fixed_useragent)
            logger.debug(f"User agent overridden to: {fixed_useragent}")
        except Exception as e:
            logger.warning(f"Could not override user agent: {e}", exc_info=True)

        self.add_start_script(r'''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        ''')
        logger.debug("WebDriver trace hiding script added.")

    def _enable_domains(self) -> None:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        try:
            self._chrome_tab.Network.enable()
            self._chrome_tab.DOM.enable()
            self._chrome_tab.Page.enable()
            self._chrome_tab.Runtime.enable()
            self._chrome_tab.Log.enable()
            logger.debug("CDP domains enabled: Network, DOM, Page, Runtime, Log.")
        except pychrome.CallMethodException as e:
            logger.error(f"Failed to enable CDP domains: {e}", exc_info=True)

    def _init_tab_monitor(self) -> None:
        if self._chrome_tab is None:
            raise ChromeException("Chrome tab is not initialized for monitoring.")

        tab_detached = False

        def monitor_tab() -> None:
            while not self._chrome_tab._stopped.is_set():
                try:
                    if not self._dev_url:
                        logger.error("DevTools URL is not set. Cannot monitor tab.")
                        break

                    ret = requests.get(f'{self._dev_url}/json', timeout=1)
                    ret.raise_for_status()

                    if not any(x['id'] == self._chrome_tab.id for x in ret.json()):
                        nonlocal tab_detached
                        tab_detached = True
                        logger.warning(f"Tab {self._chrome_tab.id} detached from browser.")
                        self._chrome_tab._stopped.set()
                        break

                    self._chrome_tab._stopped.wait(0.5)
                except ConnectionError:
                    logger.warning("Connection error while monitoring tab. Assuming tab is lost.")
                    tab_detached = True
                    self._chrome_tab._stopped.set()
                    break
                except requests.Timeout:
                    logger.warning("Timeout while monitoring tab. Assuming tab is unresponsive.")
                    tab_detached = True
                    self._chrome_tab._stopped.set()
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in tab monitor: {e}", exc_info=True)
                    tab_detached = True
                    self._chrome_tab._stopped.set()
                    break

        self._ping_thread = threading.Thread(target=monitor_tab, daemon=True)
        self._ping_thread.start()
        logger.debug("Tab monitor thread started.")

        def get_send_with_reraise() -> Callable[..., Any]:
            original_send = self._chrome_tab._send

            def wrapped_send(*args, **kwargs) -> Any:
                try:
                    return original_send(*args, **kwargs)
                except pychrome.UserAbortException:
                    if tab_detached:
                        raise pychrome.RuntimeException('Tab has been stopped')
                    else:
                        raise pychrome.UserAbortException('Operation aborted by user or tab issue.') from None
                except Exception as e:
                    logger.error(f"Error during CDP call: {e}", exc_info=True)
                    if tab_detached:
                        raise pychrome.RuntimeException('Tab has been stopped') from e
                    else:
                        raise

            return wrapped_send

        self._chrome_tab._send = get_send_with_reraise()

    def navigate(self, url: str, referer: str = '', timeout: int = 60) -> None:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        logger.debug(f"Navigating to {url} (Referer: {referer}) with timeout {timeout}s.")
        try:
            ret = self._chrome_tab.Page.navigate(url=url, _timeout=timeout, referrer=referer)
            error_message = ret.get('errorText', None)
            if error_message:
                logger.error(f"Navigation to {url} failed: {error_message}")
                raise ChromeException(f"Navigation failed: {error_message}")
            logger.debug(f"Successfully navigated to {url}.")
        except pychrome.RuntimeException as e:
            logger.error(f"Tab stopped during navigation to {url}: {e}")
            raise ChromeException(f"Tab stopped during navigation: {e}") from e
        except pychrome.CallMethodException as e:
            logger.error(f"CDP Call Method error during navigation to {url}: {e}", exc_info=True)
            raise ChromeException(f"CDP Call Method error during navigation: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred during navigation to {url}: {e}", exc_info=True)
            raise ChromeException(f"Unexpected error during navigation: {e}") from e

    @wait_until_finished(timeout=30, throw_exception=False)
    def wait_response(self, response_pattern: str) -> Response | None:
        if self._chrome_tab is None:
            logger.warning("Chrome tab is not initialized. Cannot wait for response.")
            return None

        if self._chrome_tab._stopped.is_set():
            logger.warning("Chrome tab is stopped. Cannot wait for response.")
            return None

        try:
            return self._response_queues[response_pattern].get(block=False)
        except queue.Empty:
            return None
        except KeyError:
            logger.error(f"Invalid response pattern '{response_pattern}' provided.")
            return None

    def clear_requests(self) -> None:
        with self._requests_lock:
            self._requests.clear()
            for q in self._response_queues.values():
                while not q.empty():
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        pass
        logger.debug("Cleared collected requests and response queues.")

    @wait_until_finished(timeout=15, throw_exception=False)
    def get_response_body(self, response: Response) -> str:
        if not self._chrome_tab:
            logger.warning("Chrome tab not initialized. Cannot get response body.")
            return ''

        try:
            request_id = response.get('requestId')
            if not request_id:
                logger.warning("Response object does not contain 'requestId'. Cannot get response body.")
                return ''

            response_data = self._chrome_tab.call_method('Network.getResponseBody',
                                                         requestId=request_id)
            body = response_data.get('body', '')
            base64_encoded = response_data.get('base64Encoded', False)

            if base64_encoded and body:
                try:
                    body = base64.b64decode(body).decode('utf-8', errors='ignore')
                except Exception as e:
                    logger.error(f"Failed to decode base64 response body for {request_id}: {e}", exc_info=True)
                    body = ''

            response['body'] = body
            return body
        except pychrome.CallMethodException as e:
            logger.warning(
                f"Could not get response body for request {response.get('requestId', 'N/A')}: {e}. Response might be too large or already processed.",
                exc_info=True)
            return ''
        except Exception as e:
            logger.error(f"Unexpected error getting response body for {response.get('requestId', 'N/A')}: {e}",
                         exc_info=True)
            return ''

    @wait_until_finished(timeout=None,
                         throw_exception=False)
    def get_responses(self) -> list[Response]:
        with self._requests_lock:
            responses = [x['response'] for x in self._requests.values() if 'response' in x]
            return responses

    def get_requests(self) -> list[Request]:
        with self._requests_lock:
            return list(self._requests.values())

    def get_document(self, full: bool = True) -> DOMNode:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        depth = -1 if full else 1
        logger.debug(f"Getting DOM document with depth: {depth}")
        try:
            tree = self._chrome_tab.DOM.getDocument(depth=depth)
            if 'root' not in tree:
                logger.error(f"DOM.getDocument did not return a root node. Response: {tree}")
                raise ChromeException("Failed to get DOM root node.")
            return DOMNode(**tree['root'])
        except pychrome.CallMethodException as e:
            logger.error(f"CDP Call Method error getting DOM: {e}", exc_info=True)
            raise ChromeException(f"Error getting DOM: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error getting DOM: {e}", exc_info=True)
            raise ChromeException(f"Unexpected error getting DOM: {e}") from e

    def add_start_script(self, source: str) -> None:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        logger.debug(f"Adding script to evaluate on new document:\n{source[:100]}...")
        try:
            self._chrome_tab.Page.addScriptToEvaluateOnNewDocument(source=source)
        except pychrome.CallMethodException as e:
            logger.error(f"Failed to add script to evaluate: {e}", exc_info=True)
            raise ChromeException(f"Failed to add script: {e}") from e

    def add_blocked_requests(self, urls: list[str]) -> bool:
        if not self._chrome_tab:
            logger.warning("Chrome tab not initialized. Cannot block requests.")
            return False

        logger.debug(f"Blocking requests for URLs: {urls}")
        try:
            self._chrome_tab.Network.setBlockedURLs(urls=urls)
            logger.debug("Successfully set blocked URLs.")
            return True
        except pychrome.CallMethodException as e:
            logger.warning(f"Could not set blocked URLs (possibly unsupported by browser version): {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error blocking requests: {e}", exc_info=True)
            return False

    def execute_script(self, expression: str, *args: Any) -> Any:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        logger.debug(f"Executing script: '{expression[:100]}...'")
        try:
            eval_result = self._chrome_tab.Runtime.evaluate(
                expression=expression,
                returnByValue=True,
                arguments=args
            )

            if 'result' in eval_result and 'value' in eval_result['result']:
                logger.debug(f"Script execution result value: {eval_result['result']['value']}")
                return eval_result['result']['value']
            elif 'result' in eval_result and 'exceptionDetails' in eval_result['result']:
                exception_details = eval_result['result']['exceptionDetails']
                logger.error(
                    f"Script execution resulted in an exception: {exception_details.get('text', 'Unknown error')}")
                return None
            else:
                logger.warning(f"Script execution returned unexpected result format: {eval_result}")
                return None

        except pychrome.CallMethodException as e:
            logger.error(f"CDP Call Method error executing script: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error executing script: {e}", exc_info=True)
            return None

    def perform_click(self, dom_node: DOMNode, timeout: Optional[int] = None) -> None:

        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        logger.debug(f"Performing click on DOM node with backend ID: {dom_node.backend_id}")
        try:
            resolved_node = self._chrome_tab.DOM.resolveNode(
                backendNodeId=dom_node.backend_id,
                executionContextId=dom_node.execution_context_id,
                _timeout=timeout
            )

            object_id = resolved_node['object']['objectId']

            function_declaration = '''
                (function() { 
                    this.scrollIntoView({ block: "center", behavior: "instant" }); 
                    this.click(); 
                })
            '''
            self._chrome_remote.call_function_on(objectId=object_id,
                                                 functionDeclaration=function_declaration)
            logger.debug("Click performed successfully.")

        except pychrome.CallMethodException as e:
            logger.error(f"CDP Call Method error performing click: {e}", exc_info=True)
            raise ChromeException(f"Error performing click: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error performing click: {e}", exc_info=True)
            raise ChromeException(f"Unexpected error performing click: {e}") from e

    def perform_click_by_selector(self, selector: str, timeout: Optional[int] = None) -> None:
        logger.debug(f"Performing click by selector: '{selector}'")
        try:
            query_result = self._chrome_tab.DOM.querySelector(
                selector=selector,
                nodeId=None,
                _timeout=timeout
            )

            if 'nodeId' not in query_result:
                raise ChromeException(f"Element with selector '{selector}' not found.")

            node_id = query_result['nodeId']

            resolved_node_info = self._chrome_tab.DOM.describeNode(nodeId=node_id, depth=-1)
            backend_node_id = resolved_node_info['node']['backendNodeId']
            execution_context_id = resolved_node_info['node'].get(
                'backendNodeId')

            # Правильный resolveNode вызов:
            resolved_node = self._chrome_tab.DOM.resolveNode(
                backendNodeId=backend_node_id,
                executionContextId=resolved_node_info.get('context', {}).get('id'),
                _timeout=timeout
            )

            object_id = resolved_node['object']['objectId']

            function_declaration = '''
                (function() { 
                    this.scrollIntoView({ block: "center", behavior: "instant" }); 
                    this.click(); 
                })
            '''
            self._chrome_remote.call_function_on(objectId=object_id, functionDeclaration=function_declaration)
            logger.debug(f"Click performed successfully on element with selector '{selector}'.")

        except pychrome.CallMethodException as e:
            logger.error(f"CDP Call Method error performing click by selector '{selector}': {e}", exc_info=True)
            raise ChromeException(f"Error performing click by selector '{selector}': {e}") from e
        except ChromeException as e:
            logger.error(f"ChromeException performing click by selector '{selector}': {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error performing click by selector '{selector}': {e}", exc_info=True)
            raise ChromeException(f"Unexpected error performing click by selector '{selector}': {e}") from e

    def wait(self, timeout: float | None = None) -> None:
        logger.debug(f"Waiting for {timeout} seconds.")
        if self._chrome_tab:
            self._chrome_tab.wait(timeout)
        else:
            logger.warning("Chrome tab not initialized. Cannot perform wait.")

    def stop(self) -> None:
        if self._chrome_tab and not self._chrome_tab._stopped.is_set():
            logger.debug("Stopping Chrome tab.")
            try:
                self._close_tab(self._chrome_tab)
            except (pychrome.RuntimeException, RequestException, pychrome.CallMethodException) as e:
                logger.warning(f"Error during tab close: {e}", exc_info=True)
            self._chrome_tab = None

        if self._chrome_browser:
            logger.debug("Closing Chrome browser.")
            try:
                self._chrome_browser.close()
            except Exception as e:
                logger.warning(f"Error during browser close: {e}", exc_info=True)
            self._chrome_browser = None
            self._dev_url = None

        self.clear_requests()
        self._response_queues = {}
        if self._ping_thread and self._ping_thread.is_alive():
            logger.debug("Signalling tab monitor thread to stop.")
            try:
                self._ping_thread.join(timeout=2)
            except RuntimeError:
                pass
            except Exception as e:
                logger.warning(f"Error joining tab monitor thread: {e}", exc_info=True)

        logger.debug("ChromeRemote stopped.")

    def __enter__(self) -> ChromeRemote:
        self.start()
        return self

    def __exit__(self, exc_type: Optional[type[BaseException]], exc_val: Optional[BaseException],
                 exc_tb: Optional[Any]) -> None:
        self.stop()

    def __repr__(self) -> str:
        classname = self.__class__.__name__
        return f'{classname}(options={self._chrome_options!r}, response_patterns={self._response_patterns!r})'

    def wait_for_selector(self, selector: str, timeout: float = 10.0) -> bool:
        if not self._chrome_tab:
            logger.warning("Chrome tab not initialized. Cannot wait for selector.")
            return False

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                dom_tree = self.get_document(full=True)
                element = dom_tree.search_first(
                    lambda node: node.name == 'div' and selector in node.attributes.get('class',
                                                                                        '').split())
                element_found = self._chrome_remote.execute_script(
                    f"return document.querySelector('{selector}') !== null;")

                if element_found:
                    logger.debug(f"Element with selector '{selector}' found.")
                    return True
            except Exception as e:
                logger.error(f"Error waiting for selector '{selector}': {e}", exc_info=True)
                return False
            time.sleep(0.5)

        logger.warning(f"Timeout waiting for element with selector '{selector}' after {timeout}s.")
        return False

    def call_function_on(self, object_id: str, function_declaration: str, *args: Any, **kwargs: Any) -> Any:

        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        logger.debug(f"Calling function on objectId '{object_id}'...")
        try:
            result = self._chrome_tab.Runtime.callFunctionOn(
                objectId=object_id,
                functionDeclaration=function_declaration,
                arguments=args,
                returnByValue=True,
                awaitScript=kwargs.get('awaitScript', False),
                _timeout=kwargs.get('_timeout')
            )
            if 'result' in result and 'value' in result['result']:
                return result['result']['value']
            elif 'result' in result and 'exceptionDetails' in result['result']:
                exception_details = result['result']['exceptionDetails']
                logger.error(
                    f"Function call resulted in an exception: {exception_details.get('text', 'Unknown error')}")
                return None
            else:
                logger.warning(f"Function call returned unexpected result format: {result}")
                return None
        except pychrome.CallMethodException as e:
            logger.error(f"CDP Call Method error calling function on objectId '{object_id}': {e}", exc_info=True)
            raise ChromeException(f"Error calling function on objectId: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error calling function on objectId '{object_id}': {e}", exc_info=True)
            raise ChromeException(f"Unexpected error calling function on objectId: {e}") from e
