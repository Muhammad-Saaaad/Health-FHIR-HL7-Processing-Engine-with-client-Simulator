## Summary of Lock Types

**Scenario**  |	**Lock to Use** 	| **Benefit**

Async Routes (async def) |	asyncio.Lock |	Non-blocking;
yields control to the event loop.

Sync Routes (def) |	threading.Lock |	Blocks the specific thread but is safe for thread pools.

Multiple Workers/Servers |	Redis or DB Lock  |	Works across different processes and machines.

---

**1. Single-Process Locking (asyncio.Lock)**

```
import asyncio
from fastapi import FastAPI

app = FastAPI()
# Initialize the lock globally
data_lock = asyncio.Lock()

@app.post("/update-data")
async def update_data():
    async with data_lock:
        # Critical section: only one request can be here at a time
        await asyncio.sleep(1)  # Simulate I/O or processing
        return {"message": "Data updated safely"}

```

**2. Synchronous Locking (threading.Lock)**

```
import threading
from fastapi import FastAPI

app = FastAPI()
lock = threading.Lock()

@app.get("/sync-task")
def sync_task():
    with lock:
        # Thread-safe operations here
        return {"status": "success"}
```

**3. Using Distributed Locks for Multiple Workers**

* Set up Redis: Ensure a Redis server is running and install the necessary Python library (e.g., redis or redis-asyncio).

* Implement Redis lock logic:

```
import redis.asyncio as redis
import uuid
from fastapi import FastAPI, HTTPException

# Configure Redis client
# Replace with your Redis connection details
REDIS_HOST = "localhost"
REDIS_PORT = 6379
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

app = FastAPI()
LOCK_KEY = "my_distributed_lock"

@app.post("/update-resource-distributed")
async def update_resource_distributed():
    # Use a unique value to identify the lock owner
    lock_value = str(uuid.uuid4())
    # Try to acquire the lock with a timeout (e.g., 30 seconds)
    lock_acquired = await redis_client.set(LOCK_KEY, lock_value, nx=True, ex=30)

    if not lock_acquired:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Resource is currently locked by another process. Please try again later."
        )

    try:
        # Critical section: perform data updates, etc.
        # Ensure all operations here are atomic and handle potential failures
        await asyncio.sleep(0.5) # Simulate work
        return {"message": "Resource updated with distributed lock"}

    finally:
        # Release the lock if held by the current request
        # A simple check ensures we only delete the lock if our value is present
        if await redis_client.get(LOCK_KEY) == lock_value:
            await redis_client.delete(LOCK_KEY)

```