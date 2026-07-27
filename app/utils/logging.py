import logging

from app.observability.events import peek_run_id

# Every log line carries the current request/run id (see
# app.observability.events for the contextvar it's stashed in, and
# app.main.RequestIdMiddleware for where it's set per-request) -- ROADMAP.md
# Phase 1, Step 1.1. `-` when no request/run is in flight (e.g. a script
# calling into a service module directly) rather than minting one here:
# ordinary log lines must never silently mint run ids that never appear in
# any RunEvent.
_REQUEST_ID_PLACEHOLDER = "-"


class _RequestIdFilter(logging.Filter):
    """Stamps every record reaching the handler with `request_id`.

    Attached to the *handler* (not individual loggers) in `get_logger`
    below so it also covers records from loggers this module never touched
    directly (e.g. third-party libraries propagating to the root logger)
    -- the format string below references `%(request_id)s` unconditionally,
    so every record reaching that handler must have the attribute or
    logging itself would raise while formatting.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = peek_run_id() or _REQUEST_ID_PLACEHOLDER
        return True


_root_configured = False
_filtered_logger_names: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    global _root_configured
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s",
    )
    if not _root_configured:
        for handler in logging.getLogger().handlers:
            handler.addFilter(_RequestIdFilter())
        _root_configured = True

    logger = logging.getLogger(name)
    if name not in _filtered_logger_names:
        # Belt-and-suspenders: a logger-level filter runs before ANY
        # handler sees the record (including handlers this module never
        # touched, e.g. pytest's `caplog`), whereas the handler-level
        # filter above only covers basicConfig's own handler. Stamping at
        # both layers means `request_id` is present regardless of which
        # handler ultimately processes a given record.
        logger.addFilter(_RequestIdFilter())
        _filtered_logger_names.add(name)
    return logger
