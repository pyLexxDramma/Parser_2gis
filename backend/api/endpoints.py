from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ValidationError
from uuid import UUID, uuid4
import logging

from backend.services.task_queue import TaskQueue
from backend.dependencies import get_task_queue

from backend.services.schemas.schemas import Report, CompanySearchRequest

logger = logging.getLogger(__name__)
router = APIRouter()

class CompanySearchRequestApi(BaseModel):
    company_name: str
   # company_site: str
   # email: str


@router.post("/process", status_code=202)
async def start_processing(
        request: CompanySearchRequestApi,
        task_queue: TaskQueue = Depends(get_task_queue)
):
    if not task_queue:  # Эта проверка очень важна
        logger.critical("POST /process: TaskQueue instance is None after Dependency Injection!")
        raise HTTPException(status_code=500, detail="Task processing is not configured.")

    logger.info(f"POST /process: TaskQueue instance is available: {task_queue}")  # ЛОГ 1

    report_id_uuid = uuid4()
    report_id_str = str(report_id_uuid)
    logger.info(f"POST /process: Received request for {request.company_name}. Report ID: {report_id_str}.")  # ЛОГ 2

    search_request = CompanySearchRequest(
        report_id=report_id_uuid,
        company_name=request.company_name,
        company_site=request.company_site,
        email=request.email
    )

    try:
        logger.info(f"POST /process: Calling task_queue.add_task() for report_id {report_id_str}.")  # ЛОГ 3
        await task_queue.add_task(search_request, report_id_str)
        logger.info(
            f"POST /process: task_queue.add_task() completed successfully for report_id {report_id_str}.")  # ЛОГ 4
        return {"message": "Search started", "report_id": report_id_str}
    except Exception as e:
        logger.error(f"POST /process: Exception calling task_queue.add_task() for report_id {report_id_str}: {e}",
                     exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start processing.")

@router.get("/api/report/{report_id}", response_model=Report)
async def get_report_data(
    report_id: str,
    task_queue: TaskQueue = Depends(get_task_queue)
):
    pass
