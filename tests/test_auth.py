import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from apps.api.supabase_auth import SupabaseVerifier


def test_supabase_jwt_signature_issuer_audience_expiry_and_role(monkeypatch):
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key()
    verifier = SupabaseVerifier("https://example.supabase.co")
    monkeypatch.setattr(
        verifier.jwks, "get_signing_key_from_jwt", lambda token: SimpleNamespace(key=public)
    )
    claims = {
        "iss": "https://example.supabase.co/auth/v1",
        "aud": "authenticated",
        "sub": "11111111-1111-4111-8111-111111111111",
        "role": "authenticated",
        "exp": time.time() + 3600,
        "iat": time.time(),
    }
    token = jwt.encode(claims, private, algorithm="ES256")
    assert verifier.verify(token) == claims["sub"]
    for changes in [
        {"iss": "https://evil.example"},
        {"aud": "other"},
        {"exp": time.time() - 1},
        {"role": "service_role"},
    ]:
        with pytest.raises(jwt.InvalidTokenError):
            verifier.verify(jwt.encode({**claims, **changes}, private, algorithm="ES256"))
    other_key = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(jwt.InvalidSignatureError):
        verifier.verify(jwt.encode(claims, other_key, algorithm="ES256"))
