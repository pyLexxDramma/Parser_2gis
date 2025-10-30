from fastapi import FastAPI, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pathlib
import logging
import asyncio

from backend.core.config import Settings
from backend.api.endpoints import router
from backend.dependencies import get_task_queue, task_queue_instance

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

settings = Settings()

app = FastAPI(
    title="2GIS & Yandex Maps Parser API",
    description="API for searching and parsing company data.",
    version="0.1.0",
    debug=settings.DEBUG,
)

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend" / "static"
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    logger.debug(f"Incoming request: {request.method} {request.url}")
    logger.debug(f"Headers: {request.headers}")
    response = await call_next(request)
    logger.debug(f"Response status: {response.status_code}")
    return response
app.include_router(router, dependencies=[Depends(get_task_queue)])

async def task_worker():
    logger.info("Task worker starting...")
    asyncio.create_task(task_queue_instance.process_tasks())
    logger.info("Task worker loop scheduled.")

@app.on_event("startup")
async def startup_event():
    logger.info("Startup event: Calling task_worker.")
    await task_worker()
    logger.info("Startup event: task_worker finished.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)