"""tests/test_billing_checkout_allow.py — the admin route that manages who may start a Pro checkout (test mode on prod).

Reasoning:
- api/billing_gate.py lets only accounts in a Redis set start a checkout where `stripe_checkout_restricted` is on. This
  route (reached by scripts/billing_checkout_allow.py) is how an operator changes that set without Redis access: it
  finds the account by its address and keeps only the opaque account identifier in the set.
- What is pinned: admin token only (the matrix of refused credentials in tests/test_education_admin.py covers it);
  a DRY RUN unless `apply`; the address is matched whatever its case and is never in an answer or a log line; an
  unknown address is a 404; list, remove and clear work; an unreachable set is a 503 with nothing changed; the
  answer says whether the gate is on in this deployment; and what the route puts in the set is what the gate reads.
- Real rows in an in-memory database and the real application, like tests/test_education_admin.py, whose fixtures
  are reused; Redis is a fake that has just the set commands.
"""

from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs

from api import billing_gate
from tests import test_education_admin as admin_tests
from tests.test_education_admin import ADMIN, CHECKOUT_ALLOW, add_user

db = admin_tests.db
client = admin_tests.client
mail = admin_tests.mail
redis = admin_tests.redis

pytestmark = pytest.mark.asyncio

ADDRESS = "ada@uni.ac.uk"  # add_user(db, "ada")
KEY = billing_gate.CHECKOUT_ALLOW_KEY


class FakeSetRedis:
    """Just the set commands the allow list uses."""

    def __init__(self) -> None:
        self.sets: dict[str, set[str]] = {}
        self.down = False

    def _up(self) -> None:
        if self.down:
            raise ConnectionError("redis is down")

    async def sismember(self, key: str, member: str) -> bool:
        self._up()
        return member in self.sets.get(key, set())

    async def smembers(self, key: str) -> set[str]:
        self._up()
        return set(self.sets.get(key, set()))

    async def sadd(self, key: str, member: str) -> int:
        self._up()
        self.sets.setdefault(key, set()).add(member)
        return 1

    async def srem(self, key: str, member: str) -> int:
        self._up()
        self.sets.get(key, set()).discard(member)
        return 1

    async def delete(self, key: str) -> int:
        self._up()
        self.sets.pop(key, None)
        return 1


@pytest.fixture
def allow_set(monkeypatch: pytest.MonkeyPatch) -> FakeSetRedis:
    fake = FakeSetRedis()
    monkeypatch.setattr(billing_gate, "_redis", lambda: fake)
    return fake


async def call(client, **body: Any):
    return await client.post(CHECKOUT_ALLOW, json=body, headers=ADMIN)


async def test_allow_is_a_dry_run_unless_told_to_apply(client, db, allow_set) -> None:
    await add_user(db, "ada")
    response = await call(client, action="allow", email=ADDRESS)
    assert response.status_code == 200
    assert response.json() == {
        "action": "allow",
        "applied": False,
        "restricted": False,
        "account_id": "ext-ada",
        "tier": "free",
        "was_allowed": False,
        "members": 0,
        "account_ids": [],
    }
    assert allow_set.sets == {}


async def test_allow_with_apply_puts_the_account_id_in_the_set_and_the_gate_reads_it(
    client, db, allow_set, monkeypatch
) -> None:
    await add_user(db, "ada")
    await add_user(db, "grace")
    response = await call(client, action="allow", email=ADDRESS, apply=True)
    assert response.json()["applied"] is True and response.json()["members"] == 1
    assert allow_set.sets == {KEY: {"ext-ada"}}  # the identifier, never the address
    monkeypatch.setattr(billing_gate.cfg, "stripe_checkout_restricted", True)
    assert await billing_gate.checkout_allowed("ext-ada") is True
    assert await billing_gate.checkout_allowed("ext-grace") is False


async def test_the_address_is_matched_whatever_its_case_and_never_echoed(
    client, db, allow_set
) -> None:
    await add_user(db, "ada")
    response = await call(client, action="allow", email="  ADA@Uni.AC.uk ", apply=True)
    assert response.status_code == 200 and allow_set.sets == {KEY: {"ext-ada"}}
    assert "uni.ac.uk" not in response.text.lower()


