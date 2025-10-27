from __future__ import annotations

import base64
import queue
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, List

import pychrome
import requests
from requests.exceptions import RequestException
from websocket import WebSocketException

from parser_2gis.common import wait_until_finished, floor_to_hundreds
from parser_2gis.chrome.browser import ChromeBrowser
from parser_2gis.chrome.dom import DOMNode
from parser_2gis.chrome.exceptions import ChromeException, ChromeRuntimeException
from parser_2gis.chrome.options import ChromeOptions
from parser_2gis.chrome.patches import patch_all
from parser_2gis.logger import logger

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
            return False

        try:
            self._chrome_interface = pychrome.Browser(url=self._dev_url)
            self._chrome_tab = self._create_tab()
            self._chrome_tab.start()
            return True
        except (RequestException, WebSocketException, pychrome.CallMethodException):
            return False

    def start(self) -> None:
        if self._chrome_browser is not None:
            return

        self._chrome_browser = ChromeBrowser(self._chrome_options)
        self._dev_url = f'http://127.0.0.1:{self._chrome_browser.remote_port}'

        if not self._connect_interface():
            if self._chrome_browser:
                self._chrome_browser.close()
                self._chrome_browser = None
            return

        self._setup_tab()
        self._init_tab_monitor()

    def _create_tab(self) -> pychrome.Tab:
        if not self._dev_url:
            raise ChromeException("Chrome DevTools URL not set.")
        try:
            resp = requests.put('%s/json/new' % (self._dev_url), json=True)
            resp.raise_for_status()
            return pychrome.Tab(**resp.json())
        except (RequestException, pychrome.CallMethodException) as e:
            raise ChromeException(f"Could not create new tab: {e}") from e

    def _close_tab(self, tab: pychrome.Tab) -> None:
        if tab.status == pychrome.Tab.status_started:
            tab.stop()

        if not self._dev_url:
            return

        try:
            requests.put('%s/json/close/%s' % (self._dev_url, tab.id))
        except RequestException as e:
            pass

    def _setup_tab(self) -> None:
        original_useragent = self.execute_script('navigator.userAgent')
        fixed_useragent = original_useragent.replace(' HeadlessChrome/', ' Chrome/')
        self._chrome_tab.Network.setUserAgentOverride(userAgent=fixed_useragent)

        self.add_start_script(r'''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        ''')

    def _enable_domains(self) -> None:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        try:
            self._chrome_tab.Network.enable()
            self._chrome_tab.DOM.enable()
            self._chrome_tab.Page.enable()
            self._chrome_tab.Runtime.enable()
            self._chrome_tab.Log.enable()
        except pychrome.CallMethodException as e:
            raise ChromeException(f"Failed to enable CDP domains: {e}") from e

    def _init_tab_monitor(self) -> None:
        if self._chrome_tab is None:
            raise ChromeException("Chrome tab is not initialized for monitoring.")

        tab_detached = False

        def monitor_tab() -> None:
            while not self._chrome_tab._stopped.is_set():
                try:
                    if not self._dev_url:
                        break

                    ret = requests.get(f'{self._dev_url}/json', timeout=1)
                    ret.raise_for_status()

                    if not any(x['id'] == self._chrome_tab.id for x in ret.json()):
                        nonlocal tab_detached
                        tab_detached = True
                        self._chrome_tab._stopped.set()
                        break

                    self._chrome_tab._stopped.wait(0.5)
                except ConnectionError:
                    tab_detached = True
                    self._chrome_tab._stopped.set()
                    break
                except requests.Timeout:
                    tab_detached = True
                    self._chrome_tab._stopped.set()
                    break
                except Exception as e:
                    tab_detached = True
                    self._chrome_tab._stopped.set()
                    break

        self._ping_thread = threading.Thread(target=monitor_tab, daemon=True)
        self._ping_thread.start()

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
                    if tab_detached:
                        raise pychrome.RuntimeException('Tab has been stopped') from e
                    else:
                        raise

            return wrapped_send

        self._chrome_tab._send = get_send_with_reraise()

    def navigate(self, url: str, referer: str = '', timeout: int = 60) -> None:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        try:
            ret = self._chrome_tab.Page.navigate(url=url, _timeout=timeout, referrer=referer)
            error_message = ret.get('errorText', None)
            if error_message:
                raise ChromeException(f"Navigation failed: {error_message}")
        except pychrome.RuntimeException as e:
            raise ChromeException(f"Tab stopped during navigation: {e}") from e
        except pychrome.CallMethodException as e:
            raise ChromeException(f"CDP Call Method error during navigation: {e}") from e
        except Exception as e:
            raise ChromeException(f"Unexpected error during navigation: {e}") from e

    @wait_until_finished(timeout=30, throw_exception=False)
    def wait_response(self, response_pattern: str) -> Response | None:
        if self._chrome_tab is None:
            return None

        if self._chrome_tab._stopped.is_set():
            return None

        try:
            return self._response_queues[response_pattern].get(block=False)
        except queue.Empty:
            return None
        except KeyError:
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

    @wait_until_finished(timeout=15, throw_exception=False)
    def get_response_body(self, response: Response) -> str:
        if not self._chrome_tab:
            return ''

        try:
            request_id = response.get('requestId')
            if not request_id:
                return ''

            response_data = self._chrome_tab.call_method('Network.getResponseBody',
                                                         requestId=request_id)
            body = response_data.get('body', '')
            base64_encoded = response_data.get('base64Encoded', False)

            if base64_encoded and body:
                try:
                    body = base64.b64decode(body).decode('utf-8', errors='ignore')
                except Exception as e:
                    body = ''

            response['body'] = body
            return body
        except pychrome.CallMethodException as e:
            return ''
        except Exception as e:
            return ''

    @wait_until_finished(timeout=None, throw_exception=False)
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
        try:
            tree = self._chrome_tab.DOM.getDocument(depth=depth)
            if 'root' not in tree:
                raise ChromeException("Failed to get DOM root node.")
            return DOMNode(**tree['root'])
        except pychrome.CallMethodException as e:
            raise ChromeException(f"Error getting DOM: {e}") from e
        except Exception as e:
            raise ChromeException(f"Unexpected error getting DOM: {e}") from e

    def add_start_script(self, source: str) -> None:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        try:
            self._chrome_tab.Page.addScriptToEvaluateOnNewDocument(source=source)
        except pychrome.CallMethodException as e:
            raise ChromeException(f"Failed to add script: {e}") from e

    def add_blocked_requests(self, urls: list[str]) -> bool:
        if not self._chrome_tab:
            return False

        try:
            self._chrome_tab.Network.setBlockedURLs(urls=urls)
            return True
        except pychrome.CallMethodException as e:
            return False
        except Exception as e:
            return False

    def execute_script(self, expression: str, *args: Any) -> Any:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        try:
            eval_result = self._chrome_tab.Runtime.evaluate(
                expression=expression,
                returnByValue=True,
                arguments=args
            )
            if 'result' in eval_result and 'value' in eval_result['result']:
                return eval_result['result']['value']
            elif 'result' in eval_result and 'exceptionDetails' in eval_result['result']:
                exception_details = eval_result['result']['exceptionDetails']
                raise ChromeException(
                    f"Script execution resulted in an exception: {exception_details.get('text', 'Unknown error')}")
            else:
                return None

        except pychrome.CallMethodException as e:
            raise ChromeException(f"CDP Call Method error executing script: {e}") from e
        except Exception as e:
            raise ChromeException(f"Unexpected error executing script: {e}") from e

    def perform_click(self, dom_node: DOMNode, timeout: Optional[int] = None) -> None:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

        try:
            resolved_node = self._chrome_tab.DOM.resolveNode(
                backendNodeId=dom_node.backendNodeId,
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
            self.call_function_on(objectId=object_id, functionDeclaration=function_declaration)

        except pychrome.CallMethodException as e:
            raise ChromeException(f"Error performing click: {e}") from e
        except ChromeException as e:
            raise e
        except Exception as e:
            raise ChromeException(f"Unexpected error performing click: {e}") from e

    def perform_click_by_selector(self, selector: str, timeout: Optional[int] = None) -> None:
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
            execution_context_id = resolved_node_info.get('context', {}).get('id')

            if not execution_context_id:
                raise ChromeException("Could not get execution context ID for the node.")

            resolved_node = self._chrome_tab.DOM.resolveNode(
                backendNodeId=backend_node_id,
                executionContextId=execution_context_id,
                _timeout=timeout
            )

            object_id = resolved_node['object']['objectId']

            function_declaration = '''
                (function() { 
                    this.scrollIntoView({ block: "center", behavior: "instant" }); 
                    this.click(); 
                })
            '''
            self.call_function_on(objectId=object_id, functionDeclaration=function_declaration)

        except pychrome.CallMethodException as e:
            raise ChromeException(f"Error performing click by selector '{selector}': {e}") from e
        except ChromeException as e:
            raise e
        except Exception as e:
            raise ChromeException(f"Unexpected error performing click by selector '{selector}': {e}") from e

    def wait(self, timeout: float | None = None) -> None:
        if self._chrome_tab:
            self._chrome_tab.wait(timeout)

    def stop(self) -> None:
        if self._chrome_tab and not self._chrome_tab._stopped.is_set():
            try:
                self._close_tab(self._chrome_tab)
            except (pychrome.RuntimeException, RequestException, pychrome.CallMethodException) as e:
                pass
            self._chrome_tab = None

        if self._chrome_browser:
            try:
                self._chrome_browser.close()
            except Exception as e:
                pass
            self._chrome_browser = None
            self._dev_url = None

        self.clear_requests()
        self._response_queues = {}

        if self._ping_thread and self._ping_thread.is_alive():
            try:
                self._ping_thread.join(timeout=2)
            except RuntimeError:
                pass
            except Exception as e:
                pass

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
            return False

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                element_exists = self._chrome_remote.execute_script(
                    f"return document.querySelector('{selector}') !== null;"
                )

                if element_exists:
                    return True
            except ChromeException as e:
                return False
            except Exception as e:
                pass

            time.sleep(0.5)

        return False

    def call_function_on(self, object_id: str, function_declaration: str, *args: Any, **kwargs: Any) -> Any:
        if not self._chrome_tab:
            raise ChromeException("Chrome tab is not initialized.")

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
                raise ChromeException(
                    f"Function call resulted in an exception: {exception_details.get('text', 'Unknown error')}")
            else:
                return None
        except pychrome.CallMethodException as e:
            raise ChromeException(f"Error calling function on objectId: {e}") from e
        except Exception as e:
            raise ChromeException(f"Unexpected error calling function on objectId: {e}") from e