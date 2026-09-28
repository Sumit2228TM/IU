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

SET_DP          = True
APPLY_SCREENING = True

REQUEST_CREATE_PATH    = "/specimen-catalogs/{catalog_id}/specimen-requests"
REQUEST_GET_PATH       = "/specimen-catalogs/{catalog_id}/specimen-requests/{request_id}"
REQUEST_DP_PATH        = "/specimen-catalogs/{catalog_id}/specimen-requests/{request_id}/dp"
REQUEST_SCREENING_PATH = "/specimen-catalogs/{catalog_id}/specimen-requests/{request_id}/screening-status"

METHODS_TO_TRY = ["PUT", "POST"]

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


def get_request(request_id):
    url = f"{BASE_URL}{REQUEST_GET_PATH.format(catalog_id=NEW_CATALOG_ID, request_id=request_id)}"
    resp = session.get(url)
    if resp.status_code != 200:
        return {}
    return resp.json()


def try_variants(path, request_id, payloads, changed):
    url = f"{BASE_URL}{path.format(catalog_id=NEW_CATALOG_ID, request_id=request_id)}"

    for method in METHODS_TO_TRY:
        for payload in payloads:
            resp = session.request(method, url, json=payload)

            if resp.status_code == 405:
                break

            if resp.status_code in (200, 201, 204) and changed(get_request(request_id)):
                return True

    return False


def import_request(filepath):
    filename = os.path.basename(filepath)
    url = f"{BASE_URL}{REQUEST_CREATE_PATH.format(catalog_id=NEW_CATALOG_ID)}"

    with open(filepath, "r", encoding="utf-8") as f:
        exported = json.load(f)

    dp_id  = exported.get("dpId")
    dp_ttl = exported.get("dpShortTitle")
    rmg_id = exported.get("rmgId")
    status = exported.get("screeningStatus")

    data = dict(exported)
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

    for new_id in new_ids:
        if SET_DP and dp_id:
            dp_payloads = [
                {"id": dp_id},
                {"id": dp_id, "shortTitle": dp_ttl},
                {"dpId": dp_id},
                {"dpId": dp_id, "dpShortTitle": dp_ttl},
            ]
            if try_variants(REQUEST_DP_PATH, new_id, dp_payloads,
                            lambda r: r.get("dpId") == dp_id):
                print(f"  [OK] request {new_id} DP set to {dp_id}")
            else:
                print(f"  [FAIL] request {new_id}: DP {dp_id} was not applied")

        if APPLY_SCREENING and status and status != "PENDING":
            base = {"screeningStatus": status, "dpId": dp_id, "rmgId": rmg_id,
                    "screeningComments": exported.get("screeningComments")}
            base = {k: v for k, v in base.items() if v is not None}
            alt = dict(base)
            alt["status"] = alt.pop("screeningStatus")

            if try_variants(REQUEST_SCREENING_PATH, new_id, [base, alt],
                            lambda r: r.get("screeningStatus") == status):
                print(f"  [OK] request {new_id} status set to {status}")
            else:
                print(f"  [FAIL] request {new_id}: status {status} was not applied")

        final = get_request(new_id)
        expected_status = status if (APPLY_SCREENING and status) else "PENDING"
        expected_dp     = dp_id if (SET_DP and dp_id) else None

        status_ok = final.get("screeningStatus") == expected_status
        dp_ok     = final.get("dpId") == expected_dp

        print(f"  [CHECK] request {new_id}: status expected={expected_status} now={final.get('screeningStatus')} -> {'MATCH' if status_ok else 'MISMATCH'}")
        print(f"  [CHECK] request {new_id}: dpId expected={expected_dp} now={final.get('dpId')} -> {'MATCH' if dp_ok else 'MISMATCH'}")

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
