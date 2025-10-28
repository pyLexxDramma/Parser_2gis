from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, Optional
from uuid import uuid4
import os
import pathlib
import asyncio
import logging

from backend.core.config import Settings
from backend.services.task_queue import TaskQueue
from backend.services.parser_service import ParserService
from backend.schemas.schemas import CompanySearchRequest, Report

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

settings = Settings()

app = FastAPI(
    title="2GIS & Yandex Maps Parser API",
    description="API for searching and parsing company data.",
    version="0.1.0",
    debug=settings.DEBUG
)

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend" / "static"
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

task_queue = TaskQueue()

parser_service = ParserService(settings=settings)

reports_db: Dict[str, Dict[str, Any]] = {}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/process", response_model=Dict[str, str])
async def process_search(company_name: str = Form(...), company_site: str = Form(...), email: str = Form(...)):
    report_id = str(uuid4())

    search_request = CompanySearchRequest(
        report_id=report_id,
        company_name=company_name,
        company_site=company_site,
        email=email
    )

    await task_queue.put_task(search_request)

    reports_db[report_id] = {"status": "processing", "company_name": company_name}

    return {"message": "Search started", "report_id": report_id}

@app.get("/report/{report_id}", response_class=HTMLResponse)
async def get_report_page(request: Request, report_id: str):
    report_data = reports_db.get(report_id)
    if not report_data:
        raise HTTPException(status_code=404, detail="Report not found")

    return templates.TemplateResponse("report.html", {"request": request, "report_id": report_id})

@app.get("/api/report/{report_id}", response_model=Report)
async def get_report_data(report_id: str):
    report_data = reports_db.get(report_id)
    if not report_data:
        raise HTTPException(status_code=404, detail="Report not found")

    if report_data["status"] == "processing":
        return Report(
            report_id=report_id,
            company_name=report_data.get("company_name", "Unknown"),
            status="processing"
        )
    elif report_data["status"] == "completed":
        return Report(
            report_id=report_id,
            company_name=report_data.get("company_name", "Unknown"),
            status="completed",
            yandex_stats={
                "cards_count": 20,
                "total_rating": 4.5,
                "total_reviews": 300,
                "answered_reviews": 180,
                "avg_response_time_days": 7,
                "negative_reviews": 50,
                "positive_reviews": 250
            },
            yandex_cards=[
                {
                    "name": "Card 1",
                    "rating": 4.5,
                    "reviews_count": 10,
                    "answered": 8,
                    "response_time_days": 5,
                    "negative_reviews": 2,
                    "positive_reviews": 8,
                    "reviews": []
                }
            ],
            gis_stats={
                "cards_count": 20,
                "total_rating": 4.3,
                "total_reviews": 300,
                "answered_reviews": 200,
                "avg_response_time_months": 1,
                "negative_reviews": 70,
                "positive_reviews": 230
            },
            gis_cards=[
                {
                    "name": "Card A",
                    "rating": 4.3,
                    "reviews_count": 15,
                    "answered": 12,
                    "response_time_months": 1,
                    "negative_reviews": 5,
                    "positive_reviews": 10,
                    "reviews": []
                }
            ]
        )
    else:  # Ошибка
        return Report(
            report_id=report_id,
            company_name=report_data.get("company_name", "Unknown"),
            status="error",
            error_message=report_data.get("error_message", "Unknown error")
        )

async def task_worker():
    while True:
        task: CompanySearchRequest = await task_queue.get_task()
        report_id = task.report_id

        try:
            time.sleep(10)

            report_data_completed = {
                "status": "completed",
                "company_name": task.company_name,
                "yandex_stats": {
                    "cards_count": 20,
                    "total_rating": 4.5,
                    "total_reviews": 300,
                    "answered_reviews": 180,
                    "avg_response_time_days": 7,
                    "negative_reviews": 50,
                    "positive_reviews": 250
                },
                "yandex_cards": [{
                    "name": "Card 1",
                    "rating": 4.5,
                    "reviews_count": 10,
                    "answered": 8,
                    "response_time_days": 5,
                    "negative_reviews": 2,
                    "positive_reviews": 8,
                    "reviews": []
                }],
                "gis_stats": {
                    "cards_count": 20,
                    "total_rating": 4.3,
                    "total_reviews": 300,
                    "answered_reviews": 200,
                    "avg_response_time_months": 1,
                    "negative_reviews": 70,
                    "positive_reviews": 230
                },
                "gis_cards": [{
                    "name": "Card A",
                    "rating": 4.3,
                    "reviews_count": 15,
                    "answered": 12,
                    "response_time_months": 1,
                    "negative_reviews": 5,
                    "positive_reviews": 10,
                    "reviews": []
                }]
            }
            reports_db[report_id] = report_data_completed

            logger.info(f"Отчёт {report_id} успешно сгенерирован.")

        except Exception as e:
            reports_db[report_id] = {
                "status": "error",
                "company_name": task.company_name,
                "error_message": f"Ошибка при обработке задачи: {str(e)}"
            }
            logger.error(f"Ошибка при обработке задачи {report_id}: {e}", exc_info=True)
        finally:
            task_queue.task_done()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(task_worker())
    logger.info("Рабочий процесс запущен.")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)