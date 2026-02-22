import httpx

def register_engine(data: dict):
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
        response = httpx.post("http://127.0.0.1:9000/fhir/add-patient", json=data)
        if response.status_code == 200:
            return "sucessfull"
        # The engine returns 502 when a downstream delivery (Payer/LIS) fails.
        # Raise so add_patient() rolls back the EHR insert.
        raise Exception(response.json().get("detail", f"Engine returned {response.status_code}"))

    except Exception as exp:
        # Re-raise so the calling endpoint knows delivery failed
        raise