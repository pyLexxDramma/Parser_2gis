import asyncio
import logging
from uuid import UUID
from typing import Dict, Any, Optional
from pydantic import ValidationError

from backend.core.config import Settings
from backend.services.parser_service import ParserService
from backend.services.schemas.schemas import Report, CompanySearchRequest, PlatformStats, CompanyCard, Review

logger = logging.getLogger(__name__)

DUMMY_REPORT_DATA_COMPLETED = {
    "report_id": None,
    "company_name": "Dummy Company",
    "status": "completed",
    "error_message": None,
    "yandex_stats": {
        "cards_count": 20,
        "total_rating": 4.5,
        "total_reviews": 300,
        "answered_reviews": 180,
        "avg_response_time_days": 7,
        "negative_reviews_count": 50,
        "positive_reviews_count": 250
    },
    "yandex_cards": [
        {
            "name": "Dummy Yandex Card 1",
            "url": "http://example.com/yandex/card-1",
            "rating": 4.5,
            "reviews_count": 10,
            "answered_reviews": 8,
            "response_time_str": "1 week",
            "negative_reviews_count": 2,
            "positive_reviews_count": 8,
            "reviews": []
        }
    ],
    "gis_stats": {
        "cards_count": 20,
        "total_rating": 4.3,
        "total_reviews": 300,
        "answered_reviews": 200,
        "avg_response_time_months": 1,
        "negative_reviews_count": 70,
        "positive_reviews_count": 230
    },
    "gis_cards": [
        {
            "name": "Dummy 2GIS Card A",
            "url": "http://example.com/gis/card-a",
            "rating": 4.3,
            "reviews_count": 15,
            "answered_reviews": 12,
            "response_time_str": "1 month",
            "negative_reviews_count": 5,
            "positive_reviews_count": 10,
            "reviews": []
        }
    ]
}

