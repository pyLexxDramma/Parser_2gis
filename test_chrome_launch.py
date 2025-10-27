import subprocess
import sys
import time
import os
import requests
import pathlib
from typing import Optional, List, Dict, Any


class MockChromeOptions:
    def __init__(self,
                 remote_port: int = 9222,
                 headless: bool = False,
                 chrome_executable_path: Optional[str] = None,
                 disable_gpu: bool = False,
                 disable_images: bool = False,
                 start_maximized: bool = False,
                 user_data_dir: Optional[str] = None,
                 proxy_server: Optional[str] = None
                 ):
        self.remote_port = remote_port
        self.headless = headless
        self.chrome_executable_path = chrome_executable_path
        self.disable_gpu = disable_gpu
        self.disable_images = disable_images
        self.start_maximized = start_maximized
        self.user_data_dir = user_data_dir
        self.proxy_server = proxy_server

    def to_args(self) -> List[str]:
        args = [
            f"--remote-debugging-port={self.remote_port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
            "--disable-extensions",
            "--disable-infobars",
            "--disable-notifications",
        ]
        if self.headless:
            args.append("--headless")
        if self.disable_gpu:
            args.append("--disable-gpu")
        if self.disable_images:
            args.append("--disable-image-loading")
        if self.start_maximized:
            args.append("--start-maximized")
        if self.user_data_dir:
            args.append(f"--user-data-dir={self.user_data_dir}")
        if self.proxy_server:
            args.append(f"--proxy-server={self.proxy_server}")
        return args


def find_chrome_executable() -> Optional[pathlib.Path]:
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


print("--- Starting Chrome Launch Test ---")

chrome_path_override = None
# chrome_path_override = pathlib.Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

chrome_path = chrome_path_override if chrome_path_override else find_chrome_executable()

if not chrome_path:
    print(
        "Error: Chrome executable not found. Please ensure Chrome is installed and its path is correct, or set 'chrome_executable_path' explicitly.")
    sys.exit(1)

temp_user_data_dir = pathlib.Path("./chrome_user_data_temp")
temp_user_data_dir.mkdir(exist_ok=True)

options = MockChromeOptions(
    remote_port=9222,
    headless=False,
    chrome_executable_path=str(chrome_path),
    user_data_dir=str(temp_user_data_dir.resolve()),
    disable_gpu=False,
    disable_images=False,
)

cmd: List[str] = []
process = None

try:
    cmd = [str(chrome_path)] + options.to_args()
    print(f"Attempting to start Chrome with command: {' '.join(cmd)}")

    process = subprocess.Popen(cmd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                               )
    print(f"Chrome process started with PID: {process.pid}")

    time.sleep(10)

    if process.poll() is not None:
        stderr_output = process.stderr.read().decode(errors='ignore')
        raise Exception(
            f"Chrome process exited immediately after start. Return code: {process.returncode}. Stderr: {stderr_output}")

    dev_url = f'http://127.0.0.1:{options.remote_port}/json'
    max_retries = 15
    print(f"Attempting to connect to DevTools at {dev_url}...")

    for i in range(max_retries):
        try:
            response = requests.get(dev_url, timeout=5)
            response.raise_for_status()
            print("Successfully connected to DevTools!")
            print("Available targets:")
            targets = response.json()
            for target in targets:
                print(f"  - Type: {target.get('type')}, Title: {target.get('title')}, URL: {target.get('url')}")
            break
        except (requests.exceptions.RequestException, subprocess.TimeoutExpired):
            if i == max_retries - 1:
                print(f"Error: Failed to connect to DevTools after {max_retries} retries.")
                if process and process.poll() is None:
                    stderr_output = process.stderr.read().decode(errors='ignore')
                    print(f"Chrome stderr output:\n{stderr_output}")
                raise Exception(f"Failed to connect to DevTools at {dev_url} after {max_retries} retries.") from None
            time.sleep(2)

    print("Chrome launch test successful!")

except FileNotFoundError:
    print(f"Error: Chrome executable not found at '{cmd[0]}'. Please check the path.")
except Exception as e:
    print(f"An error occurred: {e}")
    if process and process.poll() is None:
        print("Trying to terminate Chrome process due to error...")
        try:
            process.kill()
            process.wait(timeout=5)
            print("Chrome process terminated.")
        except Exception as kill_e:
            print(f"Error terminating Chrome process: {kill_e}")
finally:
    if process and process.poll() is None:
        print("Cleaning up Chrome process...")
        try:
            process.kill()
            process.wait(timeout=5)
            print("Chrome process cleaned up.")
        except Exception as e:
            print(f"Error during cleanup: {e}")
    # Очищаем временную директорию, если она была создана
    if 'temp_user_data_dir' in locals() and temp_user_data_dir.exists():
        try:
            import shutil

            shutil.rmtree(temp_user_data_dir)
            print(f"Cleaned up temporary directory: {temp_user_data_dir}")
        except Exception as e:
            print(f"Error cleaning up temporary directory {temp_user_data_dir}: {e}")

print("--- Chrome Launch Test Finished ---")