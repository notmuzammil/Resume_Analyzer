import contextvars
import logging
import logging.handlers
import time
import uuid

from . import config

request_id = contextvars.ContextVar("request_id", default="-")
logger = logging.getLogger("app.http")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def setup_logging() -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
    file_handler = logging.handlers.TimedRotatingFileHandler(
        config.LOG_DIR / "app.log", when="midnight", backupCount=config.LOG_RETENTION_DAYS, encoding="utf-8"
    )
    console_handler = logging.StreamHandler()
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        handler.addFilter(_RequestIdFilter())

    app_logger = logging.getLogger("app")
    app_logger.setLevel(config.LOG_LEVEL)
    app_logger.handlers = [file_handler, console_handler]
    app_logger.propagate = False
    logging.getLogger("uvicorn.error").addHandler(file_handler)


class RequestLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        rid = uuid.uuid4().hex[:8]
        request_id.set(rid)
        start = time.perf_counter()
        status = 500

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [*message.get("headers", []), (b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            logger.exception("Unhandled error on %s %s", scope["method"], scope["path"])
            raise
        finally:
            if scope["path"] != "/api/health":
                logger.info("%s %s -> %s in %.1fs", scope["method"], scope["path"], status, time.perf_counter() - start)