class TaskQueue:
    def __init__(self):
        logger.info("TaskQueue initializing...")
        self._queue = asyncio.Queue()
        if not isinstance(self._queue, asyncio.Queue):
            logger.error("TaskQueue.__init__: self._queue is NOT an asyncio.Queue! Type is %s", type(self._queue))
            raise TypeError("self._queue must be an asyncio.Queue")
        else:
            logger.info("TaskQueue.__init__: self._queue is successfully initialized as asyncio.Queue.")

        self._tasks: Dict[str, Dict[str, Any]] = {}

        self.settings = Settings()
        try:
            self.parser_service = ParserService(settings=self.settings)
            logger.info("ParserService initialized successfully in TaskQueue.")
        except Exception as e:
            logger.error(f"Failed to initialize ParserService in TaskQueue: {e}", exc_info=True)
            raise

        logger.info("TaskQueue initialized.")

    async def add_task(self, request: CompanySearchRequest, report_id: str):
        logger.info(f"TaskQueue.add_task: Attempting to add task {report_id} for {request.company_name} to queue.")
        if not isinstance(self._queue, asyncio.Queue):
            logger.error("TaskQueue.add_task: self._queue is not an asyncio.Queue! Cannot add task.")
            raise TypeError("self._queue is not an asyncio.Queue, cannot add task.")

        try:
            await self._queue.put((report_id, request))
            logger.info(f"TaskQueue.add_task: Task {report_id} successfully put into self._queue.")  # ЛОГ 5
        except Exception as e:
            logger.error(f"TaskQueue.add_task: Error putting task {report_id} into self._queue: {e}", exc_info=True)
            raise

        self._tasks[report_id] = {
            "request": request,
            "status": "pending",
            "report": None,
            "error_message": None
        }
        logger.info(f"TaskQueue.add_task: Task {report_id} added to _tasks. Current _tasks keys: {list(self._tasks.keys())}")

    async def process_tasks(self):
        logger.info("TaskQueue.process_tasks: Starting task processing loop.")
        while True:
            report_id = None
            request = None
            try:
                logger.debug(f"TaskQueue.process_tasks: Before await self._queue.get(). Queue size: {self._queue.qsize()}")
                report_id, request = await self._queue.get()
                logger.info(f"TaskQueue.process_tasks: Retrieved task {report_id} ({request.company_name}) from queue.")

                if not hasattr(self, 'parser_service') or not self.parser_service:
                    logger.error(f"TaskQueue.process_tasks: ParserService not available for task {report_id}.")
                    if report_id in self._tasks:
                        self._tasks[report_id]["status"] = "error"
                        self._tasks[report_id]["error_message"] = "Parser service unavailable."
                    self._queue.task_done()
                    continue

                if report_id in self._tasks:
                    self._tasks[report_id]["status"] = "processing"
                    logger.info(f"TaskQueue.process_tasks: Set status for task {report_id} to 'processing'.")
                else:
                    logger.warning(f"TaskQueue.process_tasks: Retrieved task {report_id} not found in _tasks. Creating entry for processing.")
                    self._tasks[report_id] = {
                        "request": request, "status": "processing", "report": None, "error_message": None
                    }

                logger.info(f"TaskQueue.process_tasks: Simulating parsing and using dummy data for task {report_id} ({request.company_name}).")
                await asyncio.sleep(10)

                dummy_report_data_raw = {
                    "report_id": report_id,
                    "company_name": request.company_name,
                    "status": "completed",
                    "yandex_stats": {
                        "cards_count": 20,
                        "total_rating": 4.5,
                        "total_reviews": 300,
                        "answered_reviews": 180,
                        "avg_response_time_days": 7,
                        "negative_reviews_count": 50,
                        "positive_reviews_count": 250
                    },
                    "yandex_cards": [
                        {
                            "name": "Card 1",
                            "url": "http://example.com/yandex/card-1",
                            "rating": 4.5,
                            "reviews_count": 10,
                            "answered_reviews": 8,
                            "response_time_str": "1 week",
                            "negative_reviews_count": 2,
                            "positive_reviews_count": 8,
                            "reviews": []
                        }
                    ],
                    "gis_stats": {
                        "cards_count": 20,
                        "total_rating": 4.3,
                        "total_reviews": 300,
                        "answered_reviews": 200,
                        "avg_response_time_months": 1,
                        "negative_reviews_count": 70,
                        "positive_reviews_count": 230
                    },
                    "gis_cards": [
                        {
                            "name": "Card A",
                            "url": "http://example.com/gis/card-a",
                            "rating": 4.3,
                            "reviews_count": 15,
                            "answered_reviews": 12,
                            "response_time_str": "1 month",
                            "negative_reviews_count": 5,
                            "positive_reviews_count": 10,
                            "reviews": []
                        }
                    ],
                    "error_message": None
                }

                report = Report(**dummy_report_data_raw)

                self._tasks[report_id]["report"] = report
                self._tasks[report_id]["status"] = "completed"
                logger.info(f"TaskQueue.process_tasks: Task {report_id} completed successfully with dummy data.")

            except asyncio.CancelledError:
                logger.info("TaskQueue.process_tasks: Task processing loop cancelled.")
                if report_id and report_id in self._tasks:
                    self._tasks[report_id]["status"] = "cancelled"
                    self._tasks[report_id]["error_message"] = "Task processing cancelled."
                break

            except ValidationError as e:
                logger.error(f"TaskQueue.process_tasks: ValidationError for task {report_id} ({request.company_name}): {e}", exc_info=True)
                if report_id in self._tasks:
                    self._tasks[report_id]["status"] = "error"
                    self._tasks[report_id]["error_message"] = f"Data validation error: {str(e)}"

            except Exception as e:
                logger.error(f"TaskQueue.process_tasks: Unhandled exception in task processing loop for task {report_id} ({request.company_name}): {e}", exc_info=True)
                if report_id in self._tasks:
                    self._tasks[report_id]["status"] = "error"
                    self._tasks[report_id]["error_message"] = f"An unexpected error occurred: {str(e)}"

            finally:
                if report_id is not None and request is not None:
                    try:
                        self._queue.task_done()
                        logger.debug(f"TaskQueue.process_tasks: Task {report_id} task_done() called.")
                    except Exception as td_e:
                        logger.error(f"TaskQueue.process_tasks: Error calling task_done() for task {report_id}: {td_e}", exc_info=True)
                else:
                    logger.warning("TaskQueue.process_tasks: task_done() not called because task was not retrieved from queue.")

    def get_task_info(self, report_id: str) -> Optional[Dict[str, Any]]:
        logger.debug(f"TaskQueue.get_task_info: Retrieving info for task {report_id}. Current tasks keys: {list(self._tasks.keys())}")
        return self._tasks.get(report_id)

    def get_report_data(self, report_id: str) -> Optional[Report]:
        task_info = self.get_task_info(report_id)
        if task_info and task_info.get("status") == "completed":
            return task_info.get("report")
        elif task_info and task_info.get("status") == "error":
            logger.warning(f"TaskQueue.get_report_data: Task {report_id} has status 'error'. Returning error info.")
            error_report_data = {
                "report_id": UUID(report_id) if report_id else None,
                "company_name": task_info.get("request").company_name if task_info.get("request") else "Unknown",
                "status": "error",
                "error_message": task_info.get("error_message", "Unknown error"),
            }
            try:
                return Report(**error_report_data)
            except ValidationError as e:
                logger.error(f"TaskQueue.get_report_data: ValidationError creating error Report for {report_id}: {e}", exc_info=True)
                return None
        return None

    def notify_user(self, email: str, report_id: str, message: str):
        logger.info(f"NOTIFY: User {email} about report {report_id}: {message}")

    async def run_worker(self):
        logger.info("TaskQueue.run_worker: Creating task for process_tasks.")
        asyncio.create_task(self.process_tasks())
        logger.info("TaskQueue.run_worker: process_tasks task created.")