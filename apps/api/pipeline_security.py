"""Fail-closed antivirus and resource-limited, networkless container PDF parser."""

import json
import shutil
import socket
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path

from apps.api.domain import STORAGE_HARD_CAP as HARD_CAP
from apps.api.domain import PolicyError


class ScannerUnavailable(RuntimeError):
    pass


def scan(data: bytes, host: str, port: int):
    if not data or len(data) > HARD_CAP:
        raise PolicyError("Invalid document size")
    try:
        with socket.create_connection((host, port), timeout=10) as stream:
            stream.settimeout(30)
            stream.sendall(b"zINSTREAM\0")
            for offset in range(0, len(data), 65536):
                block = data[offset : offset + 65536]
                stream.sendall(struct.pack("!I", len(block)) + block)
            stream.sendall(struct.pack("!I", 0))
            result = b""
            while b"\0" not in result and len(result) < 1024:
                block = stream.recv(1024 - len(result))
                if not block:
                    break
                result += block
    except OSError as exc:
        raise ScannerUnavailable("Malware scanner unavailable; no file was stored") from exc
    if result != b"stream: OK\0":
        if b"FOUND" in result:
            raise PolicyError("Malware detected; file rejected")
        raise ScannerUnavailable("Malware scan could not be confirmed")


def isolated_extract(data: bytes, image: str) -> str:
    with tempfile.TemporaryDirectory(prefix="certvault-quarantine-") as directory:
        path = Path(directory) / "document.pdf"
        path.write_bytes(data)
        name = "certvault-parser-" + uuid.uuid4().hex
        docker = shutil.which("docker") or str(
            Path.home() / "AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe"
        )
        try:
            result = subprocess.run(
                [
                    docker,
                    "run",
                    "--rm",
                    "--name=" + name,
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--pids-limit=32",
                    "--memory=256m",
                    "--cpus=1",
                    "--user=65534:65534",
                    "--mount",
                    f"type=bind,source={path.resolve()},target=/input.pdf,readonly",
                    image,
                ],
                capture_output=True,
                timeout=35,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ScannerUnavailable("Isolated PDF processor unavailable") from exc
        finally:
            # Kill only this invocation's uniquely named container if the CLI timed out.
            try:
                subprocess.run(
                    [docker, "rm", "-f", name], capture_output=True, timeout=10, check=False
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        if result.returncode != 0 or len(result.stdout) > 400000:
            raise PolicyError("PDF requires review; isolated processing did not succeed")
        try:
            text = json.loads(result.stdout)["text"]
            if not isinstance(text, str) or not text.strip() or len(text) > 50000:
                raise ValueError()
            return text
        except (ValueError, KeyError, TypeError) as exc:
            raise PolicyError("Invalid isolated processor output") from exc
