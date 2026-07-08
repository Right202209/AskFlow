from __future__ import annotations

import uuid
from datetime import datetime, timezone

from askflow.schemas.conversation import ConversationResponse


def test_conversation_response_shape():
    now = datetime.now(timezone.utc)
    response = ConversationResponse(
        id=uuid.uuid4(),
        status="active",
        title="Hello",
        last_message_preview="Latest reply",
        created_at=now,
        updated_at=now,
    )

    assert response.status == "active"
    assert response.title == "Hello"
    assert response.last_message_preview == "Latest reply"
