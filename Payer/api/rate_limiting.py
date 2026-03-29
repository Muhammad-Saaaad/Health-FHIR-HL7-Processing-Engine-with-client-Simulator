import hashlib
import time
from functools import wraps
from typing import Callable, Any
from fastapi import HTTPException, Request, status

def rate_limit(limit: int, period: int):
    def decorator(func: Callable) -> Callable: # here func is the endpoint function that you will call.
        calls: dict[str, list[float]] = {} # this dictionary will be created for everynew endpoint that i will decode with rate_limit.

        # this is used to preserve the original function's metadata (like its name and d ocstring) when we wrap it with our custom logic.
        # This is important for debugging and documentation purposes, as it allows us to maintain the original function's identity even after it's been decorated.
        @wraps(func) 
        async def wrapper(*args: Any, **kwargs: Any) -> Any: # enforce rate limting and then call the original function
            request = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None or not request.client:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Client information is missing."
                )
            
            # we use hashing so later on we can add more info of the client
            ip_address = request.client.host
            user_id = hashlib.sha256(str(ip_address).encode()).hexdigest()

            # update time of the calls
            current_time = time.time()
            if user_id not in calls:
                calls[user_id] = []

            timestamps = calls[user_id]
            timestamps[:] = [previous_time for previous_time in timestamps if current_time - previous_time < period]

            if len(timestamps) < limit:
                timestamps.append(current_time)
                return await func(*args, **kwargs)
            
            # Calculate the time until the next allowed call
            waiting_time = period - (current_time - timestamps[0])
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {waiting_time:.2f} seconds."
            )
            
        return wrapper
    return decorator