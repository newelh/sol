from fastapi import Depends, Request

from app.api.state import AppState
from app.services.file_service import FileService
from app.services.project_service import ProjectService


class ProjectServiceNotInitializedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Project service not initialized")


class FileServiceNotInitializedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("File service not initialized")


def get_app_state(request: Request) -> AppState:
    return request.app.state.state


def get_project_service(state: AppState = Depends(get_app_state)) -> ProjectService:
    if not state.project_service:
        raise ProjectServiceNotInitializedError()
    return state.project_service


def get_file_service(state: AppState = Depends(get_app_state)) -> FileService:
    if not state.file_service:
        raise FileServiceNotInitializedError()
    return state.file_service
