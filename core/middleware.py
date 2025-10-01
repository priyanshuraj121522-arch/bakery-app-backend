"""Custom middleware for instrumentation and request logging."""

import logging
import time
from typing import Callable

from django.http import HttpRequest, HttpResponse


class RequestTimingMiddleware:
    """Log basic metadata and duration for every incoming HTTP request."""

    logger = logging.getLogger("bakery.request")

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000

        user = getattr(request, "user", None)
        user_id = getattr(user, "id", None) if user and user.is_authenticated else None

        self.logger.info(
            "%s %s -> %s in %.2fms user=%s",
            request.method,
            request.get_full_path(),
            getattr(response, "status_code", "-"),
            duration_ms,
            user_id if user_id is not None else "-",
            extra={
                "method": request.method,
                "path": request.get_full_path(),
                "status_code": getattr(response, "status_code", None),
                "duration_ms": duration_ms,
                "user_id": user_id,
            },
        )
        return response
