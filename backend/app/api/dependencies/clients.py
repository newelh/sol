from fastapi import Depends, Request

from app.api.state import AppState
from app.core.clients.postgres import PostgresClient
from app.core.clients.s3 import S3Client
from app.core.clients.valkey import ValkeyClient


class PostgresClientNotInitializedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("PostgreSQL client not initialized")


class S3ClientNotInitializedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("S3 client not initialized")


class ValkeyClientNotInitializedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Valkey client not initialized")


def get_app_state(request: Request) -> AppState:
    return request.app.state.state


def get_postgres_client(state: AppState = Depends(get_app_state)) -> PostgresClient:
    if not state.postgres:
        raise PostgresClientNotInitializedError()
    return state.postgres


def get_s3_client(state: AppState = Depends(get_app_state)) -> S3Client:
    if not state.s3:
        raise S3ClientNotInitializedError()
    return state.s3


def get_valkey_client(state: AppState = Depends(get_app_state)) -> ValkeyClient:
    if not state.valkey:
        raise ValkeyClientNotInitializedError()
    return state.valkey
