import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import schemas
from .config import get_settings
from .routers import bills, events, people

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(
    title="Bill Splitter",
    version="1.0.0",
    description="Split shared bills. Local-only; no accounts.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(people.router)
app.include_router(events.router)
app.include_router(bills.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):  # pragma: no cover
    logging.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong. Check the API logs for details."},
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config", response_model=schemas.ConfigOut)
def config():
    """Lets the UI tell the user up front whether photo/PDF extraction is
    available, instead of failing at upload time."""
    return schemas.ConfigOut(
        extraction_enabled=settings.extraction_enabled,
        max_upload_mb=settings.max_upload_mb,
        currency=settings.currency,
    )
