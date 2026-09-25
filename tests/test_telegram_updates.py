from datetime import UTC

import pytest
from pydantic import SecretStr

import event_radar.main as main_module
from event_radar.models.direction import Direction, DirectionType
from event_radar.services.telegram_updates import (
    is_authorized_owner_direction,
    parse_direction,
)

OWNER_USER_ID = 111_111
OWNER_CHAT_ID = 222_222
OTHER_USER_ID = 333_333
OTHER_CHAT_ID = 444_444


def telegram_update(
    *,
    update_id: int = 10,
    user_id: int = OWNER_USER_ID,
    chat_id: int = OWNER_CHAT_ID,
    chat_type: str = "private",
    text: str = "/temp Private test",
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "from": {"id": user_id},
            "chat": {"id": chat_id, "type": chat_type},
            "text": text,
        },
    }


@pytest.mark.parametrize(
    ("user_id", "chat_id", "chat_type", "expected"),
    [
        pytest.param(
            OWNER_USER_ID,
            OWNER_CHAT_ID,
            "private",
            True,
            id="owner-user-owner-private-chat",
        ),
        pytest.param(
            OWNER_USER_ID,
            OTHER_CHAT_ID,
            "private",
            False,
            id="owner-user-wrong-chat",
        ),
        pytest.param(
            OTHER_USER_ID,
            OWNER_CHAT_ID,
            "private",
            False,
            id="wrong-user-owner-chat",
        ),
        pytest.param(
            OTHER_USER_ID,
            OTHER_CHAT_ID,
            "private",
            False,
            id="wrong-user-wrong-chat",
        ),
        pytest.param(
            OWNER_USER_ID,
            OWNER_CHAT_ID,
            "group",
            False,
            id="owner-ids-group-chat",
        ),
        pytest.param(
            OWNER_USER_ID,
            OWNER_CHAT_ID,
            "supergroup",
            False,
            id="owner-ids-supergroup-chat",
        ),
    ],
)
def test_owner_authorization_requires_both_ids_and_private_chat(
    user_id: int,
    chat_id: int,
    chat_type: str,
    expected: bool,
) -> None:
    direction = parse_direction(
        telegram_update(user_id=user_id, chat_id=chat_id, chat_type=chat_type)
    )

    assert direction is not None
    assert (
        is_authorized_owner_direction(
            direction,
            owner_user_id=OWNER_USER_ID,
            owner_chat_id=str(OWNER_CHAT_ID),
        )
        is expected
    )


@pytest.mark.parametrize(
    ("text", "expected_type", "expected_text"),
    [
        pytest.param(
            "/temp Prefer something outdoors this weekend.",
            DirectionType.TEMPORARY,
            "Prefer something outdoors this weekend.",
            id="plain-temp-command",
        ),
        pytest.param(
            "/permanent Workshops are especially valuable.",
            DirectionType.PERMANENT,
            "Workshops are especially valuable.",
            id="plain-permanent-command",
        ),
        pytest.param(
            "/temp@northbay_weekend_bot Keep Sunday flexible.",
            DirectionType.TEMPORARY,
            "Keep Sunday flexible.",
            id="addressed-command",
        ),
    ],
)
def test_private_command_syntax(
    text: str,
    expected_type: DirectionType,
    expected_text: str,
) -> None:
    direction = parse_direction(telegram_update(text=text))

    assert direction is not None
    assert direction.type is expected_type
    assert direction.text == expected_text
    assert direction.telegram_user_id == OWNER_USER_ID
    assert direction.telegram_chat_id == OWNER_CHAT_ID
    assert direction.telegram_chat_type == "private"
    assert direction.created_at.tzinfo is UTC


@pytest.mark.parametrize(
    "text",
    [
        "Just a normal private message.",
        "/temp",
        "/permanent",
        "/unknown Ignore this.",
    ],
)
def test_unrelated_or_incomplete_messages_are_ignored(text: str) -> None:
    assert parse_direction(telegram_update(text=text)) is None


def test_legacy_stored_direction_without_chat_metadata_still_loads() -> None:
    direction = Direction.model_validate(
        {
            "type": "permanent",
            "text": "Prefer participatory activities.",
            "telegram_user_id": OWNER_USER_ID,
            "created_at": "2026-09-24T12:00:00Z",
            "update_id": 1,
        }
    )

    assert direction.telegram_chat_id is None
    assert direction.telegram_chat_type is None


@pytest.mark.asyncio
async def test_read_directions_persists_only_authorized_private_commands_and_advances_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates = [
        telegram_update(update_id=80, text="/temp Authorized temporary"),
        telegram_update(update_id=81, text="/permanent Authorized permanent"),
        telegram_update(
            update_id=82,
            chat_id=OTHER_CHAT_ID,
            text="/temp Wrong chat",
        ),
        telegram_update(
            update_id=83,
            user_id=OTHER_USER_ID,
            text="/permanent Wrong user",
        ),
        telegram_update(
            update_id=84,
            chat_type="supergroup",
            text="/temp Non-private",
        ),
        telegram_update(update_id=85, text="Unrelated message"),
    ]
    requested_offsets: list[int | None] = []

    class FakeTelegramUpdateClient:
        def __init__(self, *, bot_token: str, timeout_seconds: float) -> None:
            assert bot_token == "test-token"
            assert timeout_seconds == main_module.settings.request_timeout_seconds

        async def get_updates(self, offset: int | None = None) -> list[dict[str, object]]:
            requested_offsets.append(offset)
            return updates

    saved_directions: list[Direction] = []
    saved_offsets: list[int] = []
    monkeypatch.setattr(main_module, "TelegramUpdateClient", FakeTelegramUpdateClient)
    monkeypatch.setattr(main_module, "load_offset", lambda: 79)
    monkeypatch.setattr(main_module, "save_direction", saved_directions.append)
    monkeypatch.setattr(main_module, "save_offset", saved_offsets.append)
    monkeypatch.setattr(main_module.settings, "telegram_bot_token", SecretStr("test-token"))
    monkeypatch.setattr(main_module.settings, "telegram_owner_user_id", OWNER_USER_ID)
    monkeypatch.setattr(main_module.settings, "telegram_chat_id", str(OWNER_CHAT_ID))

    await main_module.read_directions()

    assert requested_offsets == [79]
    assert [direction.text for direction in saved_directions] == [
        "Authorized temporary",
        "Authorized permanent",
    ]
    assert [direction.type for direction in saved_directions] == [
        DirectionType.TEMPORARY,
        DirectionType.PERMANENT,
    ]
    assert all(direction.telegram_chat_id == OWNER_CHAT_ID for direction in saved_directions)
    assert all(direction.telegram_chat_type == "private" for direction in saved_directions)
    assert saved_offsets == [86]