async def test_an_unknown_address_is_a_404_and_is_not_echoed(client, db, allow_set) -> None:
    response = await call(client, action="allow", email="nobody@uni.ac.uk", apply=True)
    assert response.status_code == 404 and "nobody" not in response.text
    assert allow_set.sets == {}


async def test_remove_is_a_dry_run_unless_applied_and_then_takes_the_account_out(
    client, db, allow_set
) -> None:
    await add_user(db, "ada")
    allow_set.sets[KEY] = {"ext-ada", "ext-other"}
    dry = await call(client, action="remove", email=ADDRESS)
    assert dry.json()["was_allowed"] is True and dry.json()["members"] == 2
    assert allow_set.sets[KEY] == {"ext-ada", "ext-other"}
    done = await call(client, action="remove", email=ADDRESS, apply=True)
    assert done.json()["applied"] is True and done.json()["members"] == 1
    assert allow_set.sets[KEY] == {"ext-other"}


async def test_list_returns_the_identifiers_sorted_and_no_address(client, db, allow_set) -> None:
    await add_user(db, "ada")
    allow_set.sets[KEY] = {"ext-b", "ext-a"}
    response = await call(client, action="list")
    assert response.status_code == 200
    assert response.json()["account_ids"] == ["ext-a", "ext-b"]
    assert response.json()["members"] == 2 and response.json()["applied"] is False
    assert "@" not in response.text


async def test_clear_counts_then_empties_the_set(client, allow_set) -> None:
    allow_set.sets[KEY] = {"ext-a", "ext-b", "ext-c"}
    dry = await call(client, action="clear")
    assert dry.json()["members"] == 3 and dry.json()["applied"] is False
    assert allow_set.sets[KEY] == {"ext-a", "ext-b", "ext-c"}
    done = await call(client, action="clear", apply=True)
    assert done.json()["members"] == 0 and done.json()["applied"] is True
    assert allow_set.sets == {}


async def test_the_answer_says_whether_the_gate_is_on(client, allow_set, monkeypatch) -> None:
    monkeypatch.setattr(billing_gate.cfg, "stripe_checkout_restricted", True)
    assert (await call(client, action="list")).json()["restricted"] is True
    monkeypatch.setattr(billing_gate.cfg, "stripe_checkout_restricted", False)
    assert (await call(client, action="list")).json()["restricted"] is False


@pytest.mark.parametrize("action", ["allow", "remove"])
async def test_allow_and_remove_need_an_email(client, allow_set, action) -> None:
    assert (await call(client, action=action)).status_code == 422


@pytest.mark.parametrize("action", ["list", "clear"])
async def test_list_and_clear_refuse_an_email(client, allow_set, action) -> None:
    assert (await call(client, action=action, email=ADDRESS)).status_code == 422


async def test_an_unknown_action_is_a_422(client, allow_set) -> None:
    assert (await call(client, action="wipe")).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"action": "list"},
        {"action": "clear", "apply": True},
        {"action": "allow", "email": ADDRESS, "apply": True},
        {"action": "remove", "email": ADDRESS, "apply": True},
    ],
)
async def test_an_unreachable_allow_list_is_a_503_and_changes_nothing(
    client, db, allow_set, body
) -> None:
    await add_user(db, "ada")
    allow_set.down = True
    response = await client.post(CHECKOUT_ALLOW, json=body, headers=ADMIN)
    assert response.status_code == 503
    assert response.json()["detail"] == "The allow list could not be reached."
    allow_set.down = False
    assert allow_set.sets == {}


async def test_no_redis_client_is_a_503(client, db, monkeypatch) -> None:
    await add_user(db, "ada")
    monkeypatch.setattr(billing_gate, "_redis", lambda: None)
    response = await call(client, action="allow", email=ADDRESS, apply=True)
    assert response.status_code == 503


async def test_a_change_is_logged_with_the_operator_and_the_account_id_but_never_the_address(
    client, db, allow_set
) -> None:
    await add_user(db, "ada")
    with capture_logs() as logs:
        await call(client, action="allow", email=ADDRESS, apply=True)
    changed = [entry for entry in logs if entry["event"] == "billing_checkout_allow_changed"]
    assert len(changed) == 1
    assert changed[0]["operator"] == "operator" and changed[0]["account_id"] == "ext-ada"
    assert "uni.ac.uk" not in repr(logs)
