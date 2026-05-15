import logging
from queue import Queue
from threading import Thread
from datetime import datetime
from database import session_local
from models import Logs


_log_queue: Queue[dict] = Queue()
_worker_started = False


def _db_log_worker():
    while True:
        payload = _log_queue.get()
        try:
            db = session_local()
            try:
                db.add(Logs(**payload))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"Failed to log to DB: {e}")
        finally:
            _log_queue.task_done()


def _ensure_worker_started():
    global _worker_started
    if _worker_started:
        return
    worker = Thread(target=_db_log_worker, daemon=True)
    worker.start()
    _worker_started = True


class DBHandler(logging.Handler):

    def __init__(self):
        super().__init__()
        _ensure_worker_started()

    def emit(self, record: logging.LogRecord):
        try:
            status = "Fail" if record.levelno in (logging.ERROR, logging.CRITICAL) else "Success"

            src_message  = getattr(record, "src_message",  None)
            dest_message = getattr(record, "dest_message", None)
            op_heading   = getattr(record, "op_heading",   record.name)

            _log_queue.put({
                "datetime": datetime.now(),
                "status": status,
                "operation_heading": op_heading,
                "operation_message": self.format(record),
                "src_message": src_message,
                "dest_message": dest_message,
            })
        except Exception as e:
            print(f"Failed to log to DB: {e}")


def attach_db_handler(logger: logging.Logger) -> None:
    """Call this once on any existing logger to add DB logging to it."""
    for handler in logger.handlers:
        if isinstance(handler, DBHandler):
            return  # already attached, skip
    logger.addHandler(DBHandler())
