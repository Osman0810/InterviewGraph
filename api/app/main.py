from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.rate_limit import InMemoryRateLimiter


app = FastAPI(title="InterviewGraph API")
rate_limiter = InMemoryRateLimiter(
    limit=settings.api_rate_limit_requests,
    window_seconds=settings.api_rate_limit_window_seconds,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["POST", "GET", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def enforce_rate_limit(request: Request, call_next):
    if request.url.path != "/health":
        client = request.client.host if request.client else "unknown"
        allowed, retry_after = rate_limiter.allow(client)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again shortly."},
                headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def request_validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Invalid request data."})


@app.exception_handler(Exception)
async def unexpected_error(_: Request, __: Exception) -> JSONResponse:
    # Deliberately do not return exception text, stack traces, or request data.
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred."})
app.include_router(api_router)
