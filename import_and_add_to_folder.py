import requests
import json
import os
import glob

with open("config.json") as f:
    cfg = json.load(f)

BASE_URL = cfg["base_url"]
LOGIN_NAME = cfg["login_name"]
PASSWORD = cfg["password"]
DOMAIN = cfg["domain"]

FOLDER     = "./exported_queries"
FOLDER_ID  = 4

QUERY_IMPORT_PATH  = "/saved-queries/definition-file"
ADD_TO_FOLDER_PATH = "/query-folders/{folder_id}/saved-queries"

session = requests.Session()

auth_response = session.post(f"{BASE_URL}/sessions", json={
    "loginName": LOGIN_NAME,
    "password":  PASSWORD,
    "domain":    DOMAIN
})

if auth_response.status_code == 200:
    print("Auth Successful")
else:
    print("Unauth Access")
    print("Status:", auth_response.status_code)
    print("Body:", repr(auth_response.text))
    exit()

auth = auth_response.json()
session.headers.update({"X-OS-API-TOKEN": auth["token"]})


def import_query(filepath):
    filename = os.path.basename(filepath)
    url = f"{BASE_URL}{QUERY_IMPORT_PATH}"

    with open(filepath, "rb") as f:
        files = {"file": (filename, f, "application/json")}
        resp = session.post(url, files=files)

    if resp.status_code not in (200, 201):
        print(f"  [FAIL] {filename}: HTTP {resp.status_code} - {resp.text[:300]}")
        return None

    try:
        result = resp.json()
    except ValueError:
        print(f"  [FAIL] {filename}: import succeeded but response wasn't JSON - {resp.text[:300]}")
        return None

    new_id = result.get("id")
    if new_id is None:
        print(f"  [WARN] {filename}: imported, but couldn't find 'id' in response - {resp.text[:300]}")
        return None

    print(f"  [OK] {filename} imported as new query ID {new_id}")
    return new_id


def add_to_folder(query_ids):
    if not query_ids:
        print("No successfully imported query IDs to add to folder.")
        return

    url = f"{BASE_URL}{ADD_TO_FOLDER_PATH.format(folder_id=FOLDER_ID)}"
    params = {"operation": "ADD"}
    resp = session.put(url, params=params, json=query_ids)

    if resp.status_code not in (200, 201):
        print(f"[FAIL] Add to folder: HTTP {resp.status_code} - Allow: {resp.headers.get('Allow')} - {resp.text[:300]}")
    else:
        print(f"[OK] Added queries {query_ids} to folder {FOLDER_ID}")


json_files = sorted(glob.glob(os.path.join(FOLDER, "*.json")))
if not json_files:
    print(f"No .json files found in {FOLDER}")
    exit()

new_ids = []
for fp in json_files:
    result_id = import_query(fp)
    if result_id is not None:
        new_ids.append(result_id)

print(f"\nImport done. {len(new_ids)} succeeded, {len(json_files) - len(new_ids)} failed.")

add_to_folder(new_ids)
