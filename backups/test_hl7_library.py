# from hl7apy.parser import parse_message
# from hl7apy.consts import VALIDATION_LEVEL
# # from hl7apy.exceptions import inva

# hl7_message = """MSH|^~\\&|EHR||LIS||20260203120000||ADT^A01|MSG00001|P|2.5
# |1||12345||Smith^John||19800515|M
# |1|12|||||||||||||Silver"""

# hl7_message = hl7_message.replace("\n", "\r")

# try:
#     message = parse_message(hl7_message, validation_level=VALIDATION_LEVEL.STRICT)  # STRICT
#     print("Parsed successfully")
# except Exception as e:
#     print(f"✅ CORRECTLY REJECTED: {str(e)}")

from hl7apy.core import Message
from hl7apy.consts import VALIDATION_LEVEL
from datetime import datetime

try:
    m = Message("ADT_A01", version="2.5", validation_level=VALIDATION_LEVEL.STRICT)
    m.msh.msh_3 = 'MY_ENGINE'
    m.msh.msh_4 = 'FACILITY'
    m.msh.msh_5 = 'RECEIVING_APP'
    m.msh.msh_6 = 'DEST'
    m.msh.msh_7 = datetime.now().strftime('%Y%m%d%H%M%S')
    m.msh.msh_9 = 'ADT^A01^ADT_A01'
    m.msh.msh_10 = 'MSG001'
    m.msh.msh_11 = 'P'
    m.msh.msh_12 = '2.5'
    
    # Set PID from FHIR
    m.pid.pid_1 = '1'
    m.validate()

    print(m.to_er7())
except Exception as e:
    print(f"Exception: {e}")