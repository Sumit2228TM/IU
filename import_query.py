import requests
import json
import os
import glob
import io

BASE_URL   = "https://demo.openspecimen.org/rest/ng"
LOGIN_NAME = ""
PASSWORD   = ""
DOMAIN     = "openspecimen"

session = requests.Session()

auth_response = session.post(f"{BASE_URL}/sessions", json={ 
    "loginName": LOGIN_NAME,
    "password":  PASSWORD,
    "domain":    DOMAIN
})

FOLDER = "./exported_queries"
 
QUERY_IMPORT_PATH = "/saved-queries/definition-file"
    
auth = auth_response.json()
session.headers.update({"X-OS-API-TOKEN": auth["token"]})

if auth_response.status_code == 200:
    print("Auth Successful")
else:
    print("Unauth Access")
    exit()

KEYS_TO_REMOVE = [
    "id",
    "createdBy",
    "lastModifiedBy",
    "lastModifiedOn",
    "createdOn",
    "lastRunOn",
    "cpId"  
]

def upload_query(filepath):
    filename = os.path.basename(filepath)
    url = f"{BASE_URL}{QUERY_IMPORT_PATH}"

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key in KEYS_TO_REMOVE:
        data.pop(key, None)

    cleaned_payload = json.dumps(data).encode("utf-8")
    files = {"file": (filename, io.BytesIO(cleaned_payload), "application/json")}

    resp = session.post(url, files=files)

    if resp.status_code not in (200, 201):
        print(f"  [FAIL] {filename}: HTTP {resp.status_code} - {resp.text[:300]}")
        return False

    print(f"  [OK] {filename} imported")
    return True


json_files = sorted(glob.glob(os.path.join(FOLDER, "*.json")))
if not json_files:
    print(f"No .json files found in {FOLDER}")
    exit()

ok, fail = 0, 0
for fp in json_files:
    if upload_query(fp):
        ok += 1
    else:
        fail += 1

print(f"\nDone. {ok} succeeded, {fail} failed.")
