import asyncio
import pathlib
import logging
from typing import Any, Dict, List, Optional

from backend.core.config import Settings
from parser_2gis.chrome.options import ChromeOptions
from parser_2gis.chrome.remote import ChromeRemote
from parser_2gis.chrome.exceptions import ChromeException
from backend.schemas.schemas import CompanySearchRequest, Report, PlatformStats, CompanyCard, Review

logger = logging.getLogger(__name__)


class YandexParser:
    def __init__(self, chrome_options: ChromeOptions):
        self.chrome_options = chrome_options
        print("YandexParser initialized.")

    async def find_and_parse(self, company_name: str, company_site: str, max_cards: int) -> Dict[str, Any]:
        print(f"Simulating Yandex parse for {company_name}...")
        await asyncio.sleep(2)
        return {
            "stats": PlatformStats(
                cards_count=10, total_rating=4.5, total_reviews=100, answered_reviews=50, avg_response_time_days=5,
                negative_reviews_count=20, positive_reviews_count=80
            ),
            "cards": [
                CompanyCard(
                    name=f"{company_name} - Card Y1", url="http://example.com/y1", rating=4.5, reviews_count=10,
                    answered_reviews=8, response_time_str="5 дней", negative_reviews_count=2, positive_reviews_count=8,
                    reviews=[]
                )
            ]
        }


class GisParser:
    def __init__(self, chrome_options: ChromeOptions):
        self.chrome_options = chrome_options
        print("GisParser initialized.")

    async def find_and_parse(self, company_name: str, company_site: str, max_cards: int) -> Dict[str, Any]:
        print(f"Simulating 2GIS parse for {company_name}...")
        await asyncio.sleep(2)
        return {
            "stats": PlatformStats(
                cards_count=15, total_rating=4.2, total_reviews=150, answered_reviews=100, avg_response_time_months=1,
                negative_reviews_count=30, positive_reviews_count=120
            ),
            "cards": [
                CompanyCard(
                    name=f"{company_name} - Card G1", url="http://example.com/g1", rating=4.2, reviews_count=15,
                    answered_reviews=12, response_time_str="1 месяц", negative_reviews_count=5,
                    positive_reviews_count=10, reviews=[]
                )
            ]
        }


class ParserService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.chrome_options = ChromeOptions(
            remote_port=settings.CHROME_REMOTE_PORT,
            headless=settings.CHROME_HEADLESS,
            chrome_executable_path=settings.CHROME_EXECUTABLE_PATH,
            user_data_dir=settings.CHROME_USER_DATA_DIR,
            proxy_server=settings.CHROME_PROXY_SERVER,
            start_maximized=settings.CHROME_START_MAXIMIZED,
            disable_images=settings.CHROME_DISABLE_IMAGES,
            disable_gpu=settings.CHROME_DISABLE_GPU,
        )

        if not self.chrome_options.chrome_executable_path:
            raise ChromeException("Chrome executable path not configured or found in settings.")

        self.yandex_parser = YandexParser(self.chrome_options)
        self.gis_parser = GisParser(self.chrome_options)

    async def parse_company(self, request: CompanySearchRequest) -> Report:
        report = Report(
            report_id=request.report_id,
            company_name=request.company_name,
            status="processing"
        )

        try:
            print(f"Starting parsing for {request.company_name}...")

            print(f"Parsing Yandex for {request.company_name}...")
            yandex_data = await self.yandex_parser.find_and_parse(
                company_name=request.company_name,
                company_site=request.company_site,
                max_cards=self.settings.MAX_COMPANIES_PER_QUERY
            )
            report.yandex_stats = yandex_data.get("stats")
            report.yandex_cards = yandex_data.get("cards", [])
            print(f"Yandex parsing complete. Found {len(yandex_data.get('cards', []))} cards.")

            print(f"Parsing 2GIS for {request.company_name}...")
            gis_data = await self.gis_parser.find_and_parse(
                company_name=request.company_name,
                company_site=request.company_site,
                max_cards=self.settings.MAX_COMPANIES_PER_QUERY
            )
            report.gis_stats = gis_data.get("stats")
            report.gis_cards = gis_data.get("cards", [])
            print(f"2GIS parsing complete. Found {len(gis_data.get('cards', []))} cards.")

            report.status = "completed"

        except ChromeException as e:
            report.status = "error"
            report.error_message = f"Chrome error during parsing: {e}"
            print(f"Chrome error during parsing: {e}")
        except Exception as e:
            report.status = "error"
            report.error_message = f"Unexpected error during parsing: {e}"
            print(f"Unexpected error during parsing: {e}")

        return report