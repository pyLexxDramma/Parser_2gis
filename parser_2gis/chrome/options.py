from __future__ import annotations

import pathlib
from typing import Optional, List

import psutil
from pydantic import BaseModel, PositiveInt

from parser_2gis.common import floor_to_hundreds


def default_memory_limit() -> int:
    memory_total = psutil.virtual_memory().total / 1024 ** 2
    return floor_to_hundreds(round(0.75 * memory_total))


class ChromeOptions(BaseModel):
    binary_path: Optional[pathlib.Path] = None
    start_maximized: bool = False
    headless: bool = False
    disable_images: bool = True
    silent_browser: bool = True
    memory_limit: PositiveInt = default_memory_limit()
    chrome_executable_path: Optional[pathlib.Path] = None
    remote_port: int = 9222
    user_data_dir: Optional[pathlib.Path] = None
    proxy_server: Optional[str] = None

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