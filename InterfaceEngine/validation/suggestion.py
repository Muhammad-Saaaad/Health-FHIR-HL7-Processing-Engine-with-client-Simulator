"""
Here we generate suggestions (transform_type + config) based on the following flow:
1. generate_single_suggestion
    1. we take the src_server and dest_server profiles into account to get any specific 
        info we can use for the mapping (e.g. date formats, code maps, etc.)
    2. we use the canonical names of the src and dest fields to derive their types (e.g. date, boolean, gender_code, regex, etc.)
    3. once we have the src_type and dest_type.

2. get_field_type
    1. we will give the canonical_names and it will give us what those names type is (refer to point 2 of generate_single_suggestion)

3. get_suggestion
    1. we will give the src_profile, dest_profile, src_type, dest_type, src_canonical_name, dest_canonical_name.
    2. it will first check the type of both src and dest fields, if they are same then it will check the field types of 
        both src and dest. if they also match then it will return copy as type and empty config.
        If the field types don't match then it will return the appropriate transform type and config based on the field type.
    
    3. if the type is not mention, then by default it will be string, means it will be just the copy, with no transformation needed.
"""

from api.endpoint import logger

def generate_single_suggestion(
    src_server: dict,
    dest_server: dict,
    src_canonical_names: list,
    dest_canonical_names: list
):
    """
        Returns transform type + config for one src->dest field pair.
        Uses both server profiles to build the correct config.
    """
    src_profile = src_server.profile if src_server.profile else {}
    dest_profile = dest_server.profile if dest_server.profile else {}

    if len(src_canonical_names) == 1 and len(dest_canonical_names) == 1:

        src_field_type = get_field_type(src_canonical_names[0])
        dest_field_type = get_field_type(dest_canonical_names[0])
        logger.info(f"Generating suggestion for {src_canonical_names[0]} ({src_field_type}) -> {dest_canonical_names[0]} ({dest_field_type})")
        return get_suggestion(src_profile, dest_profile, src_field_type, dest_field_type, src_canonical_names[0], dest_canonical_names[0])
    
    elif len(src_canonical_names) == 1 and len(dest_canonical_names) > 1:
        src_field_type = get_field_type(src_canonical_names[0])
        dest_field_types = [get_field_type(name) for name in dest_canonical_names]

        previous_suggestion = {}
        for index, dest_field_type in enumerate(dest_field_types):

            suggestion = get_suggestion(src_profile, dest_profile, src_field_type, dest_field_type, src_canonical_names[0], dest_canonical_names[index])
            if len(suggestion) > 0:
                if previous_suggestion and (previous_suggestion['transform'] != suggestion['transform'] or previous_suggestion['config'] != suggestion['config']):
                    raise ValueError(f"Conflicting suggestions for {src_canonical_names[0]} -> {dest_canonical_names[index]}: {previous_suggestion} vs {suggestion}")
            
            previous_suggestion = suggestion
        logger.info(f"Final suggestion for {src_canonical_names[0]} -> {dest_canonical_names}: {previous_suggestion}")
        return previous_suggestion if previous_suggestion else {"transform": "copy", "config": {}}
    
    elif len(src_canonical_names) > 1 and len(dest_canonical_names) == 1:
        dest_field_type = get_field_type(dest_canonical_names[0])
        src_field_types= [get_field_type(name) for name in src_canonical_names] 

        previous_suggestion = {}
        for index, src_field_type in enumerate(src_field_types):

            suggestion = get_suggestion(src_profile, dest_profile, src_field_type, dest_field_type, src_canonical_names[index], dest_canonical_names[0])
            if len(suggestion) > 0:
                if previous_suggestion and (previous_suggestion['transform'] != suggestion['transform'] or previous_suggestion['config'] != suggestion['config']):
                    raise ValueError(f"Conflicting suggestions for {src_canonical_names[index]} -> {dest_canonical_names[0]}: {previous_suggestion} vs {suggestion}")
            
            previous_suggestion = suggestion
        logger.info(f"Final suggestion for {src_canonical_names}: -> {dest_canonical_names[0]}: {previous_suggestion}")
        return previous_suggestion if previous_suggestion else {"transform": "copy", "config": {}}


