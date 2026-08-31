"""Cleanup helper: removes any TEST_/QA-prefixed leftovers created during QA runs."""
import requests
from conftest import API


def test_cleanup_qa_leftovers(client):
    removed = []
    for r in client.get(f"{API}/rentals").json():
        if (r.get("catatan") or "").startswith("TEST_") or (r.get("catatan") or "") == "qa":
            client.delete(f"{API}/rentals/{r['id']}")
            removed.append(("rental", r["id"]))
    for v in client.get(f"{API}/vehicles").json():
        if v["merek"].startswith(("TEST_", "QATest")):
            client.delete(f"{API}/vehicles/{v['id']}")
            removed.append(("vehicle", v["id"]))
    for c in client.get(f"{API}/customers").json():
        if c["nama"].startswith(("TEST_", "QA ")):
            client.delete(f"{API}/customers/{c['id']}")
            removed.append(("customer", c["id"]))
    print("cleaned:", removed)
    assert isinstance(removed, list)
