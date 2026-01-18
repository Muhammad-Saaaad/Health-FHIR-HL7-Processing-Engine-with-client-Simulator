# import json

# # servers = []

# with open (r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\servers.json", "r") as f:
#     servers = json.load(f)

# ## now we want to add server
# # print(servers)

# # servers.append({
# #     "abc":"edt"
# # })

# for server in servers:
#     if server['port'] == 8002:
#         print("found")

# with open(r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\servers.json", "w") as f:
#     json.dump(servers, f, indent=4)

# # ---
# import httpx

# new_visit_note = {
#   "patient_id": 2,
#   "doctor_id": 2,
#   "note_title": "string",
#   "patient_complaint": "string",
#   "dignosis": "string",
#   "note_details": "string",
#   "bill_amount": 10000
# }
# response = httpx.post("http://127.0.0.1:9000/fhir/push", json=new_visit_note)
# print(response)

# from queue import Queue

# Ehr_channel_queue = Queue()
# Ehr_channel_queue.put({"patient_id": 1, "doctor_id": 1, "note_title": "Checkup"})
# Ehr_channel_queue.put({"patient_id": 1})
# print(Ehr_channel_queue.get())
# print(Ehr_channel_queue.get())

# import json

# urls = [
#     {
#         "EHR": "http://127.0.0.1:8001/push"
#     },
#     {
#         "LIS": "http://127.0.0.1:8002/push"
#     },
#     {
#         "Payer": "http://127.0.0.1:8003/push"
#     }
# ]

# for url in urls:
#     if "EHR" in url:
#         print(url['EHR'])
#     else:
#         print('unsuccessfully done')

# print(type(urls[0]))

d = {"lis": "127.0.1-231"}
print(list(d.values())[0])
