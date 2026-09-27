import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from app.auth import authenticate_request, clear_principal
from app.auth import router as auth_router
from app.organization import router as organization_router
from app.outbound import router as outbound_router
from app.receipts import organization_router as organization_receipts_router
from app.receipts import router as receipts_router
from app.spending import router as spending_router

app = FastAPI(title="Reimburse API")


@app.middleware("http")
async def authenticated_principal(request: Request, call_next: RequestResponseEndpoint) -> Response:
    token = await authenticate_request(request)
    try:
        return await call_next(request)
    finally:
        clear_principal(token)

_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok")


app.include_router(receipts_router)
app.include_router(auth_router)
app.include_router(organization_receipts_router)
app.include_router(spending_router)
app.include_router(outbound_router)
app.include_router(organization_router)
