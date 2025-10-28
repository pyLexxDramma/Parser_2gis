import asyncio
import logging
from uuid import UUID, uuid4
from typing import Dict, Any, Optional

from backend.services.parser_service import ParserService
from backend.schemas.schemas import CompanySearchRequest, Report
from backend.core.config import Settings

logger = logging.getLogger(__name__)

class TaskQueue:
    def __init__(self):
        self._queue = asyncio.Queue()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self.settings = Settings()
        try:
            self.parser_service = ParserService(settings=self.settings)
            logger.info("ParserService initialized in TaskQueue.")
        except Exception as e:
            logger.error(f"Failed to initialize ParserService in TaskQueue: {e}", exc_info=True)

    async def add_task(self, request: CompanySearchRequest, report_id: str):
        logger.info(f"Adding task {report_id} to queue for {request.company_name}.")
        await self._queue.put((report_id, request))
        self._tasks[report_id] = {
            "request": request,
            "status": "pending",
            "report": None,
            "error_message": None
        }

    async def process_tasks(self):
        logger.info("Task processing loop started.")
        while True:
            try:
                report_id, request = await self._queue.get()
                logger.info(f"Processing task {report_id} for {request.company_name}...")
                self._tasks[report_id]["status"] = "processing"
                if not hasattr(self, 'parser_service') or not self.parser_service:
                    logger.error("ParserService not available in TaskQueue.")
                    self._tasks[report_id]["status"] = "error"
                    self._tasks[report_id]["error_message"] = "Parser service unavailable."
                    self._queue.task_done()
                    continue
                try:
                    report: Optional[Report] = await self.parser_service.find_and_parse(
                        company_name=request.company_name,
                        company_site=request.company_site,
                        email=request.email,
                        report_id=report_id
                    )
                    if report:
                        self._tasks[report_id]["report"] = report
                        self._tasks[report_id]["status"] = "completed"
                        logger.info(f"Report {report_id} generated successfully for {request.company_name}.")
                    else:
                        self._tasks[report_id]["status"] = "error"
                        self._tasks[report_id]["error_message"] = "Parsing failed or returned no data."
                        logger.error(f"Report generation failed for {report_id} ({request.company_name}).")
                except Exception as e:
                    logger.error(f"Error during parsing task {report_id} ({request.company_name}): {e}", exc_info=True)
                    self._tasks[report_id]["status"] = "error"
                    self._tasks[report_id]["error_message"] = str(e)
                finally:
                    self._queue.task_done()
            except Exception as e:
                logger.error(f"Unexpected error in task processing loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    def get_task_status(self, report_id: str):
        return self._tasks.get(report_id, {"status": "not_found"})

    def get_report_data(self, report_id: str) -> Optional[Report]:
        task_info = self._tasks.get(report_id)
        if task_info and task_info["status"] == "completed":
            return task_info["report"]
        return None

    def notify_user(self, email: str, report_id: str, message: str):
        logger.info(f"NOTIFY: User {email} about report {report_id}: {message}")

    async def run_worker(self):
        logger.info("Task worker starting...")
        asyncio.create_task(self.process_tasks())
        logger.info("Task worker loop scheduled.")