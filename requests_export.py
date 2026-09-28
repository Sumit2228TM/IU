import requests
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

BASE_URL   = config["base_url"]
LOGIN_NAME = config["login_name"]
PASSWORD   = config["password"]
DOMAIN     = config["domain"]

CATALOG_ID  = 182
REQUEST_IDS = [483]
OUT_DIR     = "./exported_requests"

REQUEST_GET_PATH = "/specimen-catalogs/{catalog_id}/specimen-requests/{id}"

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


def download_request(request_id, out_dir):
    url = f"{BASE_URL}{REQUEST_GET_PATH.format(catalog_id=CATALOG_ID, id=request_id)}"
    resp = session.get(url)

    if resp.status_code != 200:
        print(f"  [FAIL] Request {request_id}: HTTP {resp.status_code} - {resp.text[:300]}")
        return False

    try:
        data = resp.json()
    except ValueError:
        print(f"  [FAIL] Request {request_id}: response was not valid JSON")
        return False

    out_path = os.path.join(out_dir, f"request_{request_id}.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  [OK] Request {request_id} -> {out_path}")
    return True


os.makedirs(OUT_DIR, exist_ok=True)

ok, fail = 0, 0
for rid in REQUEST_IDS:
    if download_request(rid, OUT_DIR):
        ok += 1
    else:
        fail += 1

print(f"\nDone. {ok} succeeded, {fail} failed. Files saved in: {OUT_DIR}")
