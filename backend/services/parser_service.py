import logging
from uuid import UUID
from typing import Optional
from backend.core.config import Settings
from backend.services.schemas.schemas import Report

logger = logging.getLogger(__name__)

class ParserService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def find_and_parse(self, company_name: str, company_site: str, email: str, report_id: UUID) -> Optional[Report]:
        browser = await self._get_browser_instance()
        if not browser:
            return None

        try:
            gis_data_raw = await self._parse_platform(browser, "2gis", company_name, company_site)
            yandex_data_raw = await self._parse_platform(browser, "yandex", company_name, company_site)
            report_object = self._build_report(report_id, company_name, gis_data_raw, yandex_data_raw)

            if report_object.status == "error":
                return None

            return report_object

        except Exception as e:
            return None