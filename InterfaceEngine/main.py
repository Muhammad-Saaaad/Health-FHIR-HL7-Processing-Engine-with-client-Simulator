import asyncio
from collections import Counter
from datetime import datetime
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import time
from uuid import uuid4

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, status, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SAWarning
import warnings

from api import route, endpoint, server, logs, user
import db_logger as db_logging
from database import engine, session_local
import models
from rate_limiting import limiter, rate_limit_exceeded_handler
from validation.transformation import fill_duplicate_missing_values, regex_replace_with_template, increment_segment, set_null_if_not_available
from validation.fhir_validation import validate_unknown_fhir_resource, get_fhir_value_by_path, fhir_extract_paths
from validation.fhir_validation import build_fhir_message
from validation.hl7_validation import get_hl7_value_by_path, hl7_extract_paths
from validation.hl7_validation import build_hl7_message

warnings.filterwarnings("ignore", category=SAWarning)
os.makedirs("logs", exist_ok=True)
os.makedirs("validation_logs", exist_ok=True)

class HealthRequestFilter(logging.Filter):
    """
    Split noisy HTTP health-check request logs away from the main log.
    """
    def __init__(self, only_health: bool):
        super().__init__()
        self.only_health = only_health

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        is_health_request = "HTTP Request:" in message and "/health" in message
        return is_health_request if self.only_health else not is_health_request

class MidnightSingleFileHandler(TimedRotatingFileHandler):
    """
    A TimedRotatingFileHandler variant that clears the same file at midnight.
    This keeps exactly one log file on disk.
    """
    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None

        # Reopen in write mode to wipe previous day's logs.
        self.mode = "w"
        self.stream = self._open()
        self.mode = "a"

        current_time = int(time.time())
        self.rolloverAt = self.computeRollover(current_time)


logger = logging.getLogger("interface_engine.main")
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.propagate = False

logger_mapping = logging.getLogger("interface_engine.mapping")
logger_mapping.setLevel(logging.INFO)
logger_mapping.handlers.clear() 
logger_mapping.propagate = False

_LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "7"))

main_log_handler = MidnightSingleFileHandler(
    filename=r"logs/main.log",
    when="midnight",
    interval=1,
    backupCount=_LOG_BACKUP_COUNT,
    encoding="utf-8",
)
main_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"))
main_log_handler.addFilter(HealthRequestFilter(only_health=False))

main_log_handler_mapping = MidnightSingleFileHandler(
    filename=r"logs/main_mapping.log",
    when="midnight",
    interval=1,
    backupCount=_LOG_BACKUP_COUNT,
    encoding="utf-8",
)
main_log_handler_mapping.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"))
main_log_handler_mapping.addFilter(HealthRequestFilter(only_health=False))

health_log_handler = MidnightSingleFileHandler(
    filename=r"logs/health_checks.log",
    when="midnight",
    interval=1,
    backupCount=_LOG_BACKUP_COUNT,
    encoding="utf-8",
)
health_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"))
health_log_handler.addFilter(HealthRequestFilter(only_health=True))

logger.addHandler(main_log_handler)
logger.addHandler(health_log_handler)

logger_mapping.addHandler(main_log_handler_mapping)

@asynccontextmanager # handle lifespan events like startup or shutdown
async def lifeSpan(app: FastAPI):
    app.state.server_health_task = asyncio.create_task(server.server_health())
    app.state.connected_systems_task = asyncio.create_task(server.get_lis_payer())
    app.state.route_manager_task = asyncio.create_task(route_manager())
    app.state.redelivery_watcher_task = asyncio.create_task(redelivery_watcher())

    yield

    shutdown_tasks = [
        app.state.server_health_task,
        app.state.connected_systems_task,
        app.state.route_manager_task,
        app.state.redelivery_watcher_task,
    ]
    for task in shutdown_tasks:
        task.cancel()
    await asyncio.gather(*shutdown_tasks, return_exceptions=True)
    return

app = FastAPI(title="Interface Engine", lifespan=lifeSpan)
app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],
    allow_credentials= False,
    allow_headers=["*"],
    allow_methods=["*"]
)
models.Base.metadata.create_all(bind=engine)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(server.router, prefix="/server")
app.include_router(route.router, prefix="/route")
app.include_router(endpoint.router, prefix="/endpoint")
app.include_router(logs.router, prefix="/logs")
app.include_router(user.router, prefix="/user")

db_logger = logging.getLogger("interface_engine.db_logger")
db_logger.setLevel(logging.INFO)
db_logger.handlers.clear()
db_logger.propagate = False
db_logger.addHandler(db_logging.DBHandler())

@app.get("/")
def check_health():
    """
    Health-check endpoint for InterfaceEngine.

    **Response (200 OK):**
    - JSON object: `{ "message": "✔ Interface Engine running" }`
    """
    return {"message": "✔ Interface Engine running"}

