import asyncio
from datetime import datetime
import logging
import uuid

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, status, HTTPException, Request

from api import server, route, endpoint
from api.endpoint import get_fhir_value_by_path, get_hl7_value_by_path, fhir_extract_paths, hl7_extract_paths
from database import engine, session_local
import models

logging.basicConfig(
    filename="message.log",
    level=logging.INFO,
    format= "%(asctime)s - %(levelname)s - %(message)s"
)

@asynccontextmanager # handle lifespan events like startup or shutdown
async def lifeSpan(app: FastAPI):
    app.state.route_manager_task = asyncio.create_task(route_manager())
    app.state.check_server_status = asyncio.create_task(server.server_health())

    yield
    
    app.state.route_manager_task.cancel()
    app.state.check_server_status.cancel()
    return

app = FastAPI(title="Interface Engine", lifespan=lifeSpan)
models.Base.metadata.create_all(bind=engine)

app.include_router(server.router, prefix="/server")
app.include_router(route.router, prefix="/route")
app.include_router(endpoint.router, prefix="/endpoint")


@app.get("/")
def check_health():
    return {"message": "✔ Interface Engine running"}

active_listners = {}
route_queue = {}

async def route_manager():
    try:
        while True:
            try:

                db = session_local()
                routes = db.query(models.Route).all()
                db.close()

                for route in routes:
                    if route.route_id not in active_listners:

                        route_queue[route.route_id] = asyncio.Queue()
                        task = asyncio.create_task(worker(route))
                        active_listners[route.route_id] = task
                        logging.info(f"worker start for route {route.route_id}")
                
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                logging.info("Route_manager received Cancellation signal")
                raise # Re-raise to properly exit
            except Exception as exp:
                logging.error(f"Error in route_manager: {str(exp)}")
                await asyncio.sleep(5)  # Continue running despite errors
    except asyncio.CancelledError:

        logging.info(f"Route Manger shutting down")
        # Cleanup: cancle all worker tasks that we run above
        for route_id, task in active_listners.items():
            task.cancel()
        # wait for all the workers to finish
        await asyncio.gather(*active_listners.values(), return_exceptions=True)

async def worker(route):
    try:
        db = session_local()
        dest_endpoint= db.get(models.Endpoints, route.dest_endpoint_id)
        dest_server = db.get(models.Server, route.dest_server_id)
        src_server = db.get(models.Server, route.src_server_id)

        src_endpoint_fields = db.query(models.EndpointFileds) \
            .filter(models.EndpointFileds.endpoint_id == route.src_endpoint_id).all()
        
        dest_endpoint_fields = db.query(models.EndpointFileds) \
            .filter(models.EndpointFileds.endpoint_id == route.dest_endpoint_id).all()
        
        mapping_rules = db.query(models.MappingRule) \
            .filter(models.MappingRule.route_id == route.route_id).all()
        
        db.close()

        # lookup maps
        src_id_to_path = {f.endpoint_filed_id: f.path for f in src_endpoint_fields}
        dest_id_to_path = {f.endpoint_filed_id: f.path for f in dest_endpoint_fields}
        dest_path_to_resource = {f.path: f.resource for f in dest_endpoint_fields}

        logging.info(f"Worker Started for route {route.route_id}")

        dest_endpoint_url = f"http://{dest_server.ip}:{dest_server.port}{dest_endpoint.url}"

        while True:
            path_data = await route_queue[route.route_id].get()
            output_data = {}
            concat_data = {}
            split_data = {}

            for rule in mapping_rules: # we have all the mapping rules based on the specific route id.

                if rule.transform_type == 'concat': # for concat we should have multiple src and 1 dest
                    # this takes a key and the value, if the key doesn't exists or exists with a different value
                    # it will replace it with []
                    concat_data.setdefault(rule.dest_field_id, []) 
                    # this rule contains the src ids and other metadata that will be use for concatination.
                    concat_data[rule.dest_field_id].append(rule)
                
                elif rule.transform_type == 'split': # for split we should have multiple dest and 1 src
                    # here we have a singe src id, that will split into multiple destinations
                    split_data.setdefault(rule.src_field_id, []).append(rule)
                
                else: # map | copy | formate
                    src_path = src_id_to_path[rule.src_field_id]

                    if src_path not in path_data:
                        continue
                
                    value = path_data[src_path]

                    if rule.transform_type == 'map': # here if there is no mapping then by default we consider the same value
                        # here the first value will give me the map value, if the mapping value is not found then return the default value
                        value = rule.config.get(str(value), value) 

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
                    output_data[dest_path] = value

            ################################## Concat Data ##################################
            for dest_id , rules in concat_data.items():
                values = []

                for rule in rules:
                    if rule.src_field_id not in src_id_to_path:
                        logging.error(f"""While Concatnation, The src_filed id in rule {rule.src_field_id}
                                    does not exists in the src_id_to_path {src_id_to_path}
                                    There must be a issue when you input data in database.""")
                        continue

                    src_path = src_id_to_path[rule.src_field_id]

                    if src_path in path_data:
                        values.append(str(path_data[src_path]))

                    else:
                        logging.warning(f"while Concatnation, The src_path {src_path} not found in path data: {path_data}")
                        continue
                
                delimiter = rules[0].config.get('delimiter', " ") # concat on delimiter or by default with space " " 
                concated_value = delimiter.join(values)

                if rule.dest_field_id not in dest_id_to_path:
                    logging.error(f"""While Concatnation, The destination id in rule {rule.dest_field_id}
                                    does not matches with the destination map id {dest_id_to_path}
                                    There must be a issue when you input data in database""")
                    continue

                dest_path = dest_id_to_path[dest_id]
                output_data[dest_path] = concated_value
            
            #################################### Spit Data ####################################
            for src_id, rules in split_data.items():

                if src_id not in src_id_to_path:
                    logging.error(f"""While Spliting, The src_filed_id from route
                                    does not exists in the src_id_to_path {src_id_to_path}
                                    There must be a issue when you input data in database.""")
                    continue


                src_path = src_id_to_path[src_id]
                if src_path not in path_data:
                    logging.warning(f"while Spliting, The src_path {src_path} not found in path data: {path_data}")
                    continue
                
                # As rules 
                delimiter= rules[0].config.get('delimiter', ' ') # concat on delimiter or by default with space " " 
                parts = str(path_data[src_path]).split(delimiter)

                for i, rule in enumerate(rules): # (len = rules) < (len = parts)
                    if i < len(parts):
                        if rule.dest_field_id not in dest_id_to_path:
                            logging.error(f"""While Spliting, The destination id in rule {rule.dest_field_id}
                                        does not matches with the destination map id {dest_id_to_path}
                                        There must be a issue when you input data in database""")
                            continue

                        dest_path = dest_id_to_path[rule.dest_field_id]
                        output_data[dest_path] = parts[i]
            
            # BUILD MESSAGE
            if dest_server.protocol == "FHIR":
                msg = await build_fhir_json(output_data, dest_path_to_resource)

            else:
                msg = await build_hl7_message(output_data=output_data, src=src_server.name,
                                               dest=dest_server.name, msg_type=route.msg_type)

            try: # message
                async with httpx.AsyncClient() as client: # here we are properly closing the connection as well
                    response = await client.post(url=dest_endpoint_url, json=msg)
                    if response.status_code == 200 or response.status_code == 201:
                        logging.info("Sucessfully Send to url: {dest_endpoint_url}")
                    else:
                        logging.error("data was not send to url: {dest_endpoint_url}")
                
            except Exception as exp:
                logging.error(f"{exp} \nThis came when sending data to url: {dest_endpoint_url}")
                raise

    except Exception as exp:
        return str(exp)

