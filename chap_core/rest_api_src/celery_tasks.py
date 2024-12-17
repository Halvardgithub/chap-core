import os
from pathlib import Path
from typing import Callable, Generic
import logging
from celery import Celery, shared_task, Task
from celery.result import AsyncResult
from dotenv import find_dotenv, load_dotenv

import celery

from ..worker.interface import ReturnType
from celery.utils.log import get_task_logger
#logger = logging.getLogger(__name__)

# We use get_task_logger to ensure we get the Celery-friendly logger
# but you could also just use logging.getLogger(__name__) if you prefer.
logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)

class TaskWithPerTaskLogging(Task):
    def __call__(self, *args, **kwargs):
        print("TaskWithPerTaskLogging")
        # Extract the current task id
        task_id = self.request.id
        
        # Create a file handler for this task's logs
        file_handler = logging.FileHandler(Path("logs") / f"task_{task_id}.txt")
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        
        # Remember old handlers so we can restore them later
        old_handlers = logger.handlers[:]
        
        # also add this handler to the root-logger, so that logging done by other packages is also logged
        root_logger = logging.getLogger()
        old_root_handlers = root_logger.handlers[:]
        root_logger.addHandler(file_handler)
        
        # Replace the logger handlers with our per-task file handler
        logger.handlers = [file_handler]
        # also add stdout handler
        logger.addHandler(logging.StreamHandler())
        
        try:
            # Execute the actual task
            return super(TaskWithPerTaskLogging, self).__call__(*args, **kwargs)
        finally:
            # Close the file handler and restore old handlers after the task is done
            file_handler.close()
            logger.handlers = old_handlers
            root_logger.handlers = old_root_handlers



@shared_task(name='celery.ping')
def ping():
    return 'pong'

def read_environment_variables():
    load_dotenv(find_dotenv())
    host = os.getenv("CELERY_BROKER", "redis://localhost:6379")
    return host

url = read_environment_variables()
logger.info(f"Connecting to {url}")
app = Celery(
    "worker",
    broker=url,
    backend=url
)
app.conf.update(
    task_serializer="pickle",
    accept_content=["pickle"],  # Allow pickle serialization
    result_serializer="pickle",
)

# predict_pipeline_from_health_data = celery.task(predict_pipeline_from_health_data)
# celery = Celery(
#     "worker",
#     broker="redis://redis:6379",
#     backend="redis://redis:6379"
# )
# celery.conf.update(
#     task_serializer="pickle",
#     accept_content=["pickle"],  # Allow pickle serialization
#     result_serializer="pickle",
# )

def add_numbers(a: int, b: int):
    logger.info(f"Adding {a} + {b}")
    return a + b


#add_numbers = celery.task()(_add_numbers)
#predict_pipeline_from_health_data = celery.task(predict_pipeline_from_health_data)
#evaluate = celery.task(evaluate)


class CeleryJob(Generic[ReturnType]):
    """Wrapper for a Celery Job"""

    def __init__(self, job: celery.Task, app: Celery):
        self._job = job
        self._app = app

    @property
    def _result(self)-> AsyncResult:
        return AsyncResult(self._job.id, app=self._app)

    @property
    def status(self) -> str:
        return self._result.state

    @property
    def result(self) -> ReturnType:
        return self._result.result

    @property
    def progress(self) -> float:
        return 0

    def cancel(self):
        self._result.revoke()

    @property
    def id(self):
        return self._job.id

    @property
    def is_finished(self) -> bool:
        return self._result.state in ("SUCCESS", "FAILURE")

    @property
    def exception_info(self) -> str:
        return str(self._result.traceback or "")

    def get_logs(self) -> str:
        log_file = Path("logs") / f"task_{self._job.id}.txt"
        if log_file.exists():
            return log_file.read_text()
        return None


# set base to TaskWithPerTaskLogging to enable per-task logging
@app.task(base=TaskWithPerTaskLogging)
def celery_run(func, *args, **kwargs):
    return func(*args, **kwargs)



class CeleryPool(Generic[ReturnType]):
    """Simple abstraction for a Celery Worker"""

    def __init__(self, celery: Celery = None):
        assert celery is None
        self._celery = app

    def queue(self, func: Callable[..., ReturnType], *args, **kwargs) -> CeleryJob[ReturnType]:
        #task = predict_pipeline_from_health_data if func.__name__ == "predict_pipeline_from_health_data" else celery.task()(func)
        #task = task.delay(*args, **kwargs)

        job = celery_run.delay(func, *args, **kwargs)
        return CeleryJob(job, app=self._celery)

    def get_job(self, task_id: str) -> CeleryJob[ReturnType]:
        return CeleryJob(AsyncResult(task_id, app=self._celery), app=self._celery)

    def list_jobs(self):
        active = self._celery.control.inspect().active()
        scheduled = self._celery.control.inspect().scheduled()
        reserved = self._celery.control.inspect().reserved()
        return {
            "active": active or [],
            "scheduled": scheduled or [],
            "reserved": reserved or [],
        }