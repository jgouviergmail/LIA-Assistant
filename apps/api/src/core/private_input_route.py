"""Private browser submissions never reflect body validation inputs or cache responses."""

from collections.abc import Callable, Coroutine
from contextlib import suppress

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from src.core.exceptions import BaseAPIException


class PrivateApplicationInputRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[None, None, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await original(request)
            except RequestValidationError:
                # Count the failure without using private input or arbitrary body keys as labels.
                with suppress(Exception):
                    from src.infrastructure.observability.metrics_errors import (
                        validation_errors_total,
                    )

                    validation_errors_total.labels(
                        field="private_input", error_type="value_error"
                    ).inc()
                response = JSONResponse(
                    status_code=422, content={"detail": {"error_code": "INVALID_INPUT"}}
                )
            except BaseAPIException as error:
                error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
                raise
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            return response

        return handle
