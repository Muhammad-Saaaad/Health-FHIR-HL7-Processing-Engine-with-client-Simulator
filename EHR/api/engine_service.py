import logging
from logging.handlers import RotatingFileHandler

import httpx

logger = logging.getLogger("engine_service_logger")
logger.setLevel(logging.INFO)
formater = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")
if not logger.handlers:
    rotating_file_handler = RotatingFileHandler(
        r"logs\engine_service.log",
        maxBytes=20000, # 20KB
        backupCount=1
    )
    rotating_file_handler.setFormatter(formater)
    logger.addHandler(rotating_file_handler)

def register_patient(data: dict):
    """
    Send a FHIR Bundle (Patient + Coverage) to the InterfaceEngine for routing to downstream services.

    This is called by the EHR `POST /patients` endpoint after a new patient is inserted locally.
    The engine route is responsible for forwarding the data (via HL7) to the LIS and Payer systems.

    Args:
        data (dict): A FHIR-compliant Bundle dict containing a Patient resource and a Coverage resource.

    Returns:
        str: "sucessfull" if the engine responds with HTTP 200.

    Raises:
        Exception: If the engine returns a non-200 status (e.g., 502 on partial downstream failure),
                   raises an exception with the engine's error detail so the caller can rollback.
    """
    try:
        logger.info(f"Registering patient with engine: {data}")
        response = httpx.post("http://127.0.0.1:9000/fhir/add-patient", json=data, timeout=7)
        if response.status_code == 200:
            logger.info(f"Successfully registered patient with engine: {data['entry'][0]['resource']['id']}")
            return "sucessfull"
        # The engine returns 502 when a downstream delivery (Payer/LIS) fails.
        # Raise so add_patient() rolls back the EHR insert.
        raise Exception(response.json().get("detail", f"Engine returned {response.status_code}"))

    except Exception as exp:
        # Re-raise so the calling endpoint knows delivery failed
        logger.error(f"Failed to register patient with engine: {str(exp)}")
        raise

def send_visit_note_to_engine(data: dict):
    """
    Send a FHIR Bundle (ServiceRequest + encounter + Practitioner +  ) to the InterfaceEngine for routing to downstream services.

    This is called by the EHR `POST /visit-notes` endpoint after a new visit note is inserted locally.
    The engine route is responsible for forwarding the data (via HL7) to the LIS and Payer systems.

    Args:
        data (dict): A FHIR-compliant Bundle dict containing a ServiceRequest resource and one or more Observation resources.

    Returns:
        str: "sucessfull" if the engine responds with HTTP 200.

    Raises:
        Exception: If the engine returns a non-200 status (e.g., 502 on partial downstream failure),
                   raises an exception with the engine's error detail so the caller can rollback.
    """
    try:
        logger.info(f"Sending visit note to engine: {data}")
        response = httpx.post("http://127.0.0.1:9000/fhir/add-visit-note", json=data, timeout=7)
        
        if response.status_code in (200, 201):
            logger.info(f"Successfully sent visit note to engine: {data['entry'][0]['resource']['id']}")
            return "sucessfull"
    
    except Exception as exp:
        # Re-raise so the calling endpoint knows delivery failed
        logger.error(f"Failed to send visit note to engine: {str(exp)}")
        raise

def send_claim_to_engine(data: dict):
    try:
        logger.info(f"Sending claim to engine: {data}")
        response = httpx.post("http://127.0.0.1:9000/fhir/submit-claim", json=data, timeout=7)
        
        if response.status_code in (200, 201):
            logger.info(f"Successfully sent claim to engine: {data['id']}")
            return "sucessfull"
        
    except httpx.RequestError as req_err:
        logger.error(f"HTTP request error while sending claim to engine: {str(req_err)}")
        raise Exception(f"HTTP request error: {str(req_err)}") from req_err
    except Exception as exp:
        # Re-raise so the calling endpoint knows delivery failed
        logger.error(f"Failed to send claim to engine: {str(exp)} with response: {response}")
        raise