import asyncio
from datetime import datetime
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import time
from uuid import uuid4

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, status, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from api import server, route, endpoint
from database import engine, session_local
import models
from rate_limiting import limiter, rate_limit_exceeded_handler
from validation.transformation import regex_replace_with_template, increment_segment
from validation.fhir_validation import validate_unknown_fhir_resource, get_fhir_value_by_path, fhir_extract_paths
from validation.fhir_validation import build_fhir_message
from validation.hl7_validation import get_hl7_value_by_path, hl7_extract_paths
from validation.hl7_validation import build_hl7_message

os.makedirs("logs", exist_ok=True)

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


logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.handlers.clear()

log_handler = MidnightSingleFileHandler(
    filename="logs/message.log",
    when="midnight",
    interval=1,
    backupCount=0,
    encoding="utf-8",
)
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(log_handler)

@asynccontextmanager # handle lifespan events like startup or shutdown
async def lifeSpan(app: FastAPI):
    app.state.check_server_status = asyncio.create_task(server.server_health())
    app.state.route_manager_task = asyncio.create_task(route_manager())

    yield
    
    app.state.route_manager_task.cancel()
    app.state.check_server_status.cancel()
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


@app.get("/")
def check_health():
    return {"message": "✔ Interface Engine running"}

active_route_listners = {} # consist of all the running routes|Channels lisning for a soruce endpoint
route_queue = {} # consist of each route key with that route value that it gets from source endpoint


def _payload_preview(data, max_len: int = 240) -> str:
    text = str(data)
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[:max_len] + "..."

async def route_manager():
    """
        Takes all the routes from database, and use route_worker function, after that the route|channel
        can do everything
    """
    try:
        while True:
            try:

                db = session_local()
                all_routes = db.query(models.Route).all()
                db.close()

                for route in all_routes:
                    if route.route_id not in active_route_listners:

                        route_queue[route.route_id] = asyncio.Queue() # make a async queue for a new route that is not listning
                        task = asyncio.create_task(route_worker(route)) # this start the listning the route.
                        active_route_listners[route.route_id] = task
                        logging.info(f"route_worker start for route {route.name}")
                await asyncio.sleep(5)

            except asyncio.CancelledError:
                logging.info("Route_manager received Cancellation signal")
                raise # Re-raise to properly exit
            
            except Exception as exp:
                logging.error(f"Error in route_manager: {str(exp)}")
                await asyncio.sleep(5)  # Continue running despite errors
    
    except asyncio.CancelledError:

        logging.info(f"Route Manger shutting down")
        # Cleanup: cancle all route_worker tasks that we run above
        for route_id, task in active_route_listners.items():
            task.cancel()
        # wait for all the route_workers to finish
        await asyncio.gather(*active_route_listners.values(), return_exceptions=True)

