from typing import Annotated

from fastapi import APIRouter, Depends, Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.api.state import AppState

router = APIRouter()


def get_app_state(request: Request) -> AppState:
    """Get the application state from the request."""
    return request.app.state.state


@router.get("/")
async def metrics(
    request: Request, state: Annotated[AppState, Depends(get_app_state)]
) -> Response:
    """
    Metrics endpoint that returns Prometheus metrics.
    """
    # In a production environment, we would add more metrics here
    # For now, we just return the default Prometheus metrics
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
