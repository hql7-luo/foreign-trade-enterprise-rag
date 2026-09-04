"""Check a running synthetic demo without printing passwords or access tokens."""

import argparse
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend", default="http://127.0.0.1:3000")
    parser.add_argument("--credentials", type=Path, required=True)
    args = parser.parse_args()
    accounts = dict(line.split(": ", 1) for line in args.credentials.read_text().splitlines())
    with httpx.Client(base_url=args.url, timeout=20) as client:
        for path in ["/api/health/live", "/api/health/ready"]:
            assert client.get(path).status_code == 200, path
        response = client.post(
            "/api/auth/login", json={"username": "employee", "password": accounts["employee"]}
        )
        assert response.status_code == 200, "login"
        headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        result = client.post(
            "/api/query", headers=headers, json={"question": "NSTR-VESSEL-731 material?"}
        ).json()
        assert "18/8 stainless steel" in result["answer"] and result["sources"]
        evidence = client.get("/api/evidence/" + result["sources"][0]["chunk_id"], headers=headers)
        assert evidence.status_code == 200 and "18/8 stainless steel" in evidence.json()["excerpt"]
        assert client.get("/api/knowledge/fact-changes", headers=headers).status_code == 403
        assert client.get("/api/products").status_code == 401
        assert httpx.get(args.frontend, timeout=20).status_code == 200, "frontend"
    print("Smoke passed: readiness, employee query, evidence and role boundaries")


if __name__ == "__main__":
    main()