def get_suggestion(src_profile: dict, dest_profile: dict, src_field_type: str, dest_field_type: str, src_canonical_name: str, dest_canonical_name: str) -> dict:

    if (src_field_type == dest_field_type) and (src_field_type != "string"):
        # _________________ Date ____________________
        if src_field_type == "date":
            src_fmt = src_profile.get("date_format", "%Y-%m-%d")
            dest_fmt = dest_profile.get("date_format", "%Y-%m-%d")

            if src_fmt == dest_fmt:
                return {"transform": "copy", "config": {}}
            return {
                "transform": "format",
                "config": {"from": src_fmt, "to": dest_fmt}
            }
        
        # _________________ DateTime ____________________
        elif src_field_type == "datetime":
            src_fmt = src_profile.get("date_time_format", "%Y-%m-%dT%H:%M:%S")
            dest_fmt = dest_profile.get("date_time_format", "%Y-%m-%dT%H:%M:%S")

            if src_fmt == dest_fmt:
                return {"transform": "copy", "config": {}}
            return {
                "transform": "format",
                "config": {"from": src_fmt, "to": dest_fmt}
            }
        
        # _________________  any code map (gender, boolean, status, marital, race, relationship) ____________________

        elif src_field_type in ("gender_code", "boolean", "status_code",
                        "marital_code", "race_code", "relationship_code"):
            src_map = src_profile.get(src_field_type, {})
            dest_map = dest_profile.get(dest_field_type, {})

            if not src_map or not dest_map: # if either server doesn't have a map for this code type, can't suggest a mapping
                return {"transform": "copy", "config": {}} # default to copy, user can change later if needed
            
            # The below code will do something like this:
            # src_map = {"male":"1", "female" : "0"} , dest_map = {"male":"M", "female" : "F"}
            # config = {"1": "M", "0": "F"}

            # inv_src = {"male":"1"} -> config = {"1": "M"}
            inv_src = { v: k for k, v in src_map.items() } if src_map else {}
            config  = {}
            if inv_src and dest_map:
                for src_val, canonical_val in inv_src.items():
                    if canonical_val in dest_map:
                        config[src_val] = dest_map[canonical_val]
            elif dest_map and not inv_src:
                config = dest_map
            elif inv_src and not dest_map:
                # dest uses canonical values (FHIR style), src uses custom
                config = { v: k for k, v in inv_src.items() }

            if not config:
                return { "transform": "copy", "config": {} }
            return { "transform": "map", "config": config }
        
        # _________________ regex ____________________
        elif src_field_type in ("id_format", "subject_reference_format", "practitioner_reference_format"):
            if dest_field_type in ("id_format", "subject_reference_format", "practitioner_reference_format"):

                src_pattern = src_profile.get(src_field_type, {})
                dest_pattern = dest_profile.get(dest_field_type, {})

                if src_pattern == dest_pattern:
                    return {"transform": "copy", "config": {}}
                
                return {"transform": "regex", "config": {"from": src_pattern, "to": dest_pattern}}
            else:
                logger.error(f"Type mismatch for regex-based field: {src_canonical_name} ({src_field_type}) -> {dest_canonical_name} ({dest_field_type})")
                raise ValueError(f"Type mismatch between {src_canonical_name} ({src_field_type}) and {dest_canonical_name} ({dest_field_type})")
                
    else:
        # here the src_field_type and dest_field_types are different.
        # _________________ regex ____________________
        if src_field_type in ("id_format", "subject_reference_format", "practitioner_reference_format"):
            if dest_field_type in ("id_format", "subject_reference_format", "practitioner_reference_format"):

                src_pattern = src_profile.get(src_field_type, {})
                dest_pattern = dest_profile.get(dest_field_type, {})

                if src_pattern == dest_pattern:
                    return {"transform": "copy", "config": {}}
                
                return {"transform": "regex", "config": {"from": src_pattern, "to": dest_pattern}}
            else:
                logger.error(f"Type mismatch for regex-based field: {src_canonical_name} ({src_field_type}) -> {dest_canonical_name} ({dest_field_type})")
                raise ValueError(f"Type mismatch between {src_canonical_name} ({src_field_type}) and {dest_canonical_name} ({dest_field_type})")
                
        # ── name ─────────────────────────────────────────────────────────────────
        elif src_field_type == "name_full" and dest_field_type == "name_part":
            return {
                "transform": "split",
                "config": {
                    "delimiter": dest_profile.get("name_delimiter", " ")
                }
            }

        elif src_field_type == "name_part" and dest_field_type == "name_full":
            src_style = src_profile.get("name_style", "")
            if src_style == "concat":
                return {
                    "transform": "concat",
                    "config": {
                        "delimiter": src_profile.get("name_delimiter", " ")
                    }
                }

        # ── address ───────────────────────────────────────────────────────────────
        elif src_field_type == "address_full" and dest_field_type == "address_part":
            return {
                "transform": "split",
                "config": { "delimiter": ", " }
            }

        elif src_field_type == "address_part" and dest_field_type == "address_full":
            return {
                "transform": "concat",
                "config": { "delimiter": ", " }
            }

        if src_field_type != dest_field_type:
            raise ValueError(f"Type mismatch between {src_canonical_name} ({src_field_type}) and {dest_canonical_name} ({dest_field_type})")

        return {"transform": "copy", "config": {}}