async def route_worker(route):
    """
        use Route worker to listen incomming data using aysync queue, then it validates, sends data,
        parses data and converts data from fhir <--> hl7.

        The queue items are (src_path_to_value, future) tuples. After delivery the worker
        resolves the future so that ingest() can await the result and respond to the caller
        with a real success/failure status.
    """
    try:
        db = session_local()
        dest_endpoint= db.get(models.Endpoints, route.dest_endpoint_id)
        dest_server = db.get(models.Server, route.dest_server_id)
        src_server = db.get(models.Server, route.src_server_id)

        src_endpoint_fields = db.query(models.EndpointFields) \
            .filter(models.EndpointFields.endpoint_id == route.src_endpoint_id).all()
        
        dest_endpoint_fields = db.query(models.EndpointFields) \
            .filter(models.EndpointFields.endpoint_id == route.dest_endpoint_id).all()
        
        mapping_rules_for_specific_route = db.query(models.MappingRule) \
            .filter(models.MappingRule.route_id == route.route_id).all()
        
        db.close()

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

        logging.info(f"route_Worker Started for route {route.name}")

        dest_endpoint_url = f"http://{dest_server.ip}:{dest_server.port}{dest_endpoint.url}"

        while True:
            # Each queue item is a (data, future) tuple.
            # The future lets ingest() know whether delivery succeeded or failed.
            src_path_to_value, result_future = await route_queue[route.route_id].get()
            output_data = {} # contains the output fields with value
            concat_data = {} # contains single dest field id, and multiple mapping rule that concate multiple src into a single destination.
            split_data = {} # contain single src field id, and multiple mapping rule that split that single src into multiple destination.

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
                    
                    else: # map | copy | formate | regex
                        src_path = src_id_to_path[rule.src_field_id]

                        if src_path not in src_path_to_value:
                            logging.info(f"The src path {src_path} not found in src_path_to_value: {src_path_to_value}")
                            continue
                    
                        value = src_path_to_value[src_path]

                        if rule.transform_type == 'map':
                            # here the first value will give me the map value, if the mapping value is not found then return the default value
                            value = rule.config.get(str(value).lower(), value) 
                            print("mapped-value ---> ", value)

                        elif rule.transform_type == "regex":
                            value = regex_replace_with_template(value=value, pattern_from=rule.config["from"], pattern_to=rule.config["to"])

                        elif rule.transform_type == 'format':
                            try: # 2004-10-06 → 20041006 vice versa

                                dt = datetime.strptime(str(value), rule.config["from"])
                                value = dt.strftime(rule.config["to"])

                            except Exception as exp:
                                logging.error(f"Error while transformation: {str(exp)}")

                        if rule.dest_field_id not in dest_id_to_path:
                            logging.error(f"""The destination id in rule {rule.dest_field_id}
                                           does not matches with the destination map id {dest_id_to_path}""")
                            continue
                            
                        dest_path = dest_id_to_path[rule.dest_field_id]
                        dest_path = increment_segment(dest_path) # here PID-5.1 will become PID[1]-5.1
                        output_data[dest_path] = value

                ################################## Concat Data ##################################
                for dest_id , rules in concat_data.items(): 
                    values = []

                    for rule in rules:
                        if rule.src_field_id not in src_id_to_path:
                            logging.error(f"""While Concatnation, The src_field id in rule {rule.src_field_id}
                                        does not exists in the src_id_to_path {src_id_to_path}
                                        There must be a issue when you input data in database.""")
                            continue

                        src_path = src_id_to_path[rule.src_field_id]

                        if src_path in src_path_to_value:
                            values.append(str(src_path_to_value[src_path]))

                        else:
                            logging.warning(f"while Concatnation, The src_path {src_path} not found in path data: {src_path_to_value}")
                            continue
                    
                    delimiter = rules[0].config.get('delimiter', " ") # concat on delimiter or by default with space " " 
                    concated_value = delimiter.join(values)

                    if rule.dest_field_id not in dest_id_to_path:
                        logging.error(f"""While Concatnation, The destination id in rule {rule.dest_field_id}
                                        does not matches with the destination map id {dest_id_to_path}
                                        There must be a issue when you input data in database""")
                        continue

                    dest_path = dest_id_to_path[dest_id]
                    dest_path = increment_segment(dest_path)
                    output_data[dest_path] = concated_value
                
                #################################### Spit Data ####################################
                for src_id, rules in split_data.items():

                    if src_id not in src_id_to_path:
                        logging.error(f"""While Spliting, The src_field_id from route
                                        does not exists in the src_id_to_path {src_id_to_path}
                                        There must be a issue when you input data in database.""")
                        continue


                    src_path = src_id_to_path[src_id]
                    if src_path not in src_path_to_value:
                        logging.warning(f"while Spliting, The src_path {src_path} not found in path data: {src_path_to_value}")
                        continue
                    
                    # As rules 
                    delimiter= rules[0].config.get('delimiter', ' ') # concat on delimiter or by default with space " " 
                    parts = str(src_path_to_value[src_path]).split(delimiter)

                    for i, rule in enumerate(rules):
                        if i < len(parts):
                            if rule.dest_field_id not in dest_id_to_path:
                                logging.error(f"""While Spliting, The destination id in rule {rule.dest_field_id}
                                            does not matches with the destination map id {dest_id_to_path}
                                            There must be a issue when you input data in database""")
                                continue

                            dest_path = dest_id_to_path[rule.dest_field_id]
                            dest_path = increment_segment(dest_path)
                            output_data[dest_path] = parts[i]
                    
                    if len(parts) > len(rules): # here if the while spliting, if there is some data left concatenate it with the last path
                        dest_path = dest_id_to_path[rules[-1].dest_field_id] # take the last destination path
                        print("destination path for remaining data ---> ", dest_path)
                        output_data[dest_path] += " " + (' ').join(parts[len(rules):]) # join all the remaining parts with the remining data

                # BUILD MESSAGE
                if dest_server.protocol == "FHIR":
                    msg = build_fhir_message(output_data, dest_path_to_resource) # make a fhir message with the data

                else:
                    msg = build_hl7_message(output_data=output_data, src=src_server.name,
                                                   dest=dest_server.name, msg_type=route.msg_type)

                # DELIVER — resolve the future so ingest() knows the result
                async with httpx.AsyncClient() as client:
                    if dest_server.protocol == "FHIR":
                        response = await client.post(url=dest_endpoint_url, json=msg)
                    else:
                        # HL7 is plain text — do NOT json= encode it or it arrives as a
                        # JSON string "MSH|..." instead of the raw HL7 text
                        response = await client.post(
                            url=dest_endpoint_url,
                            content=msg,
                            headers={"Content-Type": "text/plain"}
                        )
                    if response.status_code in (200, 201):
                        logging.info(f"Successfully sent to url: {dest_endpoint_url}")
                        result_future.set_result(True)
                    else:
                        err = f"Destination {dest_endpoint_url} returned {response.status_code}: {response.text}"
                        logging.error(err)
                        result_future.set_exception(Exception(err))

            except Exception as exp:
                logging.error(f"{exp}\nThis came when processing/sending data for route {route.name}")
                if not result_future.done():
                    result_future.set_exception(exp)

    except Exception as exp:
        return str(exp)