@app.post("/{full_path:path}", status_code=status.HTTP_200_OK)
async def ingest(full_path: str, req: Request):
    try:
        print(full_path)
        payload = await req.json()

        db = session_local()
        # check url
        endpoint = db.query(models.Endpoints).filter(models.Endpoints.url == '/'+full_path).first()
        if not endpoint:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'The endpoint url: /{full_path} is not valid')
        
        endpoint_fields = db.query(models.EndpointFileds).filter(models.EndpointFileds.endpoint_id == endpoint.endpoint_id).all()
        
        routes = db.query(models.Route).filter(models.Route.src_endpoint_id == endpoint.endpoint_id).all()
        server = db.get(models.Server, endpoint.server_id)
        db.close()
        
        # Extract paths based on the protocol
        if server.protocol == "FHIR":
            paths = fhir_extract_paths(payload)
        else:
            paths = hl7_extract_paths(payload)

        # Data Validation --> here you can do any kind of step if data is not available
        # you can also return the msg back, if data is not valid. but right know we will just ignore it.
        for field in endpoint_fields:
                if field.path not in paths:
                    print(f"path: {field.path} is not in the payload")
        
        # Extract value based on the path
        path_data = {}
        if server.protocol == "FHIR":
            for path in paths:
                value = get_fhir_value_by_path(obj=payload, path=path)
                path_data[path] = value
        else:
            for path in paths:
                value = get_hl7_value_by_path(obj=payload, path=path)
                path_data[path] = value
        
        for route in routes:
            if route.route_id in route_queue:
                await route_queue[route.route_id].put(path_data)
            else:
                logging.warning(f"Route {route.route_id} queue not found. Worker may not be running")
        
        return {"message": "sucessfully send data to all destinations"}

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))


async def build_hl7_message(output_data, src, dest, msg_type):
    segments = {}
    date = datetime.now()
    dt = datetime.strptime(str(date), "%Y-%m-%d %H:%M:%S.%f")
    date = dt.strftime("%Y%m%d%H%M%S")

    header = f"MSH|^~\\&|{src}||{dest}||{date}||{msg_type}|MSG{str(uuid.uuid4())}|P|2.5"
    for path, value in output_data.items():
        # example: PID-5.1
        segment = path.split("-")[0]
        field = int(path.split("-")[1].split(".")[0])
        comp = int(path.split(".")[1]) if "." in path else None

        segments.setdefault(segment, [])

        while len(segments[segment]) < field:
            segments[segment].append("")

        if comp:
            comps = segments[segment][field-1].split("^")
            while len(comps) < comp:
                comps.append("")
            comps[comp-1] = str(value)
            segments[segment][field-1] = "^".join(comps)
        else:
            segments[segment][field-1] = str(value)

    msg = ""
    for seg, fields in segments.items():
        msg += seg + "|" + "|".join(fields) + "\n"
    msg = header+"\n"+msg
    return msg

async def build_fhir_json(output_data, dest_path_to_resource):
    resources = {}

    for path, value in output_data.items():
        resource = dest_path_to_resource[path]

        resources.setdefault(resource, {})
        resources[resource][path] = value
    
    return resources

if "__main__" == __name__:
    import uvicorn
    uvicorn.run("main:app", port=9000, reload=True, host="0.0.0.0")
    
