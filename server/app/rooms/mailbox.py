import asyncio
from dataclasses import dataclass, field

from app.protocol.models import ServerEvent


@dataclass(slots=True)
class ConnectionMailbox:
    id: str
    player_id: str
    queue: asyncio.Queue[ServerEvent] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    closed: asyncio.Event = field(default_factory=asyncio.Event)

    def offer(self, event: ServerEvent) -> bool:
        if self.closed.is_set():
            return False
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.closed.set()
            return False
        return True
