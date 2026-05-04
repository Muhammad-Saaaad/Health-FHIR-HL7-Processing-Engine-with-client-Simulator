import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import session_local
from models import Logs


class DBHandler(logging.Handler):

    def emit(self, record: logging.LogRecord):
        try:
            status = "Fail" if record.levelno in (logging.ERROR, logging.CRITICAL) else "Success"

            src_message  = getattr(record, "src_message",  None)
            dest_message = getattr(record, "dest_message", None)
            op_heading   = getattr(record, "op_heading",   record.name)

            db: Session = session_local()
            try:
                db.add(Logs(
                    datetime          = datetime.now(timezone.utc),
                    status            = status,
                    operation_heading = op_heading,
                    operation_message = self.format(record),
                    src_message       = src_message,
                    dest_message      = dest_message,
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"Failed to log to DB: {e}")
            pass


def attach_db_handler(logger: logging.Logger) -> None:
    """Call this once on any existing logger to add DB logging to it."""
    for handler in logger.handlers:
        if isinstance(handler, DBHandler):
            return  # already attached, skip
    logger.addHandler(DBHandler())