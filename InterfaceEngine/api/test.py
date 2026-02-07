# from models import EndpointFileds
# from database import get_db

mapping_abc = []
mapping = {
    "src_field" : {
        "endpoint_filed_id": "rule.src_field_id",
        "resource": "rule.src_field.resource",
        "path": "rule.src_field.path",
        "name": "rule.src_field.name",
    },
    "dest_field" : {
        "endpoint_filed_id": "rule.dest_field_id",
        "resource": "rule.dest_field.resource",
        "path": "rule.dest_field.path",
        "name": "rule.dest_field.name",
    },
    'mapping_rule_id': "rule.mapping_rule_id",
    'transform_type': "rule.transform_type",
    'config': "rule.config"
},

mapping_abc.append("1")
mapping_abc.append(mapping)
print(mapping_abc)