import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from schemas.route import GetRoute, AddRoute
import models
from database import get_db

router = APIRouter(tags=["Route"])

logger = logging.getLogger("route_logger")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler("logs/route.log", maxBytes=1000000, backupCount=5)
handler.setFormatter(logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"))
logger.addHandler(handler)


@router.get("/all-routes", status_code=status.HTTP_200_OK, response_model=list[GetRoute])
def all_routes(db: Session = Depends(get_db)):
    """
    Retrieve all configured routes in the Interface Engine.

    A route defines how messages are forwarded from a source server/endpoint
    to a destination server/endpoint, along with the associated field mapping rules.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of route objects. Each item includes:
    - `route_id` (int): Unique route identifier
    - `channel_name` (str): Descriptive name for the route (e.g., "ehr-to-lis")
    - `src_server` (object): Source server details:
        - `server_id` (int): Source server ID
        - `name` (str): Source server name
    - `src_endpoint` (object): Source endpoint details:
        - `endpoint_id` (int): Source endpoint ID
        - `url` (str): Source endpoint URL
    - `dest_server` (object): Destination server details:
        - `server_id` (int): Destination server ID
        - `name` (str): Destination server name
    - `dest_endpoint` (object): Destination endpoint details:
        - `endpoint_id` (int): Destination endpoint ID
        - `url` (str): Destination endpoint URL
    - `msg_type` (str): Message/event type this route handles (e.g., "ADT")

    **Note:**
    - Returns an empty list if no routes have been configured.

    **Error Responses:**
    - `400 Bad Request`: Unexpected database error
    """
    logger.info("All routes request received")

    try:
        routes = db.query(models.Route).all()
        response = [
            {
                "route_id": route.route_id,
                "channel_name": route.name,
                "src_server": {"server_id": route.src_server.server_id, "name": route.src_server.name, 'protocol': route.src_server.protocol},
                "src_endpoint": {"endpoint_id": route.src_endpoint.endpoint_id, "url": route.src_endpoint.url},
                "dest_server": {"server_id": route.dest_server.server_id, "name": route.dest_server.name, 'protocol': route.dest_server.protocol},
                "dest_endpoint": {"endpoint_id": route.dest_endpoint.endpoint_id, "url": route.dest_endpoint.url},
                "msg_type": route.msg_type
            } for route in routes
        ]
        logger.info(f"All routes fetched successfully: total_routes={len(response)}")
        return response
    except Exception as e:
        logger.error(f"Error retrieving routes: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.get("/mapping_rules/{route_id}", status_code=status.HTTP_200_OK)
def get_rules(route_id: int, db: Session = Depends(get_db)):
    """
    Retrieve all field mapping rules for a specific route, grouped by transformation type.

    Returns a structured representation of how source fields are mapped to destination fields.
    Rules are grouped into three transformation categories: copy/map/format, split, and concat.

    **Path Parameters:**
    - `route_id` (int, required): The unique identifier of the route to inspect.

    **Response (200 OK):**
    Returns a mixed list of mapping rule objects. The shape depends on `transform_type`:

    - **copy / map / format** — one-to-one field mapping:
      ```json
      {
        "src_field": { "endpoint_filed_id": 45, "resource": "Patient", "path": "identifier[0].value", "name": "mpi" },
        "dest_field": { "endpoint_filed_id": 49, "resource": "PID", "path": "PID-3", "name": "mpi" },
        "mapping_rule_id": 17,
        "transform_type": "copy",
        "config": {}
      }
      ```

    - **split** — one source field mapped to multiple destination fields:
      ```json
      {
        "src_field": { ... },
        "dest_field": [ { ... }, { ... } ],
        "transform_type": "split",
        "config": { "delimiter": " " }
      }
      ```

    - **concat** — multiple source fields merged into one destination field:
      ```json
      {
        "src_field": [ { ... }, { ... } ],
        "dest_field": { ... },
        "transform_type": "concat",
        "config": {}
      }
      ```

    **Supported Transform Types:**
    - `copy`: Direct value copy from source to destination
    - `map`: Value substitution using a lookup table in `config` (e.g., `{"Male": "M", "Female": "F"}`)
    - `format`: Date/time format conversion using `config` (e.g., `{"from": "%Y-%m-%d", "to": "%Y%m%d"}`)
    - `split`: Split a single source value into multiple destinations using a delimiter
    - `concat`: Merge multiple source values into a single destination field

    **Error Responses:**
    - `404 Not Found`: No route exists with the given `route_id`
    - `400 Bad Request`: Unexpected database error
    """
    logger.info(f"Mapping rules request received for route_id={route_id}")

    if not db.get(models.Route, route_id):
        logger.warning(f"Route id {route_id} not found when fetching mapping rules")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route id {route_id} does not exists")

    try:
        mapping_rules_of_route = db.query(models.MappingRule).filter(models.MappingRule.route_id == route_id).all()
        mapping_data = []
        split_data = []
        concat_data = []

        for rule in mapping_rules_of_route: # this rule is from the database hence it can only be access via . not like this: ['']
            if rule.transform_type in ['copy', 'map', 'format']:
                mapping = {
                    "src_field" : {
                        "endpoint_filed_id": rule.src_field_id,
                        "resource": rule.src_field.resource,
                        "path": rule.src_field.path,
                        "name": rule.src_field.name
                    },
                    "dest_field" : {
                        "endpoint_filed_id": rule.dest_field_id,
                        "resource": rule.dest_field.resource,
                        "path": rule.dest_field.path,
                        "name": rule.dest_field.name
                    },
                    'mapping_rule_id': rule.mapping_rule_id,
                    'transform_type': rule.transform_type,
                    'config': rule.config
                }
                mapping_data.append(mapping)

            elif rule.transform_type == 'split':

                # here we check if the src_field_id already exists or not, if does then append the data
                #  with destination. If not then add a new data in the list
                exists = False 
                for data in split_data: # if the split_data is empty then then stil the below if will execute
                    if data['src_field']['endpoint_filed_id'] == rule.src_field_id:
                        data['dest_field'].append(
                            {
                                "endpoint_filed_id": rule.dest_field_id,
                                "resource": rule.dest_field.resource,
                                "path": rule.dest_field.path,
                                "name": rule.dest_field.name
                            }
                        )
                        exists = True
                        break
                
                if exists == False: 
                    # if the src_field existed then we append data into its own place else we make a new data
                    split_data.append(
                        {
                            "src_field" : {
                                "endpoint_filed_id": rule.src_field_id,
                                "resource": rule.src_field.resource,
                                "path": rule.src_field.path,
                                "name": rule.src_field.name
                            },
                            "dest_field" : [
                                {
                                    "endpoint_filed_id": rule.dest_field_id,
                                    "resource": rule.dest_field.resource,
                                    "path": rule.dest_field.path,
                                    "name": rule.dest_field.name
                                }
                            ],
                            'mapping_rule_id': rule.mapping_rule_id,
                            'transform_type': rule.transform_type,
                            'config': rule.config
                        },
                    )
            
            elif rule.transform_type == 'concat':

                exists = False 
                for data in concat_data: # if the split_data is empty then then stil the below if will execute
                    if data['dest_field']['endpoint_filed_id'] == rule.dest_field_id:
                        data['src_field'].append(
                            {
                                "endpoint_filed_id": rule.src_field_id,
                                "resource": rule.src_field.resource,
                                "path": rule.src_field.path,
                                "name": rule.src_field.name
                            }
                        )
                        exists = True
                        break
                
                if exists == False: 
                    # if the src_field existed then we append data into its own place else we make a new data
                    concat_data.append(
                        {
                            "src_field" : [
                                {
                                    "endpoint_filed_id": rule.src_field_id,
                                    "resource": rule.src_field.resource,
                                    "path": rule.src_field.path,
                                    "name": rule.src_field.name
                                }
                            ],
                            "dest_field" :{
                                    "endpoint_filed_id": rule.dest_field_id,
                                    "resource": rule.dest_field.resource,
                                    "path": rule.dest_field.path,
                                    "name": rule.dest_field.name
                            },
                            'mapping_rule_id': rule.mapping_rule_id,
                            'transform_type': rule.transform_type,
                            'config': rule.config
                        },
                    )

        mapping_data.extend(split_data)
        mapping_data.extend(concat_data)
        logger.info(
            f"Mapping rules fetched successfully for route_id={route_id}: total_rules={len(mapping_data)}"
        )
        return mapping_data

    except Exception as exp:
        logger.error(f"Error retrieving mapping rules for route id {route_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))


@router.post("/add-route", status_code=status.HTTP_201_CREATED)
def add_route(data: AddRoute, db: Session = Depends(get_db)):
    """
    Create a new message routing rule between two server endpoints with field-level mapping.

    A route defines the complete pipeline for transforming and forwarding a message from
    a source endpoint to a destination endpoint. Each mapping rule specifies how individual
    fields are transformed (copy, split, concat, map, format).

    **Request Body:**
    - `name` (str, required): Unique descriptive name for this route (e.g., "ehr-to-lis").
    - `src_server_id` (int, required): ID of the source server. Must exist.
    - `src_endpoint_id` (int, required): ID of the source endpoint. Must exist.
    - `dest_server_id` (int, required): ID of the destination server. Must exist.
    - `dest_endpoint_id` (int, required): ID of the destination endpoint. Must exist.
    - `msg_type` (str, required): Message/event type this route handles (e.g., "ADT", "ORU").
    - `rules` (object, required): Mapping rules object with the following structure:
      ```json
      {
        "mappings": [
          {
            "src_paths": [<endpoint_field_id>],
            "dest_paths": [<endpoint_field_id>],
            "transform": "copy | map | format | split | concat",
            "config": {}
          }
        ]
      }
      ```

    **Transform Types and Config:**
    | Type | `src_paths` | `dest_paths` | `config` example |
    |------|------------|-------------|-----------------|
    | `copy` | 1 field | 1 field | `{}` |
    | `map` | 1 field | 1 field | `{"Male": "M", "Female": "F"}` |
    | `format` | 1 field | 1 field | `{"from": "%Y-%m-%d", "to": "%Y%m%d"}` |
    | `split` | 1 field | multiple fields | `{"delimiter": " "}` |
    | `concat` | multiple fields | 1 field | `{}` |

    **Response (201 Created):**
    Returns a confirmation message:
    - `message`: "Sucessfully done"

    **Constraints:**
    - Route name must be unique.
    - The same src+dest endpoint pair cannot be registered twice (even with a different name).
    - All server and endpoint IDs must refer to existing records.
    - A single mapping rule cannot have multiple source AND multiple destination paths simultaneously.

    **Error Responses:**
    - `409 Conflict`: Route name already exists
    - `409 Conflict`: A route with the same src/dest endpoint pair already exists
    - `404 Not Found`: src or dest server/endpoint ID not found
    - `403 Forbidden`: A single rule has both multiple src_paths and multiple dest_paths
    - `400 Bad Request`: Invalid transform type, or unexpected database error
    """
    logger.info(
        f"Add route request received: name={data.name}, src_endpoint_id={data.src_endpoint_id}, "
        f"dest_endpoint_id={data.dest_endpoint_id}, msg_type={data.msg_type}"
    )

    if db.query(models.Route).filter(models.Route.name == data.name).first():
        logger.warning(f"Add route rejected: duplicate route name '{data.name}'")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Route name already exists")
    
    if db.query(models.Route).filter(models.Route.src_endpoint_id == data.src_endpoint_id, 
                                        models.Route.dest_endpoint_id == data.dest_endpoint_id).first():
        logger.warning(
            f"Add route rejected: duplicate src/dest endpoint pair "
            f"src_endpoint_id={data.src_endpoint_id}, dest_endpoint_id={data.dest_endpoint_id}"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This same route with different name already exists")
    
    if not db.get(models.Server, data.src_server_id):
        logger.warning(f"Add route rejected: src server id {data.src_server_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="src server id not found")
    
    if not db.get(models.Server, data.dest_server_id):
        logger.warning(f"Add route rejected: dest server id {data.dest_server_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dest server id not found")
            
    if not db.get(models.Endpoints, data.src_endpoint_id):
        logger.warning(f"Add route rejected: src endpoint id {data.src_endpoint_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="src endpoint id not found")
    
    if not db.get(models.Endpoints, data.dest_endpoint_id):
        logger.warning(f"Add route rejected: dest endpoint id {data.dest_endpoint_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dest endpoint id not found")
        
    try:
        route = models.Route(
            name = data.name,
            src_server_id = data.src_server_id,
            src_endpoint_id = data.src_endpoint_id,
            dest_server_id = data.dest_server_id,
            dest_endpoint_id = data.dest_endpoint_id,
            msg_type = data.msg_type
        )

        db.add(route)
        db.flush()
        db.refresh(route)
        logger.info(f"Route created and flushed successfully with route_id={route.route_id}")
    except Exception as exp:
        db.rollback()
        logger.error(f"Add route failed while creating route header: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))
    
    # Takes the mapping part of the data.
    for rule in data.rules['mappings']:
        if len(rule['src_paths']) > 1 and len(rule['dest_paths']) > 1: # if there are multiple src and destination mapping
            db.rollback()
            logger.warning(
                f"Add route rejected: invalid mapping rule has multiple source and destination fields "
                f"for route_id={route.route_id}"
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cannot give 2 src and destination in a single rule")
        
        rules = []
        if rule['transform'] == 'concat': # if transformation type is concat then take 1 dest_path and list of src paths
            for src_path in rule['src_paths']:
                rules.append(models.MappingRule(
                    route_id = route.route_id,
                    src_field_id = src_path,
                    dest_field_id = rule['dest_paths'][0],
                    transform_type = rule['transform'],
                    config = rule['config']
            ))
            
        elif rule['transform'] == 'split': # if transformation type is split then take 1 src_path and list of dest paths
            for dest_path in rule['dest_paths']:
                rules.append(models.MappingRule(
                    route_id = route.route_id,
                    src_field_id = rule['src_paths'][0],
                    dest_field_id = dest_path,
                    transform_type = rule['transform'],
                    config = rule['config']
            ))

        elif rule['transform'] in ['copy', 'map', 'format'] :
            rules.append(models.MappingRule(
                route_id = route.route_id,
                src_field_id = rule['src_paths'][0],
                dest_field_id = rule['dest_paths'][0],
                transform_type = rule['transform'],
                config = rule['config']
            ))
        
        else:
            db.rollback()
            logger.warning(
                f"Add route rejected: invalid transform type '{rule['transform']}' for route_id={route.route_id}"
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='transform type not valid')

        db.add_all(rules)
    db.commit() # this is added outside the loop so all the mapping_rules are added permentlly at the same time.
    logger.info(
        f"Add route completed successfully: route_id={route.route_id}, total_mapping_rules={len(data.rules['mappings'])}"
    )
    return {"message": "Sucessfully done"}

@router.delete("/delete-route/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(route_id: int, db: Session = Depends(get_db)):
    """
    Delete an existing route and all its associated mapping rules.

    **Path Parameters:**
    - `route_id` (int, required): The unique identifier of the route to delete.

    **Response:**
    - `204 No Content`: Route and its mapping rules were successfully deleted.

    **Error Responses:**
    - `404 Not Found`: No route exists with the given `route_id`
    - `400 Bad Request`: Unexpected database error
    """
    logger.info(f"Delete route request received: route_id={route_id}")

    route = db.get(models.Route, route_id)
    if not route:
        logger.warning(f"Delete route rejected: route id {route_id} does not exist")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route id {route_id} does not exists")
    
    try:
        db.query(models.MappingRule).filter(models.MappingRule.route_id == route_id).delete()
        db.delete(route)
        db.commit()
        logger.info(f"Delete route completed successfully: route_id={route_id}")
    except Exception as exp:
        db.rollback()
        logger.error(f"Delete route failed for route_id={route_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))