import datetime
import glob
import json
import os
import requests

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.json"
)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
  config = json.load(f)

BASE_URL = config["base_url"]
LOGIN_NAME = config["login_name"]
PASSWORD = config["password"]
DOMAIN = config["domain"]

FOLDER = "./exported_requests"
NEW_CATALOG_ID = 182

SET_DP = True
APPLY_SCREENING = True
SET_REQUEST_DATE = True

REQUEST_CREATE_PATH = "/specimen-catalogs/{catalog_id}/specimen-requests"
REQUEST_GET_PATH = (
    "/specimen-catalogs/{catalog_id}/specimen-requests/{request_id}"
)
REQUEST_UPDATE_PATH = (
    "/specimen-catalogs/{catalog_id}/specimen-requests/{request_id}"
)
REQUEST_DP_PATH = (
    "/specimen-catalogs/{catalog_id}/specimen-requests/{request_id}/dp"
)
REQUEST_SCREENING_PATH = (
    "/specimen-catalogs/{catalog_id}/specimen-requests/{request_id}/screening-status"
)

session = requests.Session()

auth_response = session.post(
    f"{BASE_URL}/sessions",
    json={"loginName": LOGIN_NAME, "password": PASSWORD, "domain": DOMAIN},
)

if auth_response.status_code == 200:
  print("Auth Successful")
else:
  print("Unauth Access")
  print("Status:", auth_response.status_code)
  print("Body:", repr(auth_response.text))
  exit()

auth = auth_response.json()
session.headers.update({"X-OS-API-TOKEN": auth["token"]})


def get_req_date(data):
  if not isinstance(data, dict):
    return None
  for k in [
      "dateOfRequest",
      "dateofRequest",
      "requestDate",
      "date",
      "creationDate",
  ]:
    if data.get(k):
      return data[k]
  return None


def normalize_date_to_variants(val):
  if val is None:
    return []
  variants = [val]

  dt = None
  try:
    num = float(val)
    if num > 1e11:
      dt = datetime.datetime.fromtimestamp(num / 1000.0, datetime.timezone.utc)
    else:
      dt = datetime.datetime.fromtimestamp(num, datetime.timezone.utc)
  except (ValueError, TypeError):
    pass

  if dt is None and isinstance(val, str):
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
      try:
        dt = datetime.datetime.strptime(val, fmt).replace(
            tzinfo=datetime.timezone.utc
        )
        break
      except ValueError:
        pass

  if dt:
    ymd = dt.strftime("%Y-%m-%d")
    iso_z = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    iso_ms = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    millis = int(dt.timestamp() * 1000)
    seconds = int(dt.timestamp())

    for v in [ymd, iso_z, iso_ms, millis, seconds]:
      if v not in variants:
        variants.append(v)

  return variants


def get_request(request_id):
  url = f"{BASE_URL}{REQUEST_GET_PATH.format(catalog_id=NEW_CATALOG_ID, request_id=request_id)}"
  resp = session.get(url)
  if resp.status_code != 200:
    return {}
  return resp.json()


def try_put_endpoint(path, request_id, payloads, check_changed):
  url = f"{BASE_URL}{path.format(catalog_id=NEW_CATALOG_ID, request_id=request_id)}"
  for payload in payloads:
    resp = session.put(url, json=payload)
    if resp.status_code in (200, 201, 204) and check_changed(
        get_request(request_id)
    ):
      return True
  return False


def restore_request_date(request_id, req_date):
  date_vars = normalize_date_to_variants(req_date) if req_date else []
  if not date_vars:
    return

  for d_var in date_vars:
    date_payloads = [
        {"dateOfRequest": d_var},
        {"requestDate": d_var},
        {"date": d_var},
        {"dateOfRequest": d_var, "requestDate": d_var, "date": d_var},
    ]
    if try_put_endpoint(
        REQUEST_UPDATE_PATH,
        request_id,
        date_payloads,
        lambda r: get_req_date(r) == req_date,
    ):
      return

  cur_req = get_request(request_id)
  if cur_req:
    for d_var in date_vars:
      test_obj = dict(cur_req)
      test_obj["dateOfRequest"] = d_var
      test_obj["requestDate"] = d_var
      test_obj["date"] = d_var
      update_url = f"{BASE_URL}{REQUEST_UPDATE_PATH.format(catalog_id=NEW_CATALOG_ID, request_id=request_id)}"
      session.put(update_url, json=test_obj)


def screening_payloads(exported):
  status = exported.get("screeningStatus")
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


def import_request(filepath):
  filename = os.path.basename(filepath)
  url = f"{BASE_URL}{REQUEST_CREATE_PATH.format(catalog_id=NEW_CATALOG_ID)}"

  with open(filepath, "r", encoding="utf-8") as f:
    exported = json.load(f)

  req_date = get_req_date(exported)
  dp_id = exported.get("dpId")
  dp_ttl = exported.get("dpShortTitle")
  status = exported.get("screeningStatus")

  # Preserve all original payload fields (requestor, requestorEmailId, irbId, etc.)
  data = dict(exported)
  data.pop("id", None)

  resp = session.post(url, json=data)

  if resp.status_code not in (200, 201):
    print(f"[FAIL] {filename}: HTTP {resp.status_code}")
    return None

  try:
    result = resp.json()
  except ValueError:
    print(f"[FAIL] {filename}: Invalid JSON response")
    return None

  if isinstance(result, list):
    new_ids = [r.get("id") for r in result]
  else:
    new_ids = [result.get("id")]

  for new_id in new_ids:
    if SET_REQUEST_DATE and req_date:
      restore_request_date(new_id, req_date)

    if SET_DP and dp_id:
      dp_payloads = [
          {"id": dp_id},
          {"id": dp_id, "shortTitle": dp_ttl},
          {"dpId": dp_id},
          {"dpId": dp_id, "dpShortTitle": dp_ttl},
      ]
      try_put_endpoint(
          REQUEST_DP_PATH,
          new_id,
          dp_payloads,
          lambda r: r.get("dpId") == dp_id,
      )

    if APPLY_SCREENING and status and status != "PENDING":
      try_put_endpoint(
          REQUEST_SCREENING_PATH,
          new_id,
          screening_payloads(exported),
          lambda r: r.get("screeningStatus") == status,
      )

  formatted_ids = (
      ", ".join(map(str, new_ids)) if len(new_ids) > 1 else str(new_ids[0])
  )
  print(f"[OK] {filename} -> Imported as Request ID {formatted_ids}")
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
