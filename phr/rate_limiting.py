from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    response = _rate_limit_exceeded_handler(request, exc)
    retry_after = response.headers.get("Retry-After", "0")
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": f"Rate limit exceeded. Retry After {float(retry_after)} seconds.",
        },
        headers={"Retry-After": retry_after},
    )

limiter = Limiter(key_func=get_remote_address, headers_enabled=True)