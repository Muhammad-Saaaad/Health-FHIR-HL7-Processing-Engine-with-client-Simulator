from sqlalchemy import Column, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base # Ensure your engine uses a shared or local Base

class Server(Base):
    __tablename__ = "server"

    server_id = Column(Integer, primary_key=True, index=True)
    ip = Column(String(15), nullable=False)
    port = Column(Integer, nullable=False)
    name = Column(String(100), unique=True, nullable=False) # name(always unique)
    protocol = Column(String(5)) # e.g. FHIR, HL7
    status = Column(String(20)) # e.g. Active, Inactive

    endpoints = relationship("Endpoints", back_populates="server")

    src_route = relationship("Route", back_populates="src_server", foreign_keys="[Route.src_server_id]")
    dest_route = relationship("Route", back_populates="dest_server", foreign_keys="[Route.dest_server_id]")

class Endpoints(Base):
    __tablename__ = "endpoints"

    endpoint_id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("server.server_id")) # source(fk of server)
    url = Column(String(255), nullable=False) # endpoint url

    server = relationship("Server", back_populates="endpoints")

    endpoint_fileds = relationship("EndpointFileds", back_populates="endpoint")

    src_route = relationship("Route", back_populates="src_endpoint", foreign_keys="[Route.src_endpoint_id]")
    dest_route = relationship("Route", back_populates="dest_endpoint", foreign_keys="[Route.dest_endpoint_id]")

class EndpointFileds(Base): 
    __tablename__ = "endpoint_fileds"

    endpoint_filed_id = Column(Integer, primary_key=True, index=True)
    endpoint_id = Column(Integer, ForeignKey("endpoints.endpoint_id")) # source(fk of endpoint)
    resource = Column(String(50), nullable=False) # Patient | PID | Encounter | ORU -> useful when there are multiple resources in a msg
    path = Column(String(100), nullable=False) # name.text | name.given
    name = Column(String(100), nullable=False) # fullname | given name | mpi

    endpoint = relationship("Endpoints", back_populates="endpoint_fileds")

    mapping_rules_src = relationship("MappingRule", back_populates="src_field", foreign_keys="[MappingRule.src_field_id]")
    mapping_rules_dest = relationship("MappingRule", back_populates="dest_field", foreign_keys="[MappingRule.dest_field_id]")

class Route(Base):
    __tablename__ = "route"

    route_id = Column(Integer, primary_key=True, index=True)
    
    name = Column(String(100), unique=True, nullable=False) # name(always unique)
    src_server_id = Column(Integer, ForeignKey("server.server_id"))
    src_endpoint_id = Column(Integer, ForeignKey("endpoints.endpoint_id")) # src_endpointid(fk of endpoint)
    dest_server_id = Column(Integer, ForeignKey("server.server_id"))
    dest_endpoint_id = Column(Integer, ForeignKey("endpoints.endpoint_id")) # dest_endpoint(from server)
    msg_type = Column(String(50)) # e.g., ADT, ORM, ORU

    mapping_rules = relationship("MappingRule", back_populates="route")

    src_server = relationship("Server", back_populates="src_route", foreign_keys=[src_server_id])
    dest_server = relationship("Server", back_populates="dest_route", foreign_keys=[dest_server_id])

    src_endpoint = relationship("Endpoints", back_populates="src_route", foreign_keys=[src_endpoint_id])
    dest_endpoint = relationship("Endpoints", back_populates="dest_route", foreign_keys=[dest_endpoint_id])

class MappingRule(Base):
    __tablename__ = "mapping_rule"

    mapping_rule_id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("route.route_id")) # route(fk of route)
    src_field_id = Column(Integer, ForeignKey("endpoint_fileds.endpoint_filed_id")) # src_field(fk of endpoint_fileds)
    dest_field_id = Column(Integer, ForeignKey("endpoint_fileds.endpoint_filed_id")) # dest_field(fk of endpoint_fileds)
    transform_type = Column(String(20), nullable=False) # copy | map | format | split | concat
    config = Column(JSON, nullable=False)

    route = relationship("Route", back_populates="mapping_rules")

    src_field = relationship("EndpointFileds", back_populates="mapping_rules_src", foreign_keys=[src_field_id])
    dest_field = relationship("EndpointFileds", back_populates="mapping_rules_dest", foreign_keys=[dest_field_id])