active_route_listners = {} # consist of all the running routes|Channels lisning for a soruce endpoint
route_queue = {} # consist of each route key with that route value that it gets from source endpoint
destination_semaphores = {}
# Park-and-resume buffer: dest_server_id -> list of (route_id, route_name, (src_paths, simple_paths, src_msg))
# Messages that couldn't be delivered because the destination is Inactive are parked here
# and re-enqueued by redelivery_watcher() once the destination becomes Active again.
pending_redelivery: dict[int, list] = {}

_BATCH_CONCURRENCY = int(os.getenv("BATCH_CONCURRENCY", "25"))
_ROUTE_WORKER_CONCURRENCY = int(os.getenv("ROUTE_WORKER_CONCURRENCY", "15"))
_DESTINATION_CONCURRENCY = int(os.getenv("DESTINATION_CONCURRENCY", "3"))
_HTTP_READ_TIMEOUT = float(os.getenv("HTTP_READ_TIMEOUT", "30"))
_INGEST_AWAIT_TIMEOUT = float(os.getenv("INGEST_AWAIT_TIMEOUT", str(_HTTP_READ_TIMEOUT + 10)))
_INACTIVE_DEST_MAX_RETRIES = int(os.getenv("INACTIVE_DEST_MAX_RETRIES", "3"))
_INACTIVE_DEST_BACKOFF_SECS = int(os.getenv("INACTIVE_DEST_BACKOFF_SECS", "20"))
_REDELIVERY_CHECK_INTERVAL = int(os.getenv("REDELIVERY_CHECK_INTERVAL", "15"))

def _payload_preview(data, max_len: int = 400) -> str:
    text = str(data)
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[:max_len] + "..."


def _get_destination_semaphore(dest_server_id: int) -> asyncio.Semaphore:
    if dest_server_id not in destination_semaphores:
        destination_semaphores[dest_server_id] = asyncio.Semaphore(_DESTINATION_CONCURRENCY)
    return destination_semaphores[dest_server_id]

async def route_manager():
    """
        Takes all the routes from database, and use route_worker function, after that the route|channel
        can do everything
    """
    try:
        while True:
            try:

                with session_local() as db:
                    all_routes = db.query(models.Route).all()

                current_route_ids = {r.route_id for r in all_routes}

                # Reconcile: cancel workers for routes that were deleted from the DB
                stale_route_ids = set(active_route_listners.keys()) - current_route_ids
                for stale_id in stale_route_ids:
                    logger.info("route %s no longer exists in DB - cancelling its workers", stale_id)
                    for task in active_route_listners.pop(stale_id, []):
                        task.cancel()
                    route_queue.pop(stale_id, None)

                for route in all_routes:
                    if route.route_id not in active_route_listners:

                        route_queue[route.route_id] = asyncio.Queue() # make a async queue for a new route that is not listning
                        tasks = [
                            asyncio.create_task(route_worker(route, worker_number=worker_number))
                            for worker_number in range(1, _ROUTE_WORKER_CONCURRENCY + 1)
                        ]
                        active_route_listners[route.route_id] = tasks
                        logger.info(
                            "route_workers started for route -> %s workers=%s",
                            route.name,
                            _ROUTE_WORKER_CONCURRENCY,
                        )
                await asyncio.sleep(5)

            except asyncio.CancelledError:
                logger.info("Route_manager received Cancellation signal")
                raise # Re-raise to properly exit
            
            except Exception as exp:
                logger.error(f"Error in route_manager: {str(exp)}")
                await asyncio.sleep(5)  # Continue running despite errors
    
    except asyncio.CancelledError:

        logger.info(f"Route Manger shutting down")
        # Cleanup: cancle all route_worker tasks that we run above
        for route_id, tasks in active_route_listners.items():
            for task in tasks:
                task.cancel()
        # wait for all the route_workers to finish
        await asyncio.gather(
            *(task for tasks in active_route_listners.values() for task in tasks),
            return_exceptions=True,
        )

async def redelivery_watcher():
    """
    Background task that periodically checks the `pending_redelivery` buffer and re-enqueues
    parked messages once their destination server becomes Active again.

    Messages land in `pending_redelivery` from `route_worker` when a destination is Inactive
    past `_INACTIVE_DEST_MAX_RETRIES`. Each retried message gets a fresh future; we don't
    await it (best-effort redelivery) and log any failure via a done-callback.
    """
    def _log_redelivery_outcome(route_name: str, fut: asyncio.Future):
        if fut.cancelled():
            logger.warning("redelivery for route '%s' was cancelled", route_name)
            return
        exp = fut.exception()
        if exp is not None:
            logger.error("redelivery for route '%s' failed: %s", route_name, exp)
        else:
            logger.info("redelivery for route '%s' succeeded", route_name)

    try:
        while True:
            await asyncio.sleep(_REDELIVERY_CHECK_INTERVAL)
            if not pending_redelivery:
                continue

            try:
                loop = asyncio.get_running_loop()
                with session_local() as db:
                    for dest_server_id in list(pending_redelivery.keys()):
                        dest_server = db.get(models.Server, dest_server_id)
                        if dest_server is None:
                            dropped = pending_redelivery.pop(dest_server_id, [])
                            logger.error(
                                "dropping %s parked messages — destination server id=%s no longer exists",
                                len(dropped), dest_server_id,
                            )
                            continue
                        if dest_server.status != "Active":
                            continue

                        items = pending_redelivery.pop(dest_server_id, [])
                        logger.info(
                            "redelivering %s parked messages to %s (id=%s)",
                            len(items), dest_server.name, dest_server_id,
                        )
                        for route_id, route_name, parked_payload in items:
                            if route_id not in route_queue:
                                logger.warning(
                                    "cannot redeliver to route '%s' (id=%s) — route_queue missing",
                                    route_name, route_id,
                                )
                                continue
                            src_path_to_value, simple_paths, src_msg = parked_payload
                            new_future = loop.create_future()
                            new_future.add_done_callback(
                                lambda fut, name=route_name: _log_redelivery_outcome(name, fut)
                            )
                            await route_queue[route_id].put(
                                (src_path_to_value, simple_paths, new_future, src_msg)
                            )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("redelivery_watcher iteration failed")
    except asyncio.CancelledError:
        logger.info("redelivery_watcher cancelled — %s destinations still have parked messages", len(pending_redelivery))
        raise

