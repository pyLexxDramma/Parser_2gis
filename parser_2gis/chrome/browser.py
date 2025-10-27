import subprocess
import time
import sys
import signal
import psutil
import pychrome
import requests
import pathlib
import os
from typing import Optional, List

from .options import ChromeOptions
from .exceptions import ChromeException


class ChromeBrowser:
    def __init__(self, chrome_options: ChromeOptions):
        self._chrome_options = chrome_options
        self._process: Optional[subprocess.Popen] = None
        self.remote_port: Optional[int] = None
        self._dev_url: Optional[str] = None

        self.chrome_executable = chrome_options.chrome_executable_path
        if not self.chrome_executable:
            self.chrome_executable = self._find_chrome_executable()
            if not self.chrome_executable:
                raise ChromeException(
                    "Chrome executable not found. Please specify 'chrome_executable_path' in ChromeOptions or ensure Chrome is in your PATH.")

    def _find_chrome_executable(self) -> Optional[pathlib.Path]:
        if sys.platform == "win32":
            possible_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]
            for path_str in possible_paths:
                if os.path.exists(path_str):
                    return pathlib.Path(path_str)
        elif sys.platform == "darwin":
            possible_path_str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if os.path.exists(possible_path_str):
                return pathlib.Path(possible_path_str)
        else:
            for path_dir in os.environ.get("PATH", "").split(os.pathsep):
                exe_path = os.path.join(path_dir, "google-chrome")
                if os.path.exists(exe_path):
                    return pathlib.Path(exe_path)
            for path_dir in os.environ.get("PATH", "").split(os.pathsep):
                exe_path = os.path.join(path_dir, "chrome")
                if os.path.exists(exe_path):
                    return pathlib.Path(exe_path)
        return None

    def start(self) -> None:
        if self._process is not None:
            return

        cmd = [str(self.chrome_executable)] + self._chrome_options.to_args()

        try:
            self._process = subprocess.Popen(cmd,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE,
                                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                                             )

            time.sleep(5)

            if self._process.poll() is not None:
                stderr_output = self._process.stderr.read().decode(errors='ignore')
                raise ChromeException(
                    f"Chrome process exited immediately after start. Return code: {self._process.returncode}. Stderr: {stderr_output}")

            self.remote_port = self._chrome_options.remote_port
            self._dev_url = f'http://127.0.0.1:{self.remote_port}'

            max_retries = 15
            for i in range(max_retries):
                try:
                    response = requests.get(self._dev_url + "/json", timeout=5)
                    response.raise_for_status()
                    break
                except (requests.exceptions.RequestException, subprocess.TimeoutExpired):
                    if i == max_retries - 1:
                        self.close()
                        raise ChromeException(
                            f"Failed to connect to Chrome DevTools at {self._dev_url} after {max_retries} retries. Process PID: {self._process.pid if self._process else 'N/A'}") from None
                    time.sleep(2)

            print(f"Chrome browser started successfully. PID: {self._process.pid}. DevTools URL: {self._dev_url}")

        except FileNotFoundError:
            self.close()
            raise ChromeException(f"Chrome executable not found at '{self.chrome_executable}'.") from None
        except Exception as e:
            self.close()
            raise ChromeException(f"Error starting Chrome browser: {e}. Command: {' '.join(cmd)}") from e

    def close(self) -> None:
        if self._process is None:
            return

        if self._process.poll() is None:
            try:
                if sys.platform == "win32":
                    self._process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    self._process.send_signal(signal.SIGTERM)

                try:
                    self._process.wait(timeout=10)
                    print(f"Chrome process {self._process.pid} terminated gracefully.")
                except subprocess.TimeoutExpired:
                    print(f"Chrome process {self._process.pid} did not terminate gracefully, killing it.")
                    self._process.kill()
                    self._process.wait()
                    print(f"Chrome process {self._process.pid} forcefully killed.")

            except Exception as e:
                print(f"Error during Chrome process termination for PID {self._process.pid}: {e}")
                try:
                    self._process.kill()
                    self._process.wait()
                except Exception as kill_e:
                    print(f"Error during forceful kill for PID {self._process.pid}: {kill_e}")

        self._process = None
        self.remote_port = None
        self._dev_url = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()