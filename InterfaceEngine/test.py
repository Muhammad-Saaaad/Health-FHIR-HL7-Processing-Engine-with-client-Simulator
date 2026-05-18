from database import session_local
import models

def get_lis_payer():
    """
        create a list, that tells that from this ehr we can send data to this lab and this payer.
        use to display the labs and payers in the ehr while adding patient, and visiting notes.
    """
    db = None
    db = session_local()
    all_routes = db.query(models.Route).all()
    
    data_by_ehr = {}
    for route in all_routes:
        src_server = route.src_server # takes the entire server data.
        dest_server = route.dest_server
        
        if not src_server or not dest_server:
            continue

        if src_server.category != "EHR" or dest_server.status != "Active":
            continue

        ehr_data = data_by_ehr.setdefault(src_server.system_id, {
            "ehr_system_id": src_server.system_id,
            "labs": [],
            "payers": []
        })

        # Any active EHR→LIS route makes that lab "connected" (don't filter by msg_type:
        # the EHR may use multiple message types — orders, results, etc. — for the same lab).
        if dest_server.category == "LIS":
            lab = {
                "system_id": dest_server.system_id,
                "name": dest_server.name
            }
            if lab not in ehr_data["labs"]:
                ehr_data["labs"].append(lab)

        elif dest_server.category == "Payer":
            payer = {
                "system_id": dest_server.system_id,
                "name": dest_server.name
            }
            if payer not in ehr_data["payers"]:
                ehr_data["payers"].append(payer)

    data = list(data_by_ehr.values())
    db.close()
    return data

print(get_lis_payer())