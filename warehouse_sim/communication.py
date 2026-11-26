"""Tick-based simulated communication system for warehouse agents."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    message_id: int
    sender: str
    receiver: str
    payload: Dict[str, Any]
    sent_tick: int
    delivery_tick: int
    delivered_tick: Optional[int] = None


class CommunicationSystem:
    """Simulates latency, outages, message delivery, and communication metrics."""

    def __init__(
        self,
        latency_ticks: int = 0,
        outage_start: Optional[int] = None,
        outage_end: Optional[int] = None,
    ):
        if latency_ticks < 0:
            raise ValueError("latency_ticks cannot be negative")

        if outage_start is not None and outage_end is not None:
            if outage_end <= outage_start:
                raise ValueError("outage_end must be greater than outage_start")

        self.latency_ticks = latency_ticks
        self.outage_start = outage_start
        self.outage_end = outage_end

        self._next_message_id = 1
        self._in_transit: List[Message] = []
        self._delivered: List[Message] = []

        self.messages_sent = 0
        self.messages_delivered = 0
        self.messages_delayed = 0
        self.messages_dropped = 0
        self.messages_held_by_outage = 0
        self._held_message_ids = set()

    def is_outage(self, tick: int) -> bool:
        """Returns True if the network is down at this tick."""
        if self.outage_start is None or self.outage_end is None:
            return False

        return self.outage_start <= tick < self.outage_end

    def send(
        self,
        sender: str,
        receiver: str,
        payload: Dict[str, Any],
        current_tick: int,
    ) -> Optional[Message]:
        """Create and schedule a message, or drop it during an outage."""
        self.messages_sent += 1

        if self.is_outage(current_tick):
            self.messages_dropped += 1
            return None

        delivery_tick = current_tick + self.latency_ticks

        message = Message(
            message_id=self._next_message_id,
            sender=sender,
            receiver=receiver,
            payload=payload.copy(),
            sent_tick=current_tick,
            delivery_tick=delivery_tick,
        )

        self._next_message_id += 1
        self._in_transit.append(message)

        if delivery_tick > current_tick:
            self.messages_delayed += 1

        return message

    def deliver_due(self, current_tick: int) -> List[Message]:
        """Deliver messages due now or earlier, unless an outage holds them."""
        if self.is_outage(current_tick):
            for message in self._in_transit:
                if message.delivery_tick <= current_tick:
                    if message.message_id not in self._held_message_ids:
                        self._held_message_ids.add(message.message_id)
                        self.messages_held_by_outage += 1
            return []

        ready = []
        remaining = []

        for message in self._in_transit:
            if message.delivery_tick <= current_tick:
                message.delivered_tick = current_tick
                ready.append(message)
            else:
                remaining.append(message)

        self._in_transit = remaining

        ready.sort(key=lambda message: (message.delivery_tick, message.message_id))

        self._delivered.extend(ready)
        self.messages_delivered += len(ready)

        return ready

    def get_metrics(self) -> Dict[str, int]:
        """Return a snapshot of communication statistics."""
        return {
            "messages_sent": self.messages_sent,
            "messages_delivered": self.messages_delivered,
            "messages_delayed": self.messages_delayed,
            "messages_dropped": self.messages_dropped,
            "messages_in_transit": len(self._in_transit),
            "messages_held_by_outage": self.messages_held_by_outage,
        }

    def get_in_transit_count(self) -> int:
        return len(self._in_transit)
