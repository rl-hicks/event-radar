"""Ephemeral signing fixtures; no private keys are written to disk."""

import json
import time
from io import BytesIO
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from event_radar.auth.config import AuthConfig
from event_radar.auth.verifier import SupabaseVerifier

CONFIG = AuthConfig("https://project.example.test", "sb_publishable_test")


def signing_fixture(
    monkeypatch: pytest.MonkeyPatch, algorithm: str = "ES256"
) -> tuple[Any, dict, SupabaseVerifier]:
    if algorithm == "ES256":
        key = ec.generate_private_key(ec.SECP256R1())
        public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update({"kid": "test-key", "alg": algorithm, "use": "sig"})
    monkeypatch.setattr(
        "urllib.request.OpenerDirector.open",
        lambda *a, **kw: BytesIO(json.dumps({"keys": [public]}).encode()),
    )
    claims = {
        "sub": str(uuid4()),
        "iss": CONFIG.issuer,
        "aud": "authenticated",
        "exp": int(time.time()) + 300,
        "role": "authenticated",
        "email": "verified@example.test",
    }
    return key, claims, SupabaseVerifier(CONFIG)


def signed(key: Any, claims: dict, algorithm: str = "ES256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": "test-key"})
