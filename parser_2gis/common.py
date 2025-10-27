import time
import functools
from typing import Callable, Any



def wait_until_finished(timeout: float = 60, throw_exception: bool = True):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    return func(*args, **kwargs)
                except Exception:
                    time.sleep(0.5)

            if throw_exception:
                raise TimeoutError(f"Function {func.__name__} did not complete within {timeout} seconds.")
            return None

        return wrapper

    return decorator



def floor_to_hundreds(x: int) -> int:
    return (x // 100) * 100