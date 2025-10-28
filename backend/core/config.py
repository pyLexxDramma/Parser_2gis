from pydantic_settings import BaseSettings
import pathlib
from typing import Optional

class Settings(BaseSettings):
    CHROME_EXECUTABLE_PATH: Optional[pathlib.Path] = None
    CHROME_REMOTE_PORT: int = 9222
    CHROME_HEADLESS: bool = True
    CHROME_USER_DATA_DIR: Optional[pathlib.Path] = None
    CHROME_PROXY_SERVER: Optional[str] = None
    CHROME_START_MAXIMIZED: bool = False
    CHROME_DISABLE_IMAGES: bool = True
    CHROME_DISABLE_GPU: bool = False

    SECRET_KEY: str = "your-super-secret-key"
    DEBUG: bool = True

    EMAIL_HOST: Optional[str] = None
    EMAIL_PORT: Optional[int] = None
    EMAIL_USE_TLS: bool = False
    EMAIL_USE_SSL: bool = False
    EMAIL_USERNAME: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None
    EMAIL_SUBJECT_PREFIX: str = "[EgoScan]"

    MAX_COMPANIES_PER_QUERY: int = 20
    REPORT_STORAGE_PATH: pathlib.Path = pathlib.Path("reports")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True