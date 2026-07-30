import pytest
from app.protocol.constants import CommandType, EventType
from app.protocol.models import ClientCommand, ServerEvent
from pydantic import ValidationError


def test_client_command_parses_wire_aliases() -> None:
    command = ClientCommand.model_validate(
        {
            "protocolVersion": 1,
            "commandId": "cmd_hello",
            "type": "session.hello",
            "roomId": "room_01JABC",
            "sessionToken": "opaque-random-token",
            "clientTime": 1_785_360_000_000,
            "payload": {"lastEventId": 1042},
        }
    )

    assert command.type is CommandType.SESSION_HELLO
    assert command.session_token.get_secret_value() == "opaque-random-token"
    assert command.model_dump()["commandId"] == "cmd_hello"
    assert "opaque-random-token" not in repr(command)


def test_server_event_serializes_wire_aliases() -> None:
    event = ServerEvent(
        event_id=1042,
        type=EventType.QUESTION_QUEUED,
        room_id="room_01JABC",
        server_time=1_785_360_000_123,
        caused_by_command_id="cmd_01JABC",
        payload={"questionId": "question_01JABC"},
    )

    assert event.model_dump() == {
        "protocolVersion": 1,
        "eventId": 1042,
        "type": "question.queued",
        "roomId": "room_01JABC",
        "serverTime": 1_785_360_000_123,
        "causedByCommandId": "cmd_01JABC",
        "payload": {"questionId": "question_01JABC"},
    }


def test_protocol_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ClientCommand.model_validate(
            {
                "commandId": "cmd_hello",
                "type": "session.hello",
                "roomId": "room_01JABC",
                "sessionToken": "token",
                "clientTime": 1,
                "payload": {},
                "unexpected": True,
            }
        )


def test_protocol_models_reject_unknown_command_type() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        ClientCommand.model_validate(
            {
                "commandId": "cmd_hello",
                "type": "unknown.command",
                "roomId": "room_01JABC",
                "sessionToken": "token",
                "clientTime": 1,
                "payload": {},
            }
        )


def test_protocol_models_reject_unsupported_body_version() -> None:
    with pytest.raises(ValidationError, match="Input should be 1"):
        ClientCommand.model_validate(
            {
                "protocolVersion": 2,
                "commandId": "cmd_hello",
                "type": "session.hello",
                "roomId": "room_01JABC",
                "sessionToken": "token",
                "clientTime": 1,
                "payload": {},
            }
        )


def test_client_command_requires_protocol_version() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        ClientCommand.model_validate(
            {
                "commandId": "cmd_hello",
                "type": "session.hello",
                "roomId": "room_01JABC",
                "sessionToken": "token",
                "clientTime": 1,
                "payload": {},
            }
        )
