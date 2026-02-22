# `asyncio` and `Future` — How They Work

---

## Part 1 — `asyncio`

### What is it?

`asyncio` is Python's built-in library for writing **concurrent code** using `async`/`await`.
It runs in a **single thread** but switches between tasks whenever one is waiting (for I/O, a
timer, a network call, etc.).  
The brain of `asyncio` is the **Event Loop**.

---

### The Event Loop

Think of the event loop as a traffic controller sitting in an infinite loop:

```
while True:
    look at all the tasks
    pick the one that is ready to run
    run it until it hits an "await"  ← task yields control back
    go back to top
```

```python
import asyncio

async def task_a():
    print("A: start")
    await asyncio.sleep(1)   # ← yields control, event loop picks another task
    print("A: done")

async def task_b():
    print("B: start")
    await asyncio.sleep(0.5)
    print("B: done")

async def main():
    await asyncio.gather(task_a(), task_b())

asyncio.run(main())
# Output:
# A: start
# B: start        ← B started while A was sleeping
# B: done
# A: done
```

**Key rule:** `async` functions only run when you `await` them. Just calling `task_a()` does
nothing — it creates a *coroutine object*. You must `await` it or schedule it as a `Task`.

---

### `asyncio.create_task()`

Schedules a coroutine to run **concurrently** — it starts immediately in the background
without you having to wait for it.

```python
async def main():
    task = asyncio.create_task(task_a())  # starts running now in background
    print("I can do other things here")
    await task  # wait for it to finish when I need the result
```

In the Interface Engine, this is exactly how `route_manager` starts workers:

```python
task = asyncio.create_task(route_worker(route))
active_route_listners[route.route_id] = task
```

---

### `asyncio.Queue`

A thread-safe queue designed for async code. Used to pass data between coroutines
without them having to know about each other.

```python
queue = asyncio.Queue()

async def producer():
    await queue.put("some data")  # puts item in, never blocks (unbounded queue)

async def consumer():
    item = await queue.get()      # blocks HERE until something is in the queue
    print(item)
```

**In the Interface Engine:**
- `ingest()` is the **producer** — puts `(data, future)` into `route_queue[route_id]`
- `route_worker()` is the **consumer** — loops forever with `await queue.get()`

```
ingest()           route_queue[id]        route_worker()
   │                     │                      │
   │── put(data, fut) ──►│                      │
   │                     │◄─── get() awaits ────│
   │                     │──── (data,fut) ──────►│
   │                     │                      │  (transforms + sends)
   │◄── await future ────┼──────────────────────│  fut.set_result(True)
   │   (blocks here)     │                      │
   │    result = True    │                      │
   │                     │                      │
```

---

### `asyncio.gather()`

Runs multiple awaitables **concurrently** and waits for all of them.

```python
results = await asyncio.gather(coroutine_1(), coroutine_2(), coroutine_3())
```

Returns a list of results in the same order. If one raises an exception, it propagates.

---

### `asyncio.sleep(n)`

Pauses a coroutine for `n` seconds WITHOUT blocking the event loop. Other tasks keep running.
This is completely different from `time.sleep(n)` which blocks the entire thread.

```python
await asyncio.sleep(5)  # ✅ other tasks run during these 5 seconds
time.sleep(5)           # ❌ NOTHING runs for 5 seconds
```

---

## Part 2 — `Future`

### What is a `Future`?

A `Future` is a **placeholder for a result that doesn't exist yet**.

It represents the answer to the question: *"Will you tell me the result when you have it?"*

```
Future states:

  [PENDING]  →  set_result(value)   →  [DONE ✅]
  [PENDING]  →  set_exception(err)  →  [DONE ❌]
```

---

### Creating and Using a Future

```python
import asyncio

async def resolver(future):
    await asyncio.sleep(2)          # simulate work
    future.set_result("done!")      # signal that work is complete

async def main():
    loop = asyncio.get_event_loop()
    future = loop.create_future()   # create an empty placeholder

    asyncio.create_task(resolver(future))  # start work in background

    result = await future           # WAIT HERE until resolver calls set_result()
    print(result)                   # "done!"

asyncio.run(main())
```

The caller (`main`) and the worker (`resolver`) don't call each other — the `Future` is how
they communicate the result.

---

### Key Methods

| Method | What it does |
|--------|--------------|
| `future.set_result(value)` | Marks future as done with a value. Any `await future` unblocks. |
| `future.set_exception(exc)` | Marks future as failed. `await future` raises the exception. |
| `future.done()` | Returns `True` if result or exception has been set. |
| `await future` | Suspends current coroutine until the future is resolved. |

---

### Difference Between `Future` and `Task`

| | `Future` | `Task` |
|-|----------|--------|
| What it wraps | Nothing — you set result manually | A coroutine |
| How result is set | You call `set_result()` | Set automatically when coroutine returns |
| Use case | Cross-coroutine signalling | Running a coroutine in background |

```python
# Task — wraps a coroutine, result set automatically
task = asyncio.create_task(some_coroutine())
result = await task   # result = return value of some_coroutine()

# Future — raw placeholder, you set it yourself
future = loop.create_future()
future.set_result(42)
result = await future  # result = 42
```

`Task` is actually a subclass of `Future`.

---

## Part 3 — How Both Are Used Together in This Engine

In `main.py`, `Future` and `asyncio.Queue` are combined to turn the async queue pattern
into a **request-reply** pattern:

### Step-by-step

```python
# ingest() — the sender
loop = asyncio.get_event_loop()
future = loop.create_future()           # 1. create empty promise

await route_queue[route_id].put(        # 2. send data AND the promise together
    (src_path_to_value, future)
)

await future                            # 3. BLOCK here — waiting for route_worker
                                        #    to resolve the promise
```

```python
# route_worker() — the receiver
src_path_to_value, result_future = await route_queue[route_id].get()  # 4. pick up both

# ... do transformation work ...

response = await client.post(url, json=msg)     # 5. deliver to Payer/LIS
if response.status_code in (200, 201):
    result_future.set_result(True)              # 6a. resolve promise ✅ → ingest() unblocks
else:
    result_future.set_exception(Exception(...)) # 6b. reject promise ❌ → ingest() raises
```

### Why this matters

Without the `Future`:
```
EHR → Engine (returns 200 immediately) → EHR commits patient ✅
                         ↓ (async, nobody waiting)
                      route_worker → Payer FAILS ❌  (EHR never knows)
```

With the `Future`:
```
EHR → Engine (awaits future) ─────────────────────────────────────────┐
                                route_worker → Payer FAILS ❌          │
                                future.set_exception() ────────────────┘
                         Engine returns 502 Bad Gateway
EHR receives 502 → raises → db.rollback() → patient NOT saved ✅
```

---

## Quick Reference

```python
import asyncio

# Run the event loop
asyncio.run(main())

# Define an async function
async def my_func():
    ...

# Await a coroutine (run it, wait for result)
result = await my_func()

# Run coroutine as background task (don't wait)
task = asyncio.create_task(my_func())

# Wait for multiple things concurrently
results = await asyncio.gather(coro1(), coro2())

# Sleep without blocking other tasks
await asyncio.sleep(5)

# Queue — pass data between coroutines
q = asyncio.Queue()
await q.put(item)
item = await q.get()

# Future — manual result placeholder
loop = asyncio.get_event_loop()
fut = loop.create_future()
fut.set_result(value)       # from one coroutine
result = await fut          # from another coroutine
```
