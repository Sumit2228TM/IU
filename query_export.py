import requests
import json
import os

BASE_URL   = "https://test.openspecimen.org/rest/ng"
LOGIN_NAME = ""
PASSWORD   = ""
DOMAIN     = "openspecimen"

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})

auth_response = session.post(f"{BASE_URL}/sessions", json={ 
    "loginName": LOGIN_NAME,
    "password":  PASSWORD,
    "domain":    DOMAIN
})
    
auth = auth_response.json()
session.headers.update({"X-OS-API-TOKEN": auth["token"]})

if auth_response.status_code == 200:
    print("Auth Successful")
else:
    print("Unauth Access")
    exit()

QUERY_IDS = [621, 381, 23]
OUT_DIR = "./exported_queries"

QUERY_EXPORT_PATH = "/saved-queries/{id}"

def download_query(query_id, out_dir):
    url = f"{BASE_URL}{QUERY_EXPORT_PATH.format(id=query_id)}"
    resp = session.get(url)
 
    if resp.status_code != 200:
        print(f"  [FAIL] Query {query_id}: HTTP {resp.status_code} - {resp.text[:200]}")
        return False
 
    try:
        data = resp.json()
    except ValueError:
        print(f"  [FAIL] Query {query_id}: response was not valid JSON")
        return False
 
    out_path = os.path.join(out_dir, f"query_{query_id}.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
 
    print(f"  [OK] Query {query_id} -> {out_path}")
    return True

os.makedirs(OUT_DIR, exist_ok=True)
 
ok, fail = 0, 0
for qid in QUERY_IDS:
    if download_query(qid, OUT_DIR):
        ok += 1
    else:
        fail += 1
 
print(f"\nDone. {ok} succeeded, {fail} failed. Files saved in: {OUT_DIR}")
