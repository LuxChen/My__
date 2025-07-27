
import requests
import logging
from localtools import base
base.initLogging()
res = requests.request('POST', 'https://api.dify.ai/v1/workflows/run', headers={"Authorization": "Bearer app-oq8UPqAO6T32wZLuo0jF2GZT",
                 "Content-Type": "application/json"}, json={"inputs": {}, "response_mode": "blocking", "user": "abc-123"})

logging.info(f"Response: {res.status_code} {res.text}")
# logging.info(res.json().get("data",{}).get("outputs",{}).get("outarr",[]))