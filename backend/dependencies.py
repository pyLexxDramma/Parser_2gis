from fastapi import Depends
from backend.services.task_queue import TaskQueue
from backend.core.config import Settings

try:
    settings_dep = Settings()
    task_queue_instance = TaskQueue()
except Exception as e:
    print(f"CRITICAL ERROR: Failed to initialize TaskQueue instance in dependencies.py: {e}")
    raise

def get_task_queue() -> TaskQueue:
    logger.debug(f"get_task_queue() called. Returning instance: {task_queue_instance}")
    return task_queue_instance