def get_field_type(canonical_name: str) -> str:
    """
    Derive field type from canonical name suffix.
    Checked in order — first match wins.
    if no suffix matches, defaults to "string" -> means no transformation needed, just copy the value as is.
    """

    # ── Explicit overrides for ambiguous names ────────────────────────────────
    EXPLICIT = {
        # regex (Here we say that different names can have the regex pattern type, so we will take the pattern from the profile based on the canonical name)
        "MPI":                                "id_format",
        "VID":                                "id_format",
        "practitioner_id":                    "id_format",
        "coverage_patient_ref":               "subject_reference_format",
        "invoice_patient_ref":                "subject_reference_format",
        "encounter_patient_ref":              "subject_reference_format",
        "lab_order_patient_ref":              "subject_reference_format",

        "practitioner_role_practitioner_ref": "practitioner_reference_format",
        "invoice_participant_ref_id":         "practitioner_reference_format",

        # "":  "encounter_reference_format",

        # dates
        "birth_date":                  "date",
        "deceased_date":               "date",
        "vaccine_expiry":              "date",
        "allergy_onset":               "date",
        "reaction_onset":              "date",
        "condition_onset":             "date",
        "condition_onset_start":       "date",
        "condition_end":               "date",
        "condition_recorded":          "date",
        "allergy_recorded":            "date",
        "allergy_last_occurrence":     "date",
        "immunization_date":           "date",
        "immunization_recorded":       "date",
        "rx_authored":                 "date",
        "claim_service_date":          "date",
        "eob_service_date":            "date",
        "eob_payment_date":            "date",
        "practitioner_birth_date":     "date",
        "practitioner_qualification_start": "date",
        "practitioner_qualification_end":   "date",
        "coverage_start":              "date",
        "coverage_end":                "date",
        "coverage_start_date":         "date",
        "coverage_end_date":           "date",
        "plan_effective_date":         "date",
        "plan_expiration_date":        "date",

        # datetimes
        "message_datetime":            "datetime",
        "admit_datetime":              "datetime",
        "discharge_datetime":          "datetime",
        "observation_date":            "datetime",
        "observation_start":           "datetime",
        "observation_end":             "datetime",
        "observation_issued":          "datetime",
        "report_date":                 "datetime",
        "report_issued":               "datetime",
        "report_period_start":         "datetime",
        "report_period_end":           "datetime",
        "claim_created":               "datetime",
        "eob_created":                 "datetime",
        "order_date":                  "datetime",
        "order_authored":              "datetime",
        "last_update_datetime":        "datetime",
        "requested_datetime":          "datetime",
        "observation_start_datetime":  "datetime",
        "observation_end_datetime":    "datetime",
        "specimen_received_datetime":  "datetime",
        "report_status_datetime":      "datetime",
        "scheduled_datetime":          "datetime",
        "observation_datetime":        "datetime",
        "analysis_datetime":           "datetime",
        "transaction_datetime":        "datetime",
        "diagnosis_datetime":          "datetime",
        "rx_fill_datetime":            "datetime",

        # booleans
        "deceased":                    "boolean",
        "multiple_birth":              "boolean",
        "patient_active":              "boolean",
        "practitioner_active":         "boolean",
        "org_active":                  "boolean",
        "rx_substitution":             "boolean",
        "vaccine_subpotent":           "boolean",
        "immunization_primary_source": "boolean",
        "order_do_not_perform":        "boolean",
        "coverage_subrogation":        "boolean",
        "claim_insurance_focal":       "boolean",

        # gender codes
        "gender":                      "gender_code",
        "practitioner_gender":         "gender_code",
        "subscriber_gender":           "gender_code",
        "guarantor_gender":            "gender_code",
        "nok_sex":                     "gender_code",

        # status codes
        "encounter_status":            "status_code",
        "coverage_status":             "status_code",
        "claim_status":                "status_code",
        "observation_status":          "status_code",
        "report_status":               "status_code",
        "order_status":                "status_code",
        "rx_status":                   "status_code",
        "allergy_status":              "status_code",
        "immunization_status":         "status_code",
        "procedure_status":            "status_code",
        "condition_status":            "status_code",
        "eob_status":                  "status_code",
        "observation_result_status":   "status_code",
        "result_status":               "status_code",

        # marital
        "marital_status":              "marital_code",

        # name
        "fullname":                    "name_full",
        "practitioner_fullname":       "name_full",
        "nok_fullname":                "name_full",
        "guarantor_fullname":          "name_full",
        "family_name":                 "name_part",
        "given_name":                  "name_part",
        "practitioner_family_name":    "name_part",
        "practitioner_given_name":     "name_part",
        "nok_family_name":             "name_part",
        "nok_given_name":              "name_part",
        "guarantor_family_name":       "name_part",
        "guarantor_given_name":        "name_part",

        # address
        "address":                     "address_full",
        "practitioner_address":        "address_full",
        "org_address":                 "address_full",
        "nok_address":                 "address_full",
        "guarantor_address":           "address_full",
        "address_line":                "address_part",
        "city":                        "address_part",
        "state":                       "address_part",
        "postal_code":                 "address_part",
        "country":                     "address_part",

        # phone
        "phone":                       "phone",
        "org_phone":                   "phone",
        "practitioner_phone":          "phone",
        "nok_phone":                   "phone",
        "guarantor_phone":             "phone",
        "business_phone":              "phone",
        "insurance_phone":             "phone",

        # quantity
        "result_value":                "quantity",
        "ref_range_low":               "quantity",
        "ref_range_high":              "quantity",
        "vaccine_dose_value":          "quantity",
        "rx_dose_value":               "quantity",
        "rx_max_dose":                 "quantity",
        "rx_quantity":                 "quantity",
        "claim_total":                 "quantity",
        "claim_unit_price":            "quantity",
        "claim_net":                   "quantity",
        "cost_amount":                 "quantity",
        "eob_total_amount":            "quantity",
        "eob_payment_amount":          "quantity",
        "eob_adjudication_amount":     "quantity",
        "component_value":             "quantity",
    }

    if canonical_name in EXPLICIT:
        return EXPLICIT[canonical_name]

    # ── Suffix-based fallback — covers all remaining fields ───────────────────
    # Checked in order, first match wins

    if canonical_name.endswith("_datetime"):    return "datetime"
    if canonical_name.endswith("_issued"):      return "datetime"

    if canonical_name.endswith("_date"):        return "date"
    if canonical_name.endswith("_start"):       return "date"
    if canonical_name.endswith("_end"):         return "date"
    if canonical_name.endswith("_dob"):         return "date"
    if canonical_name.endswith("_expiry"):      return "date"
    if canonical_name.endswith("_recorded"):    return "date"

    if canonical_name.endswith("_active"):      return "boolean"
    if canonical_name.endswith("_focal"):       return "boolean"

    if canonical_name.endswith("_status"):      return "status_code"

    if canonical_name.endswith("_amount"):      return "quantity"
    if canonical_name.endswith("_value"):       return "quantity"
    if canonical_name.endswith("_price"):       return "quantity"
    if canonical_name.endswith("_total"):       return "quantity"
    if canonical_name.endswith("_cost"):        return "quantity"
    if canonical_name.endswith("_quantity"):    return "quantity"

    if canonical_name.endswith("_phone"):       return "phone"

    if canonical_name.endswith("_fullname"):    return "name_full"
    if canonical_name.endswith("_family_name"): return "name_part"
    if canonical_name.endswith("_given_name"):  return "name_part"

    if canonical_name.endswith("_address"):     return "address_full"

    # everything else — plain string, just copy
    return "string"