"""Production identity verifier, kept separate from local demonstration sessions."""

import uuid

import jwt


class SupabaseVerifier:
    def __init__(self, project_url: str):
        if not project_url.startswith("https://") or not project_url.endswith(".supabase.co"):
            raise ValueError("Configure an HTTPS Supabase project URL")
        self.issuer = project_url + "/auth/v1"
        self.jwks = jwt.PyJWKClient(
            self.issuer + "/.well-known/jwks.json", cache_keys=True, lifespan=300
        )

    def verify(self, token: str) -> str:
        signing_key = self.jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=self.issuer,
            options={"require": ["exp", "sub", "iss", "aud", "iat"]},
        )
        if claims.get("role") != "authenticated":
            raise jwt.InvalidTokenError("Authenticated user token required")
        return str(uuid.UUID(claims["sub"]))
