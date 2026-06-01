import json
import urllib.request
import os
from pathlib import Path

token = os.environ.get("GH_TOKEN", "")
if not token:
    print("ERROR: GH_TOKEN not set. Run: export GH_TOKEN=<your-github-token>")
    exit(1)

project_dir = Path(__file__).resolve().parents[2]
with open(project_dir / "GEM5_ISSUE_REPORT.md", encoding="utf-8") as f:
    body = f.read()

data = json.dumps({
    "title": "sim/power: ThermalModel intermediate nodes initialized to 0 K (absolute zero), causing unphysical junction cooling",
    "body": body,
    "labels": ["bug"]
}).encode()

req = urllib.request.Request(
    "https://api.github.com/repos/gem5/gem5/issues",
    data=data,
    headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
    }
)

with urllib.request.urlopen(req) as r:
    resp = json.loads(r.read())
    print("Issue created:", resp["html_url"])
