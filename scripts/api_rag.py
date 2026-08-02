"""Call the local FastAPI /rag endpoint from Make.

The script keeps JSON construction out of the Makefile so questions can contain
normal punctuation without shell quoting surprises.
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    """Post one direct-RAG request to the configured API URL."""
    api_url = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "question": os.environ.get(
            "QUESTION", "where is repository configuration validated?"
        ),
        "repository_path": os.environ.get("REPO_PATH", "."),
        "mode": os.environ.get("RAG_MODE", "auto"),
        "retrieval_mode": os.environ.get("RETRIEVAL_MODE", "dense"),
        "limit": int(os.environ.get("LIMIT", "5")),
    }
    request = Request(
        f"{api_url}/rag",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        sys.stderr.write(error.read().decode("utf-8"))
        sys.stderr.write("\n")
        return 1
    except URLError as error:
        sys.stderr.write(f"Could not reach {api_url}: {error.reason}\n")
        return 1
    parsed = json.loads(body)
    print(json.dumps(parsed, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
