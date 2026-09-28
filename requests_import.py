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

COMPARE_FIELDS = [
    "requestor", "requestorEmailId", "irbId",
    "dpId", "dpShortTitle", "rmgId", "rmgName", "cpId", "cpShortTitle",
    "dateOfRequest", "screeningStatus", "dateOfScreening", "screenedBy",
    "screeningComments", "activityStatus",
]

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


def try_variants(path, request_id, payloads, changed, verbose=False):
    url = f"{BASE_URL}{path.format(catalog_id=NEW_CATALOG_ID, request_id=request_id)}"

    for method in METHODS_TO_TRY:
        for payload in payloads:
            resp = session.request(method, url, json=payload)

            if verbose:
                print(f"      {method} {url}")
                print(f"        payload: {json.dumps(payload)[:300]}")
                print(f"        -> {resp.status_code} {resp.text[:300]}")
                if resp.status_code == 405:
                    print(f"        Allow: {resp.headers.get('Allow')}")

            if resp.status_code == 405:
                break

            if resp.status_code in (200, 201, 204) and changed(get_request(request_id)):
                return True

    return False


def screening_payloads(exported):
    status      = exported.get("screeningStatus")
    screened_by = exported.get("screenedBy")
    screened_id = (screened_by or {}).get("id")

    base = {"status": status, "extraAttrs": {"notifyDpUsers": False}}
    if exported.get("dateOfScreening"):
        base["date"] = exported["dateOfScreening"]

    if not screened_id:
        return [base]

    return [
        dict(base, user=screened_by),
        dict(base, user={"id": screened_id}),
    ]


def normalise(value):
    if isinstance(value, dict) and "id" in value:
        return value.get("id")
    return value


def compare_with_export(exported, final):
    diffs = 0
    for field in COMPARE_FIELDS:
        old = normalise(exported.get(field))
        new = normalise(final.get(field))
        if old == new:
            print(f"      MATCH  {field}: {old}")
        else:
            diffs += 1
            note = "  (server stamps this on create)" if field == "dateOfRequest" else ""
            print(f"      DIFF   {field}: exported={old}  imported={new}{note}")
    return diffs


def import_request(filepath):
    filename = os.path.basename(filepath)
    url = f"{BASE_URL}{REQUEST_CREATE_PATH.format(catalog_id=NEW_CATALOG_ID)}"

    with open(filepath, "r", encoding="utf-8") as f:
        exported = json.load(f)

    dp_id       = exported.get("dpId")
    dp_ttl      = exported.get("dpShortTitle")
    status      = exported.get("screeningStatus")
    screened_id = (exported.get("screenedBy") or {}).get("id")

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
        # DP
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
            print(f"  [SCREENING] request {new_id}: status {status}, original screener id {screened_id}")
            if try_variants(REQUEST_SCREENING_PATH, new_id, screening_payloads(exported),
                            lambda r: r.get("screeningStatus") == status, verbose=True):
                print(f"  [OK] request {new_id} status set to {status}")
            else:
                print(f"  [FAIL] request {new_id}: status {status} was not applied")

        final = get_request(new_id)
        print(f"  [VERIFY] request {new_id} vs {filename}")
        diffs = compare_with_export(exported, final)
        print(f"  [VERIFY] request {new_id}: {'IDENTICAL' if diffs == 0 else str(diffs) + ' field(s) differ'}")

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
