from pydantic import Field

from app.protocol.models import ProtocolModel


class EmptyPayload(ProtocolModel):
    pass


class SessionHelloPayload(ProtocolModel):
    last_event_id: int = Field(default=0, ge=0)
    client_version: str = Field(min_length=1, max_length=40)


class DiscussionSendPayload(ProtocolModel):
    content: str = Field(min_length=1, max_length=180)


class QuestionSubmitPayload(ProtocolModel):
    client_question_id: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=180)


class QuestionCancelPayload(ProtocolModel):
    question_id: str = Field(min_length=1, max_length=80)


class PlayerTargetPayload(ProtocolModel):
    player_id: str = Field(min_length=1, max_length=80)


class RematchVotePayload(ProtocolModel):
    agree: bool = Field(strict=True)


class ConclusionSubmitPayload(ProtocolModel):
    content: str = Field(min_length=1, max_length=800)
    accept_detail_penalty: bool = Field(default=False, strict=True)
