"""Local synthetic antivirus/parser smoke; no accounts, databases or cloud resources."""

import json
import os
import socket
import subprocess
import time
import uuid
from unittest.mock import patch

from apps.api.domain import PolicyError
from apps.api.pipeline_security import isolated_extract, scan
from apps.api.processing import sample_pdf


def main():
    pdf = sample_pdf("Local security smoke", "Synthetic test issuer")
    deadline = time.monotonic() + 180
    print("Waiting for local antivirus signatures and readiness...", flush=True)
    while True:
        try:
            scan(pdf, "127.0.0.1", 3310)
            break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise SystemExit("ClamAV did not become ready within 180 seconds") from None
            time.sleep(2)
    with socket.create_connection(("127.0.0.1", 3310), timeout=5) as stream:
        stream.sendall(b"zVERSION\0")
        version = stream.recv(512).decode().strip("\0\n")
    print("Antivirus ready:", version, flush=True)
    # Standard harmless antivirus test signature, held only in memory.
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    try:
        scan(eicar, "127.0.0.1", 3310)
    except PolicyError:
        print("Clean PDF accepted; EICAR test signature rejected", flush=True)
    else:
        raise SystemExit("Antivirus failed the harmless EICAR check")

    real_run = subprocess.run
    checks = {}

    def observed_run(command, **kwargs):
        if len(command) < 2 or command[1] != "run":
            return real_run(command, **kwargs)
        # Retain only this test container until inspection; the application's finally
        # block still removes it. All production security flags remain unchanged.
        retained = [arg for arg in command if arg != "--rm"]
        result = real_run(retained, **kwargs)
        name = next(arg.split("=", 1)[1] for arg in command if arg.startswith("--name="))
        inspection = real_run(
            [command[0], "inspect", name], capture_output=True, check=True, timeout=10
        )
        container = json.loads(inspection.stdout)[0]
        host, config = container["HostConfig"], container["Config"]
        env_names = {entry.split("=", 1)[0] for entry in config.get("Env", [])}
        expected_env = {"PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256"}
        checks.update(
            {
                "network_none": host["NetworkMode"] == "none",
                "non_root": config["User"] == "65534:65534",
                "read_only_root": host["ReadonlyRootfs"],
                "no_capabilities": host["CapDrop"] == ["ALL"] and not host.get("CapAdd"),
                "no_privilege_escalation": "no-new-privileges" in host["SecurityOpt"]
                and not host["Privileged"],
                "memory_256_mib": host["Memory"] == 256 * 1024 * 1024,
                "cpu_one": host["NanoCpus"] == 1000000000,
                "pids_32": host["PidsLimit"] == 32,
                "only_read_only_pdf_mount": len(container["Mounts"]) == 1
                and container["Mounts"][0]["Destination"] == "/input.pdf"
                and not container["Mounts"][0]["RW"],
                "no_secrets_or_host_environment": env_names <= expected_env,
            }
        )
        # Exercise restrictions inside the same image with the exact runtime flags.
        probe = [arg for arg in command if not arg.startswith("--name=")]
        probe.insert(2, "--name=certvault-security-probe-" + uuid.uuid4().hex)
        probe.insert(-1, "--entrypoint=python")
        probe += [
            "-B",
            "-c",
            "import os,json;from pathlib import Path; s=Path('/proc/self/status').read_text();print(json.dumps({'uid':os.getuid(),'read_only':bool(os.statvfs('/').f_flag & os.ST_RDONLY),'interfaces':os.listdir('/sys/class/net'),'caps_zero':next(x for x in s.splitlines() if x.startswith('CapEff:')).split()[1]=='0000000000000000','no_new_privs':'NoNewPrivs:\\t1' in s,'host_canary_absent':'CERTVAULT_SECURITY_CANARY' not in os.environ}))",
        ]
        probe_name = next(arg.split("=", 1)[1] for arg in probe if arg.startswith("--name="))
        try:
            output = real_run(probe, capture_output=True, check=True, timeout=15)
            runtime = json.loads(output.stdout)
            checks["runtime_restrictions"] = (
                runtime["uid"] == 65534
                and runtime["read_only"]
                and runtime["interfaces"] == ["lo"]
                and runtime["caps_zero"]
                and runtime["no_new_privs"]
                and runtime["host_canary_absent"]
            )
        finally:
            real_run(
                [command[0], "rm", "-f", probe_name], capture_output=True, timeout=10, check=False
            )
        return result

    os.environ["CERTVAULT_SECURITY_CANARY"] = "synthetic-not-a-secret"
    try:
        with patch("apps.api.pipeline_security.subprocess.run", side_effect=observed_run):
            text = isolated_extract(pdf, "certvault-parser:dev")
    finally:
        os.environ.pop("CERTVAULT_SECURITY_CANARY", None)
    assert "Local security smoke" in text
    # Exercise the actual parser's fail-closed path too.
    try:
        isolated_extract(b"not a PDF", "certvault-parser:dev")
    except PolicyError:
        checks["malformed_pdf_rejected"] = True
    else:
        checks["malformed_pdf_rejected"] = False
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit("Security restriction verification failed")
    print("Local security smoke passed. No database or external account was accessed.")


if __name__ == "__main__":
    main()
