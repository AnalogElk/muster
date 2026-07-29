#!/usr/bin/env python3
"""GraphQL probe: blocked-family org2 tasks in the portal tasks shape."""
import json
import os
import urllib.request

BASE = "https://cms.musterr.dev"


import sys  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client.directus_client import load_env  # noqa: E402


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]

query = """
query {
  os_tasks(
    filter: { status: { _in: ["blocked", "on_hold"] } }
    limit: 3
  ) {
    id
    name
    status
    priority
    due_date
    is_visible_to_client
    is_test_data
    responsibility
    points
    assigned_to { id first_name last_name }
    project { id name status organization { id name } }
  }
}
"""
r = urllib.request.Request(
    BASE + "/graphql",
    data=json.dumps({"query": query}).encode(),
    headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
)
with urllib.request.urlopen(r) as resp:
    out = json.load(resp)
print(json.dumps(out, indent=1))
