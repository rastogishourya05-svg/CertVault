"""Container entrypoint: no secrets, network, host directories or write access."""

import json
import resource
from pathlib import Path

from apps.api.processing import extract_pdf

resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
try:
    text = extract_pdf(Path("/input.pdf").read_bytes())
    print(json.dumps({"text": text}))
except Exception:
    # Never print document contents or parser diagnostics on failure.
    raise SystemExit(2) from None