async def route_worker(route, worker_number: int = 1):
    """
        use Route worker to listen incomming data using aysync queue, then it validates, sends data,
        parses data and converts data from fhir <--> hl7.

        The queue items are (src_path_to_value, future) tuples. After delivery the worker
        resolves the future so that ingest() can await the result and respond to the caller
        with a real success/failure status.
    """
    client = None
    try:
        with session_local() as db:
            dest_endpoint = db.get(models.Endpoints, route.dest_endpoint_id)
            dest_server = db.get(models.Server, route.dest_server_id)
            src_server = db.get(models.Server, route.src_server_id)

            src_endpoint_fields = db.query(models.EndpointFields) \
                .filter(models.EndpointFields.endpoint_id == route.src_endpoint_id).all()

            dest_endpoint_fields = db.query(models.EndpointFields) \
                .filter(models.EndpointFields.endpoint_id == route.dest_endpoint_id).all()

            mapping_rules_for_specific_route = db.query(models.MappingRule) \
                .filter(models.MappingRule.route_id == route.route_id).all()

        if dest_endpoint is None or dest_server is None or src_server is None:
            logger.error(
                "route_worker %s aborting — missing FK row(s) for route '%s': dest_endpoint=%s dest_server=%s src_server=%s",
                worker_number, route.name, dest_endpoint, dest_server, src_server,
            )
            return

        # lookup maps 
        """
            Here we take the endpoing field id, and then we give to src_id_to_path to take the path of the src_field.
            then give the src_path to take the value from the src_path_to_value that we get from the ingest function right after the while loop.
            we then do some transformation if needed, and then we take the dest_path from the dest_id_to_path using the dest_field_id, 
            we know have the path, just take the src value and put it against the path and make the message.
        """
        src_id_to_path = {f.endpoint_field_id: f.path for f in src_endpoint_fields} # e.g. path = Patient-identifier[0].value
        dest_id_to_path = {f.endpoint_field_id: f.path for f in dest_endpoint_fields}
        dest_path_to_resource = {f.path: f.resource for f in dest_endpoint_fields} # use resource for making messages.

        logger.info(f"route_worker {worker_number} started for route -> {route.name}")

        dest_endpoint_url = f"http://{dest_server.ip}:{dest_server.port}{dest_endpoint.url}"
        dest_system_id = dest_server.system_id
        client = httpx.AsyncClient(timeout=httpx.Timeout(_HTTP_READ_TIMEOUT, connect=5.0))
        destination_semaphore = _get_destination_semaphore(route.dest_server_id)

        while True:
            # Each queue item is a (data, future) tuple.
            # The future lets ingest() know whether delivery succeeded or failed.
            src_path_to_value, simple_paths, result_future, src_msg = await route_queue[route.route_id].get()
            logger.info(f"route_worker {worker_number} for route -> {route.name} received data: {src_path_to_value}")
            normal_src_paths_counter = [] # this will contain data just the output_data dictionary, but with the src paths instead of dest paths, useful for multiple same segments/sources to extract data from.
            split_src_paths_counter = []
            concat_src_paths_counter = []

            simple_path_counts = Counter(simple_paths) # this will convert list [PID-5.1, PID-5.2, PID-5.1] into Counter({'PID-5.1': 2, 'PID-5.2': 1}). instead of using list.count() that iterate list everytime, you take the counts once.

            output_data = {} # contains the output fields with value
            concat_data = {} # contains single dest field id, and multiple mapping rule that concate multiple src into a single destination.
            split_data = {} # contain single src field id, and multiple mapping rule that split that single src into multiple destination.

            # if dest_server.status == "Inactive" :
            #         logger.error(f"Destination server {dest_server.name} is Inactive")
            #         result_future.set_exception(Exception(err))
            #         continue
            try:
                for rule in mapping_rules_for_specific_route: # rule for each src-to-dest field mapping in the route
                    if rule.transform_type == 'concat': # for concat we should have multiple src and 1 dest
                        # this takes a key and the value, if the key doesn't exists or exists with a different value
                        # it will replace it with []
                        concat_data.setdefault(rule.dest_field_id, []) 
                        # this rule contains the src ids and other metadata that will be use for concatination.
                        concat_data[rule.dest_field_id].append(rule)
                    
                    elif rule.transform_type == 'split': # for split we should have multiple dest and 1 src
                        # here we have a singe src id, that will split into multiple destinations
                        split_data.setdefault(rule.src_field_id, []).append(rule)
                    
                    else: # map | copy | format | regex
                        src_path = src_id_to_path[rule.src_field_id]

                        for _ in range(simple_path_counts[src_path]): # if there is multiple same src paths then we have to do the transformation for that many times, and also have to take care of the counter in the segment name.

                            src_path = await increment_segment(segment_path=src_path, list_data=normal_src_paths_counter) # here PID-5.1 will become PID[1]-5.1, useful when multiple same segments.
                            normal_src_paths_counter.append(src_path) # just to keep the count of the src paths that we have, and to increment the segment if there is multiple same segments.

                            if src_path not in src_path_to_value:
                                logger.warning(f"The src path {src_path} not found in src_path_to_value: {src_path_to_value}")
                                continue
                            value = src_path_to_value[src_path]

                            if rule.transform_type == 'map':
                                # here the first value will give me the map value, if the mapping value is not found then return the default value
                                value = rule.config.get(str(value).lower(), value) 

                            elif rule.transform_type == "regex":
                                value = regex_replace_with_template(value=value, pattern_from=rule.config["from"], pattern_to=rule.config["to"])

                            elif rule.transform_type == 'format':
                                try: # 2004-10-06 → 20041006 vice versa
                                    dt = datetime.strptime(str(value), rule.config["from"])
                                    value = dt.strftime(rule.config["to"])
                                except Exception as exp:
                                    try:
                                        dt = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
                                        value = dt.strftime(rule.config["to"])
                                    except ValueError:
                                        logger.error(f"Error while transformation: {str(exp)}")

                            if rule.dest_field_id not in dest_id_to_path:
                                logger.error(f"""The destination id in rule {rule.dest_field_id}
                                            does not matches with the destination map id {dest_id_to_path}""")
                                continue
                                
                            dest_path = dest_id_to_path[rule.dest_field_id]
                            dest_path = await increment_segment(output_data=output_data, segment_path=dest_path) # here PID-5.1 will become PID[1]-5.1
                            output_data[dest_path] = value
                            logger_mapping.info(f"src_path: {src_path}, dest_path: {dest_path} value: {value}")

                logger.info(f"output data dictionary before & without concat and split transformation for route {route.name} -> {output_data}")
                logger.info(f"concat_data for route {route.name} -> {concat_data}")
                logger.info(f"split_data for route {route.name} -> {split_data}")

                ################################## Concat Data ##################################
                for dest_id , concat_rules in concat_data.items(): 
                    logger_mapping.info(f"Applying concat transformation for dest_id: {dest_id} with rules: {concat_rules}")
                    multiple_src_paths_to_concat: dict[int, list[str]] = dict() # this will contain data like this: {1: [PID-5.1, PID[1]-5.1], 2: [PID-5.2, PID[1]-5.2]} this is useful when we have multiple same src paths to concatinate, and also to take care of the counter in the segment name.
                    
                    delimiter = " "
                    for concat_rule in concat_rules:
                        delimiter = concat_rule.config.get('delimiter', " ") # concat on delimiter or by default with space " "

                        src_path = src_id_to_path[concat_rule.src_field_id]
                        for i in range(simple_path_counts[src_path]): # if there is multiple same src paths then we have to do the transformation for that many times, and also have to take care of the counter in the segment name.
                            
                            current_src_path = await increment_segment(segment_path=src_path, list_data=concat_src_paths_counter)
                            concat_src_paths_counter.append(current_src_path)

                            if current_src_path in src_path_to_value:

                                if i not in multiple_src_paths_to_concat:
                                    multiple_src_paths_to_concat[i] = []
                                multiple_src_paths_to_concat[i].append(str(src_path_to_value[current_src_path]))

                            else:
                                logger.warning(f"while Concatnation, The src_path '{current_src_path}' not found in path data: '{src_path_to_value}'")
                                continue
                                        
                    for idx in multiple_src_paths_to_concat.keys(): # here we are taking the values of the same src paths with the same counter and concatinate them.
                        concated_value = delimiter.join(multiple_src_paths_to_concat[idx])

                        dest_path = dest_id_to_path[dest_id]
                        dest_path = await increment_segment(output_data=output_data, segment_path=dest_path)
                        output_data[dest_path] = concated_value
                        logger.info(f"Concated value for dest_path {dest_path} is {concated_value}")
                
                #################################### Split Data ####################################
                for src_id, split_rules in split_data.items():
                    logger_mapping.info(f"Applying split transformation for src_id: {src_id} with split_rules: {split_rules}")

                    for _ in range(simple_path_counts[src_id_to_path[src_id]]): # if there is multiple same src paths then we have to do the transformation for that many times, and also have to take care of the counter in the segment name.
                        src_path = src_id_to_path[src_id]
                        src_path = await increment_segment(segment_path=src_path, list_data=split_src_paths_counter)
                        split_src_paths_counter.append(src_path)
                        
                        if src_path not in src_path_to_value:
                            logger.warning(f"while Spliting, The src_path {src_path} not found in path data: {src_path_to_value}")
                            continue
                        
                        # As split_rules 
                        delimiter= split_rules[0].config.get('delimiter', ' ') # concat on delimiter or by default with space " " 
                        parts = str(src_path_to_value[src_path]).split(delimiter)

                        last_dest_path = None
                        for i, split_rule in enumerate(split_rules):
                            if i < len(parts):

                                dest_path = dest_id_to_path[split_rule.dest_field_id]
                                dest_path = await increment_segment(output_data=output_data, segment_path=dest_path)
                                output_data[dest_path] = parts[i]
                                last_dest_path = dest_path
                        
                        if len(parts) > len(split_rules) and last_dest_path: # here if the while spliting, if there is some data left concatenate it with the last path
                            logger.info(f"destination path for remaining data ---> {last_dest_path}")
                            output_data[last_dest_path] += " " + (' ').join(parts[len(split_rules):]) # join all the remaining parts with the remining data
                        elif last_dest_path is None:
                            logger.warning(f"while Splitting, last_dest_path is None: {last_dest_path}, means no split data is mapped to any destination")

                output_data = fill_duplicate_missing_values(output_data)
            except Exception as exp:
                logger.exception(f"{exp} -> This came when processing data for route -> '{route.name}'")
                if not result_future.done():
                    result_future.set_exception(exp)
                # Skip the delivery block below and pick up the next queue item.
                continue

            try:
                # BUILD MESSAGE
                output_data = await set_null_if_not_available(output_data, dest_path_to_resource) # set the data to null if data if not available.
                logger.info(f"Output for route -> {route.name}: {output_data}")

                if dest_server.protocol == "FHIR":
                    logger_mapping.info(f"Building FHIR message for route -> {route.name} with output_data: {output_data} and dest_path_to_resource: {dest_path_to_resource}")
                    msg = await build_fhir_message(output_data, dest_path_to_resource) # make a fhir message with the data

                else:
                    logger_mapping.info(f"Building HL7 message for route -> {route.name} with output_data: {output_data}")
                    msg = await build_hl7_message(output_data=output_data, src=src_server.name,
                                                   dest=dest_server.name, msg_type=route.msg_type)
                logger.info(f"Built message for route -> {route.name}:\n {msg}")

                # DELIVER — resolve the future so ingest() knows the result
                if client:
                    with session_local() as db:
                        dest_server = db.get(models.Server, route.dest_server_id)

                    retries = 0
                    while dest_server is not None and dest_server.status == "Inactive" and retries < _INACTIVE_DEST_MAX_RETRIES:
                        logger.warning(
                            "Destination server %s is Inactive; retry %s/%s after %ss",
                            dest_server.name, retries + 1, _INACTIVE_DEST_MAX_RETRIES, _INACTIVE_DEST_BACKOFF_SECS,
                        )
                        await asyncio.sleep(_INACTIVE_DEST_BACKOFF_SECS)
                        retries += 1
                        with session_local() as db:
                            dest_server = db.get(models.Server, route.dest_server_id)

                    if dest_server is None:
                        err = f"Destination server (id={route.dest_server_id}) no longer exists in DB"
                        logger.error(err)
                        if not result_future.done():
                            result_future.set_exception(Exception(err))
                        continue

                    if dest_server.status == "Inactive":
                        # Park the message so redelivery_watcher() can replay it once the destination comes back.
                        parked_payload = (src_path_to_value, simple_paths, src_msg)
                        pending_redelivery.setdefault(route.dest_server_id, []).append(
                            (route.route_id, route.name, parked_payload)
                        )
                        parked_count = len(pending_redelivery[route.dest_server_id])
                        logger.warning(
                            "Parked message for route '%s' (dest=%s) — queued_for_retry=%s",
                            route.name, dest_server.name, parked_count,
                        )
                        db_logger.warning(
                            f"Destination {dest_server.name} inactive — message parked for retry",
                            extra={
                                "src_message": json.dumps(src_msg) if isinstance(src_msg, (dict, list)) else str(src_msg),
                                "dest_message": "(not built — parked before delivery)",
                                "op_heading": f"Channel: {route.name}",
                            },
                        )
                        if not result_future.done():
                            result_future.set_result({
                                "status": "queued_for_retry",
                                "destination": dest_server.name,
                                "parked_count": parked_count,
                            })
                        continue

                    request_headers = {}
                    if dest_system_id is not None:
                        request_headers["System-Id"] = str(dest_system_id)
                        request_headers["Src-System-Id"] = str(src_server.system_id)
                        request_headers["Src-System-Name"] = str(src_server.name)

                    async with destination_semaphore:
                        logger.info(f"Sending data to url: {dest_endpoint_url}")
                        if dest_server.protocol == "FHIR":
                            response = await client.post(url=dest_endpoint_url, json=msg, headers=request_headers)
                        else:
                        # HL7 is plain text — do NOT json= encode it or it arrives as a
                        # JSON string "MSH|..." instead of the raw HL7 text
                            request_headers["Content-Type"] = "text/plain"
                            response = await client.post(
                                url=dest_endpoint_url,
                                content=msg,
                                headers=request_headers
                            )
                    if response.status_code in (200, 201, 202, 203, 204):
                        db_logger.info(f"Data Sucessfully Send to : {dest_server.name}",
                                    extra= {
                                            "src_message": json.dumps(src_msg),
                                            "dest_message": json.dumps(msg),
                                            "op_heading": f"Channel: {route.name}"
                                        }
                        )
                        logger.info(f"Successfully sent to url: {dest_endpoint_url}")
                        result_future.set_result(True)
                    else:
                        err = f"Destination {dest_endpoint_url} returned {response.status_code}: {response.text}"
                        logger.error(err)
                        db_logger.error(f"Data Failed to Send to : {dest_server.name}",
                                    extra= {
                                            "src_message": json.dumps(src_msg),
                                            "dest_message": json.dumps(msg),
                                            "op_heading": f"Channel: {route.name}"
                                        }
                        )
                        result_future.set_exception(Exception(err))

            except Exception as exp:
                logger.exception(f"{exp} -> This came when sending data for route -> '{route.name}'")
                db_logger.error(f"Data Failed to Send to : {dest_server.name}",
                                extra= {
                                        "src_message": json.dumps(src_msg),
                                        "dest_message": json.dumps(msg) if 'msg' in locals() else
                                        "msg not defined due to error in message building",
                                        "op_heading": f"Channel: {route.name}"
                                    }
                )
                if not result_future.done():
                    result_future.set_exception(exp)

    except asyncio.CancelledError:
        logger.info(
            "route_worker %s cancelled for route '%s'",
            worker_number, getattr(route, 'name', route),
        )
        raise
    except Exception as exp:
        logger.exception("route_worker %s crashed for route '%s': %s", worker_number, getattr(route, 'name', route), exp)
        return str(exp)
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.warning("route_worker %s: error closing httpx client", worker_number, exc_info=True)

