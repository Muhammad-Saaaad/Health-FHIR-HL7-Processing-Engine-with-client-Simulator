from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from schemas.route import GetRoute, AddRoute
import models
from database import get_db

router = APIRouter(tags=["Route"])

@router.get("/all-routes", status_code=status.HTTP_200_OK, response_model=list[GetRoute])
def all_routes(db: Session = Depends(get_db)):
    try:
        routes = db.query(models.Route).all()
        return routes
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.get("/mapping_rules/{route_id}", status_code=status.HTTP_200_OK)
def get_rules(route_id: int, db: Session = Depends(get_db)):
    """
        Take the route id, and give detail mapping based on the route id.

        returns:
        [
            {
                "src_field": {
                "endpoint_filed_id": 45,
                "resource": "Patient",
                "path": "identifier[0].value",
                "name": "mpi"
                },
                "dest_field": {
                "endpoint_filed_id": 49,
                "resource": "PID",
                "path": "PID-3",
                "name": "mpi"
                },
                "mapping_rule_id": 17,
                "transform_type": "copy",
                "config": {}
            }
        ]
    """

    if not db.get(models.Route, route_id):
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
        return mapping_data

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))


@router.get("/endpoint_field_path/{endpoint_id}", status_code=status.HTTP_200_OK)
def endpoint_field_paths(endpoint_id: int, db:Session = Depends(get_db)):
    """
        Takes all the endpoint fileds of a specific endpoint. it is use when you wanted to get fields 
        of a specific endpoint while making a route.

        returns: List of all the endpoint fileds of a specific endpoint. 
    """

    if not db.get(models.Endpoints, endpoint_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"endpoint id {endpoint_id} does not exists")

    try:    
        data = db.query(models.EndpointFileds).filter(models.EndpointFileds.endpoint_id == endpoint_id).all()
        return data

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.post("/add-route", status_code=status.HTTP_201_CREATED)
def add_route(data: AddRoute, db: Session = Depends(get_db)):
    """
    takes the route data such as: the example commented at the end, perform validation like: 
    The route already exists or not. The route name is unique or not.
    The src server id and dest server id is valid or not. and also the src|dest endpoint id.
    """
    if db.query(models.Route).filter(models.Route.name == data.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Route name already exists")
    
    if db.query(models.Route).filter(models.Route.src_endpoint_id == data.src_endpoint_id, 
                                        models.Route.dest_endpoint_id == data.des_endpoint_id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This same route with different name already exists")
    
    if not db.get(models.Server, data.src_server_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="src server id not found")
    
    if not db.get(models.Server, data.des_server_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dest server id not found")
            
    if not db.get(models.Endpoints, data.src_endpoint_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="src endpoint id not found")
    
    if not db.get(models.Endpoints, data.des_endpoint_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dest endpoint id not found")
        
    try:
        route = models.Route(
            name = data.name,
            src_server_id = data.src_server_id,
            src_endpoint_id = data.src_endpoint_id,
            dest_server_id = data.des_server_id,
            dest_endpoint_id = data.des_endpoint_id,
            msg_type = data.msg_type
        )

        db.add(route)
        db.flush()
        db.refresh(route)
    except Exception as exp:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))
    
    # Takes the mapping part of the data.
    for rule in data.rules['mappings']:
        if len(rule['src_paths']) > 1 and len(rule['dest_paths']) > 1: # if there are multiple src and destination mapping
            db.rollback()
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='transform type not valid')

        db.add_all(rules)
    db.commit() # this is added outside the loop so all the mapping_rules are added permentlly at the same time.
    return {"message": "Sucessfully done"}

# example:

# {
#   "name": "ehr-to-lis",
#   "src_server_id": 1,
#   "src_endpoint_id": 23,
#   "des_server_id": 3,
#   "des_endpoint_id": 24,
#   "msg_type": "ADT",
#   "rules": {
#     "mappings": [ 
#     {
#       "src_paths": [45],
#       "dest_paths": [49],
#       "transform": "copy",
#       "config": {}
#     },
#     {
#       "src_paths": [46],
#       "dest_paths": [50,51],
#       "transform": "split",
#       "config": {
#          "delimiter": " "
#       }
#     },
#     {
#       "src_paths": [47],
#       "dest_paths": [53],
#       "transform": "map",
#       "config": {
#         "Male": "M", "Female": "F"
#        }
#     },
#     {
#      "src_paths": [48],
#       "dest_paths": [52],
#       "transform": "format",
#       "config": {
#          "from": "%Y-%m-%d", "to": "%Y%m%d"
#       }
#     }
     
#    ]
#   }
# }