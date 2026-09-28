import requests
import json
import os
import glob

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

BASE_URL   = config["base_url"]
LOGIN_NAME = config["login_name"]
PASSWORD   = config["password"]
DOMAIN     = config["domain"]

FOLDER         = "./exported_requests"
NEW_CATALOG_ID = 182

REQUEST_CREATE_PATH = "/specimen-catalogs/{catalog_id}/specimen-requests"

session = requests.Session()

auth_response = session.post(f"{BASE_URL}/sessions", json={
    "loginName": LOGIN_NAME,
    "password": PASSWORD,
    "domain": DOMAIN
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


def import_request(filepath):
    filename = os.path.basename(filepath)
    url = f"{BASE_URL}{REQUEST_CREATE_PATH.format(catalog_id=NEW_CATALOG_ID)}"

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    data.pop("id", None)

    resp = session.post(url, json=data)

    if resp.status_code not in (200, 201):
        print(f"  [FAIL] {filename}: HTTP {resp.status_code} - {resp.text[:300]}")
        return None

    try:
        result = resp.json()
    except ValueError:
        print(f"  [FAIL] {filename}: import succeeded but response wasn't JSON - {resp.text[:300]}")
        return None

    if isinstance(result, list):
        new_ids = [r.get("id") for r in result]
    else:
        new_ids = [result.get("id")]

    print(f"  [OK] {filename} imported as new request ID(s) {new_ids}")
    return new_ids


json_files = sorted(glob.glob(os.path.join(FOLDER, "*.json")))
if not json_files:
    print(f"No .json files found in {FOLDER}")
    exit()

ok, fail = 0, 0
for fp in json_files:
    if import_request(fp) is not None:
        ok += 1
    else:
        fail += 1

print(f"\nDone. {ok} succeeded, {fail} failed.")