def _build_single_response(result: dict) -> dict:
    """
    Convert a `_process_message` result dict into the shape returned by the single-ingest endpoint.
    Preserves the legacy `{"message": "Successfully sent..."}` format on a fully clean delivery
    so existing fire-and-forget callers don't break, and adds parked-route info when relevant.
    """
    delivered = result.get("delivered_routes", [])
    parked = result.get("parked_routes", [])
    if parked:
        return {
            "message": f"Delivered to {len(delivered)} destination(s); {len(parked)} parked for retry",
            "delivered_routes": delivered,
            "parked_routes": parked,
        }
    return {"message": "Successfully sent data to all destinations"}


# Shared processing for single or batch items.
async def _process_message(full_path: str, payload, trace_id: str, system_id: str):
    normalized_path = full_path if full_path.startswith("/") else "/" + full_path

    with session_local() as db:
        server = db.query(models.Server).filter(models.Server.system_id == system_id).first()
        if not server:
            logger.warning("trace=%s invalid_system_id=%s for endpoint_url=%s", trace_id, system_id, normalized_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No server registered for System-Id '{system_id}'",
            )

        endpoint = db.query(models.Endpoints).filter(models.Endpoints.url == normalized_path, models.Endpoints.server_id == server.server_id).first()
        if not endpoint:
            logger.warning("trace=%s invalid_endpoint_url=%s", trace_id, normalized_path)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'The endpoint url: {normalized_path} is not valid')

        endpoint_fields = db.query(models.EndpointFields).filter(models.EndpointFields.endpoint_id == endpoint.endpoint_id).all()
        routes = db.query(models.Route).filter(models.Route.src_endpoint_id == endpoint.endpoint_id).all()

    logger.info(f"server: {server}")
    
    if server.protocol == "FHIR":
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="FHIR payload must be a JSON object")

        logger.info("trace=%s ingest_payload_preview=%s", trace_id, payload)
        # validating fhir message
        is_valid, message = await asyncio.to_thread(
            validate_unknown_fhir_resource,
            fhir_data=payload,
        )
        if not is_valid:
            logger.exception("trace=%s FHIR validation failed: %s", trace_id, message)
            db_logger.error(
                f"FHIR validation failed for endpoint /{full_path}",
                extra={
                    "src_message": json.dumps(payload),
                    "dest_message": "FHIR validation failed, so no dest message",
                    "op_heading": f"Endpoint: /{full_path}",
                },
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(message))
    else:
        if not isinstance(payload, str):
            payload = str(payload)
        logger.info("trace=%s ingest_payload_preview=%s", trace_id, _payload_preview(payload))

    # Extract paths based on the protocol, mirroring how add_fhir/hl7_endpoint_fields
    simple_paths = []
    paths = []
    if server.protocol == "FHIR":
        resource_type = payload.get("resourceType", "Unknown")
        bundle_path_to_resource = {}
        if resource_type == "Bundle":
            for entry in payload.get("entry", []):
                resource = entry.get("resource", {})
                res_type = resource.get("resourceType", "Unknown")

                raw_paths = fhir_extract_paths(resource)
                for p in raw_paths:
                    full_path = f"{res_type}-{p}"
                    simple_paths.append(full_path)

                    full_path = await increment_segment(segment_path=full_path, list_data=paths)
                    paths.append(full_path)
                    bundle_path_to_resource[full_path] = resource
        else:
            raw_paths = fhir_extract_paths(payload)
            simple_paths = [f"{resource_type}-{p}" for p in raw_paths]
            paths = [f"{await increment_segment(segment_path=f'{resource_type}-{p}', list_data=paths)}" for p in raw_paths]
    else:
        for segment in payload.split('\n')[1:]:
            if not segment.strip():
                continue
            _, seg_paths = hl7_extract_paths(segment)
            simple_paths.extend(seg_paths)
            for p in seg_paths:
                p = await increment_segment(segment_path=p, list_data=paths)
                paths.append(p)

    logger.info("trace=%s extracted_paths=%s", trace_id, paths)
    for field in endpoint_fields:
        if await increment_segment(segment_path=field.path, list_data=[]) not in paths:
            logger.warning("trace=%s missing_path=%s", trace_id, field.path)

    src_path_to_value = {}
    if server.protocol == "FHIR":
        for path in paths:
            resource = bundle_path_to_resource.get(path, payload) if resource_type == "Bundle" else payload
            value = get_fhir_value_by_path(obj=resource, path=path)
            src_path_to_value[path] = value
    else:
        src_path_to_value = get_hl7_value_by_path(hl7_message=payload, paths=paths)

    loop = asyncio.get_running_loop()
    delivery_futures = []
    missing_routes = []
    for route in routes:
        if route.route_id in route_queue:
            future = loop.create_future()
            await route_queue[route.route_id].put((src_path_to_value, simple_paths, future, payload))
            delivery_futures.append((route.route_id, route.name, future))
        else:
            logger.warning("trace=%s route_queue_missing route_id=%s", trace_id, route.name)
            missing_routes.append(route.name)

    if routes and not delivery_futures:
        logger.error("trace=%s no_route_workers_available routes=%s", trace_id, missing_routes)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No route workers ready for routes: {', '.join(missing_routes)}. The engine may still be starting up.",
        )

    delivered_routes = []
    parked_routes = []
    errors = []
    for _, route_name, future in delivery_futures:
        try:
            outcome = await asyncio.wait_for(future, timeout=_INGEST_AWAIT_TIMEOUT)
            if isinstance(outcome, dict) and outcome.get("status") == "queued_for_retry":
                parked_routes.append({"route": route_name, "destination": outcome.get("destination")})
            else:
                delivered_routes.append(route_name)
        except asyncio.TimeoutError:
            errors.append(f"Route -> {route_name}: worker did not respond within {_INGEST_AWAIT_TIMEOUT}s (worker may have crashed or destination is down)")
        except Exception as exp:
            errors.append(f"Route -> {route_name}: {str(exp)}")

    if errors:
        logger.error("trace=%s delivery_failed errors=%s", trace_id, errors)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"One or more downstream deliveries failed: {'; '.join(errors)}",
        )

    logger.info(
        "trace=%s ingest_delivery_succeeded delivered=%s parked=%s",
        trace_id, len(delivered_routes), len(parked_routes),
    )
    return {
        "delivered_routes": delivered_routes,
        "parked_routes": parked_routes,
    }

