import asyncio
import uuid
from typing import Dict, Any, List

from backend.schemas.schemas import CompanySearchRequest

class TaskQueue:
    def __init__(self):
        self._queue: asyncio.Queue[CompanySearchRequest] = asyncio.Queue()
        self._tasks: Dict[uuid.UUID, CompanySearchRequest] = {}

    async def put_task(self, task_data: CompanySearchRequest):
        await self._queue.put(task_data)
        self._tasks[task_data.report_id] = task_data
        print(f"Task {task_data.report_id} added to queue.")

    async def get_task(self) -> CompanySearchRequest:
        task = await self._queue.get()
        print(f"Task {task.report_id} retrieved from queue.")
        return task

    def task_done(self):
        self._queue.task_done()
        print("Task marked as done.")

    def get_task_status(self, report_id: uuid.UUID) -> Dict[str, Any]:
        if report_id in self._tasks:
            return {"status": "processing", "task_data": self._tasks[report_id].model_dump()}
        return {"status": "not_found"}
