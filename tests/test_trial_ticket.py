"""tests/test_trial_ticket.py — a trial ticket is accepted only by the lane, and refused by everything else.

Reasoning:
- CLAUDE.md 3.5 holds only while no route takes a ticket for an account credential. The mechanism is the `aud`
  claim: python-jose refuses a token that has an audience at a decoder that names none, which is every existing
  HTTP route (decode_token_payload), and the stream decoder names a different one.
- The converse does NOT come for free. A decoder that names an audience still lets through a token with no `aud`
  at all, which is every session JWT, so decode_ticket checks the claim itself. The tests below pin the four
  tokens the plan names (ticket, session JWT, API key, stream token) against the lane, and the ticket against
  an ordinary route, the key-management route and the stream decoder.
- No mocking: the tokens are signed with the real helpers and decoded by the real code.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from jose import JWTError, jwt

from api.middleware import trial as lane
from api.middleware.auth import (
    create_access_token,
    create_stream_token,
    decode_stream_payload,
    decode_token_payload,
)
from api.middleware.trial import TRIAL_AUDIENCE, decode_ticket, mint_ticket
from main import create_app

APP = create_app()


def _sign(claims: dict[str, Any]) -> str:
    return str(jwt.encode(claims, lane.cfg.jwt_secret, algorithm=lane.cfg.jwt_algorithm))


def _claims(**changes: Any) -> dict[str, Any]:
    now = int(time.time())
    base: dict[str, Any] = {
        "aud": TRIAL_AUDIENCE,
        "jti": "abcdefghijklmnopqrstuv",
        "iat": now,
        "exp": now + 3600,
    }
    base.update(changes)
    return {key: value for key, value in base.items() if value is not None}


def test_a_minted_ticket_has_an_audience_a_random_id_a_72_hour_life_and_no_subject_or_tier() -> (
    None
):
    token, ticket = mint_ticket()
    claims = jwt.get_unverified_claims(token)
    assert claims["aud"] == "pyvar-trial"
    assert set(claims) == {"aud", "jti", "iat", "exp"}  # no sub, no tier, nothing else
    assert claims["exp"] - claims["iat"] == 72 * 3600
    assert ticket.jti == claims["jti"] and len(claims["jti"]) >= 16
    other, other_ticket = mint_ticket()
    assert other_ticket.jti != ticket.jti


def test_decode_ticket_accepts_a_fresh_ticket() -> None:
    token, ticket = mint_ticket()
    assert decode_ticket(token) == ticket


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(create_access_token("someone", "enterprise"), id="session JWT (no aud)"),
        pytest.param(create_stream_token("someone", "task-1"), id="stream token (another aud)"),
        pytest.param("pyvar_" + "a" * 43, id="API key"),
        pytest.param("", id="empty"),
        pytest.param(_sign(_claims(aud="pyvar-admin")), id="another audience"),
        pytest.param(_sign(_claims(aud=[TRIAL_AUDIENCE, "other"])), id="audience list"),
        pytest.param(_sign(_claims(aud=None)), id="no audience at all"),
        pytest.param(_sign(_claims(sub="someone")), id="a subject"),
        pytest.param(_sign(_claims(tier="pro")), id="a tier claim"),
        pytest.param(_sign(_claims(jti=None)), id="no jti"),
        pytest.param(_sign(_claims(jti="short")), id="a short jti"),
        pytest.param(_sign(_claims(jti="x" * 16 + "!")), id="a jti with a bad character"),
        pytest.param(_sign(_claims(exp=int(time.time()) - 10)), id="expired"),
    ],
)
def test_decode_ticket_refuses_everything_that_is_not_a_ticket(token: str) -> None:
    with pytest.raises(JWTError):
        decode_ticket(token)


def test_decode_ticket_refuses_a_ticket_signed_with_another_secret() -> None:
    forged = str(jwt.encode(_claims(), "not-the-signing-secret", algorithm="HS256"))
    with pytest.raises(JWTError):
        decode_ticket(forged)


def test_python_jose_alone_would_let_a_session_jwt_through_which_is_why_the_claim_is_checked() -> (
    None
):
    """The reason decode_ticket checks `aud` itself (pinned so a library change is noticed)."""
    session = create_access_token("someone", "enterprise")
    payload = jwt.decode(
        session,
        lane.cfg.jwt_secret,
        algorithms=[lane.cfg.jwt_algorithm],
        audience=TRIAL_AUDIENCE,
    )
    assert "aud" not in payload  # accepted by the library; refused only by decode_ticket


def test_every_existing_decoder_refuses_a_ticket() -> None:
    token, _ = mint_ticket()
    with pytest.raises(JWTError):
        decode_token_payload(token)  # every HTTP route
    with pytest.raises(JWTError):
        decode_stream_payload(token, "task-1")  # the WebSocket route


async def test_an_ordinary_route_and_the_key_routes_answer_401_to_a_ticket() -> None:
    token, _ = mint_ticket()
    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as client:
        compute = await client.post(
            "/api/v1/market-risk/parametric_delta_normal_var", json={}, headers=headers
        )
        result = await client.get("/api/v1/var/result/some-task", headers=headers)
        keys = await client.post("/api/v1/auth/api-keys", json={"name": "x"}, headers=headers)
        stream_token = await client.post("/api/v1/var/stream-token/some-task", headers=headers)
    assert compute.status_code == 401
    assert result.status_code == 401
    assert keys.status_code == 401
    assert stream_token.status_code == 401