@app.post("/{full_path:path}", status_code=status.HTTP_200_OK)
async def ingest(full_path: str, req: Request):
    trace_id = req.headers.get("X-Trace-Id") or uuid4().hex[:12]
    try:
        db = session_local()
        # check url if it exists in the database.
        endpoint = db.query(models.Endpoints).filter(models.Endpoints.url == '/'+full_path).first()
        if not endpoint:
            db.close()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'The endpoint url: /{full_path} is not valid')
        
        endpoint_fields = db.query(models.EndpointFields).filter(models.EndpointFields.endpoint_id == endpoint.endpoint_id).all()
        
        # getting all the routes with this endpoint as src endpoint.
        routes = db.query(models.Route).filter(models.Route.src_endpoint_id == endpoint.endpoint_id).all()
        server = db.get(models.Server, endpoint.server_id)
        db.close()
        logging.info(
            "trace=%s ingest_received path=/%s protocol=%s routes=%s",
            trace_id,
            full_path,
            server.protocol,
            len(routes),
        )

        # Read the request body based on protocol.
        # FHIR endpoints send JSON; HL7 endpoints send the raw HL7 string
        # (either as text/plain bytes OR as a JSON-encoded string — we handle both).
        if server.protocol == "FHIR":
            payload = await req.json()  # dict
            logging.info("trace=%s ingest_payload_preview=%s", trace_id, _payload_preview(payload))

            is_valid, message = validate_unknown_fhir_resource(fhir_data=payload) # validating fhir message
            if not is_valid:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(message))
        else:
            # Try JSON first (EHR may wrap the HL7 string in JSON).
            # Fall back to raw bytes if the body is already plain text.
            try:
                payload = await req.json()  # may be a bare string "MSH|..."
                if not isinstance(payload, str):
                    # Unexpected — treat whatever we got as a string
                    payload = str(payload)
            except Exception:
                logging.info("trace=%s ingest_hl7_json_parse_failed_falling_back_to_text", trace_id)
                raw = await req.body()
                payload = raw.decode("utf-8", errors="replace")
            logging.info("trace=%s ingest_payload_preview=%s", trace_id, _payload_preview(payload))
        
        # Extract paths based on the protocol, mirroring how add_fhir/hl7_endpoint_fields
        # parses paths during endpoint 
        if server.protocol == "FHIR":
            resource_type = payload.get("resourceType", "Unknown")
            bundle_path_to_resource = {}
            if resource_type == "Bundle":
                # Bundle: extract paths per entry resource, prefixed with each resource type.
                # e.g. "Patient-birthDate", "Coverage-identifier[0].value"
                paths = []
                for entry in payload.get("entry", []):
                    resource = entry.get("resource", {})
                    res_type = resource.get("resourceType", "Unknown")
                    raw_paths = fhir_extract_paths(resource)
                    for p in raw_paths:
                        full_path = f"{res_type}-{p}"
                        paths.append(full_path)
                        bundle_path_to_resource[full_path] = resource
            else:
                # Single resource: prefix with that resource's type.
                raw_paths = fhir_extract_paths(payload)
                paths = [f"{resource_type}-{p}" for p in raw_paths]
        else:
            # HL7: iterate each non-MSH segment and collect paths, just like
            # add_hl7_endpoint_fields does during endpoint registration.
            paths = []
            for segment in payload.split('\n')[1:]:
                if not segment.strip():
                    continue
                _, seg_paths = hl7_extract_paths(segment)
                paths.extend(seg_paths)

        # Data Validation --> here you can do any kind of step if data is not available
        # you can also return the msg back, if data is not valid. but right know we will just ignore it.
        logging.info("trace=%s extracted_path_count=%s", trace_id, len(paths))
        for field in endpoint_fields:
            if field.path not in paths:
                logging.warning("trace=%s missing_path=%s", trace_id, field.path)
        
        # Extract value based on the path
        # Note: get_fhir_value_by_path strips the resource prefix internally
        src_path_to_value = {}
        if server.protocol == "FHIR":
            # Use a single loop for both single resources and Bundles.
            # For Bundles, each full path maps to its entry resource object.
            for path in paths:
                obj = bundle_path_to_resource.get(path, payload) if resource_type == "Bundle" else payload
                value = get_fhir_value_by_path(obj=obj, path=path)
                src_path_to_value[path] = value
        else:
            # For HL7, extract all values in one pass over the message segments
            src_path_to_value = get_hl7_value_by_path(hl7_message=payload, paths=paths)
        
        # For each route, create a Future so we can await the delivery result.
        # route_worker resolves the future after it gets a response from the destination.
        loop = asyncio.get_event_loop()
        delivery_futures = []
        for route in routes:
            if route.route_id in route_queue:
                future = loop.create_future()
                await route_queue[route.route_id].put((src_path_to_value, future))
                delivery_futures.append((route.route_id, future))
            else:
                logging.warning("trace=%s route_queue_missing route_id=%s", trace_id, route.name)
        
        # Wait for all route workers to finish delivery.
        # If any delivery failed, raise an error so the caller (EHR) knows to rollback.
        errors = []
        for route_id, future in delivery_futures:
            try:
                await future
            except Exception as exp:
                errors.append(f"Route {route_id}: {str(exp)}")
        
        if errors:
            logging.error("trace=%s delivery_failed errors=%s", trace_id, errors)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"One or more downstream deliveries failed: {'; '.join(errors)}"
            )
        logging.info("trace=%s ingest_delivery_succeeded destination_count=%s", trace_id, len(delivery_futures))
        return {"message": "Successfully sent data to all destinations"}
    except HTTPException:
        raise  # re-raise HTTP exceptions as-is
    except Exception as exp:
        logging.exception("trace=%s ingest_unhandled_error=%s", trace_id, str(exp))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))


if "__main__" == __name__:
    import uvicorn
    uvicorn.run("main:app", port=9000, reload=True, host="0.0.0.0")