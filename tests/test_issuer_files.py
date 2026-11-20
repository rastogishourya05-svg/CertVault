"""Exercise the issuer transport without requesting third-party credentials or files."""

import io
import socket
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from apps.api import issuer_files as links
from apps.api.domain import HardLimitExceeded


@pytest.mark.parametrize(
    ("status", "headers", "error"),
    [
        (200, b"Content-Length: 3", None),
        (302, b"Location: http://localhost", links.LinkUnavailable),
        (200, b"Content-Length: 50000001", HardLimitExceeded),
        (200, b"Transfer-Encoding: chunked", links.LinkUnavailable),
    ],
)
def test_pinned_issuer_response(monkeypatch, status, headers, error):
    host = links.HOST
    peer = ("8.8.8.8", 443)
    raw, tls, context = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(
        links.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", peer)],
    )
    monkeypatch.setattr(links.socket, "socket", lambda *args: nullcontext(raw))
    monkeypatch.setattr(links.ssl, "create_default_context", lambda: context)
    context.wrap_socket.return_value = nullcontext(tls)
    tls.makefile.return_value = io.BytesIO(
        f"HTTP/1.1 {status} Test\r\n".encode() + headers + b"\r\n\r\nabc"
    )
    url = f"https://{host}/pdf/UC-demo123.pdf"
    if error:
        with pytest.raises(error):
            links.fetch_file(url)
    else:
        assert links.fetch_file(url) == b"abc"
    raw.connect.assert_called_once_with(peer)
    context.wrap_socket.assert_called_once_with(raw, server_hostname=host)
    assert b"Authorization" not in tls.sendall.call_args.args[0]