@app.post("/batch")
async def ingest_batch(req: Request):
    """
    Bulk ingest endpoint. Each item is processed independently — one failing item does NOT
    cancel the others. The response aggregates per-item outcomes:

    Status codes:
    - `200 OK`             — all items delivered (some may be parked for retry on inactive destinations)
    - `207 Multi-Status`   — at least one item failed AND at least one succeeded
    - `502 Bad Gateway`    — every item failed
    """
    trace_id = req.headers.get("X-Trace-Id") or uuid4().hex[:12]
    start_time = time.perf_counter()
    logger.info("trace=%s batch_received", trace_id)

    try:
        payload = await req.json()
    except Exception as exp:
        logger.exception("trace=%s batch_json_parse_failed", trace_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON batch payload: {str(exp)}")

    if not isinstance(payload, list):
        logger.warning("trace=%s batch_invalid_payload_type=%s", trace_id, type(payload).__name__)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch payload must be a list")

    logger.info("trace=%s batch_item_count=%s", trace_id, len(payload))

    semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)

    async def _run_one(path_key: str, item, idx: int, system_id: str):
        item_trace_id = f"{trace_id}-{idx}"
        async with semaphore:
            try:
                result = await _process_message(path_key, item, item_trace_id, system_id=system_id)
                return {
                    "index": idx,
                    "path": path_key,
                    "status": "ok",
                    "delivered_routes": result.get("delivered_routes", []),
                    "parked_routes": result.get("parked_routes", []),
                }
            except HTTPException as http_exp:
                logger.warning(
                    "trace=%s batch_item_failed path=%s http_status=%s detail=%s",
                    item_trace_id, path_key, http_exp.status_code, http_exp.detail,
                )
                return {
                    "index": idx,
                    "path": path_key,
                    "status": "failed",
                    "http_status": http_exp.status_code,
                    "detail": str(http_exp.detail),
                }
            except Exception as exp:
                logger.exception("trace=%s batch_item_failed path=%s error=%s", item_trace_id, path_key, str(exp))
                return {
                    "index": idx,
                    "path": path_key,
                    "status": "failed",
                    "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "detail": str(exp),
                }

    tasks = []
    msg_idx = 0
    for batch_idx, batch_item in enumerate(payload):
        if not isinstance(batch_item, dict):
            logger.warning("trace=%s batch_invalid_item index=%s item_type=%s", trace_id, batch_idx, type(batch_item).__name__)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each batch item must be an object")

        system_id = batch_item.get("system_id", None)
        if system_id is None:
            logger.warning("trace=%s batch_missing_system_id index=%s", trace_id, batch_idx)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each batch item must include a 'system_id' field")

        for path_key, messages in batch_item.items():
            if path_key == "system_id":
                continue
            if isinstance(messages, list):
                for msg in messages:
                    tasks.append(_run_one(path_key, msg, msg_idx, system_id))
                    msg_idx += 1
            else:
                tasks.append(_run_one(path_key, messages, msg_idx, system_id))
                msg_idx += 1

    logger.info("trace=%s batch_message_count=%s", trace_id, len(tasks))
    results = await asyncio.gather(*tasks)

    succeeded = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] == "failed"]
    total_parked = sum(len(r.get("parked_routes", [])) for r in succeeded)
    duration = time.perf_counter() - start_time

    summary = {
        "total": len(results),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "parked_for_retry": total_parked,
        "duration_seconds": round(duration, 2),
    }

    # All items failed → 502
    if failed and not succeeded:
        logger.error("trace=%s batch_all_failed summary=%s first_error=%s", trace_id, summary, failed[0])
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"summary": summary, "failures": failed[:50]},
        )

    # Partial failure → 207 Multi-Status
    if failed:
        logger.warning("trace=%s batch_partial_failure summary=%s", trace_id, summary)
        return JSONResponse(
            status_code=207,
            content={
                "message": f"{len(succeeded)}/{len(results)} items delivered; {len(failed)} failed; {total_parked} parked for retry",
                "summary": summary,
                "failures": failed[:50],
            },
        )

    # All succeeded — note parked items if any
    if total_parked > 0:
        logger.info("trace=%s batch_success_with_parked summary=%s", trace_id, summary)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Sent {len(succeeded)} items; {total_parked} parked for retry",
                "summary": summary,
            },
        )

    logger.info("trace=%s batch_success summary=%s", trace_id, summary)
    return {"message": "Successfully sent data to all destinations", "summary": summary}


