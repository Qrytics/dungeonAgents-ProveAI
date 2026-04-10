"""M-11 — Game Loop: Message Queue.

Implements communication lag between agents.  Messages sent on turn N are
delivered on turn N + :data:`~packages.shared.constants.COMM_LAG_TURNS`.
"""

from __future__ import annotations

from apps.simulation.schemas.events import MessageEvent
from packages.shared.types import AgentID, TurnNumber


class MessageQueue:
    """Ordered in-memory queue that enforces per-agent communication lag.

    Enqueued :class:`~apps.simulation.schemas.events.MessageEvent` objects
    are held until their ``turn_delivered`` field matches the current turn.
    Each call to :meth:`deliver` consumes and removes all matching messages
    for the given recipient, ensuring one-time delivery.

    Example::

        queue = MessageQueue()
        queue.enqueue(event)          # event.turn_delivered == 3
        msgs = queue.deliver(3, "agent_b")   # returns [event.content]
        msgs = queue.deliver(3, "agent_b")   # returns [] — already consumed
    """

    def __init__(self) -> None:
        self._queue: list[MessageEvent] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(self, event: MessageEvent) -> None:
        """Store *event* for later delivery.

        The ``turn_delivered`` field on *event* must already be set to
        ``event.turn_sent + COMM_LAG_TURNS`` by the caller (typically the
        ``communicate`` tool in M-07).

        Parameters
        ----------
        event:
            The :class:`~apps.simulation.schemas.events.MessageEvent` to queue.
        """
        self._queue.append(event)

    def deliver(self, turn: TurnNumber, recipient: AgentID) -> list[str]:
        """Return and consume all messages due for *recipient* on *turn*.

        A message is due when ``event.turn_delivered == turn`` and
        ``event.recipient == recipient``.  Consumed messages are removed
        from the queue so they are never delivered twice.

        Parameters
        ----------
        turn:
            The current turn number.
        recipient:
            The agent ID to deliver messages to.

        Returns
        -------
        list[str]
            The ``content`` strings of all delivered messages, in the order
            they were enqueued.  Returns an empty list if no messages are due.
        """
        delivered: list[str] = []
        remaining: list[MessageEvent] = []

        for event in self._queue:
            if event.turn_delivered == turn and event.recipient == recipient:
                delivered.append(event.content)
            else:
                remaining.append(event)

        self._queue = remaining
        return delivered