@app.post("/{full_path:path}", status_code=status.HTTP_200_OK)
async def ingest(full_path: str, req: Request):
    """
    Ingest source payloads and fan out to all mapped destination routes.

    **Path Parameters:**
    - `full_path` (str): Source endpoint URL path registered in InterfaceEngine.

    **Response (200 OK):**
    - JSON object: `{ "message": "Successfully sent data to all destinations" }`

    **Error Responses:**
    - `404 Not Found`: Incoming path is not a registered endpoint.
    - `400 Bad Request`: Validation/parsing error.
    - `502 Bad Gateway`: One or more downstream deliveries failed.
    """
    trace_id = req.headers.get("X-Trace-Id") or uuid4().hex[:12]
    system_id = req.headers.get("System-Id")
    if system_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing System-Id header")
    try:
        with session_local() as db:
            logger.info("system_id=%s", system_id)
            server = db.query(models.Server).filter(models.Server.system_id == system_id).first()
            if server is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No server found for System-Id: {system_id}")
            endpoint = db.query(models.Endpoints).filter(models.Endpoints.url == '/' + full_path, models.Endpoints.server_id == server.server_id).first()
            if not endpoint:
                logger.warning("trace=%s invalid_endpoint_url=/%s", trace_id, full_path)
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'The endpoint url: /{full_path} is not valid')

            server_protocol = server.protocol

        if server_protocol == "FHIR":
            payload = await req.json()
            result = await _process_message(full_path, payload, trace_id, system_id=system_id)
            return _build_single_response(result)

        # HL7: try JSON first (single string), then raw text
        try:
            payload = await req.json()
        except Exception:
            logger.info("trace=%s ingest_hl7_json_parse_failed_falling_back_to_text", trace_id)
            raw = await req.body()
            payload = raw.decode("utf-8", errors="replace")

        if not isinstance(payload, str):
            payload = str(payload)
        # process a single hl7 message
        result = await _process_message(full_path, payload, trace_id, system_id=system_id)
        return _build_single_response(result)
    except HTTPException:
        raise  # re-raise HTTP exceptions as-is
    except Exception as exp:
        logger.exception("trace=%s ingest_unhandled_error=%s", trace_id, str(exp))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

if "__main__" == __name__:
    import uvicorn
    uvicorn.run("main:app", port=9000, reload=True, host="0.0.0.0")
