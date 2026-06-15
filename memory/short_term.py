"""Short-Term Memory for AgentFlow

Stores conversation context within a single session.
This is a stub implementation - see docs/limitations.md for details
on what a production memory system would look like.

Design decision: Short-term memory is scoped to a session ID.
Different sessions have isolated memory.
"""

import time
from typing import Any, Optional
from collections import deque
from dataclasses import dataclass, field


@dataclass
class MemoryEntry:
    """A single memory entry."""
    content: str
    metadata: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    agent: str = "unknown"
    importance: float = 1.0  # 0-1 scale


class ShortTermMemory:
    """Session-scoped memory that resets on new session.

    Limitations (see docs/limitations.md):
    - Resets between sessions
    - No semantic search (just recency-based retrieval)
    - No importance weighting (stub only)
    - No persistence between restarts
    """

    def __init__(self, session_id: str, max_entries: int = 50):
        self.session_id = session_id
        self.max_entries = max_entries
        self._memory: deque[MemoryEntry] = deque(maxlen=max_entries)

    def add(
        self,
        content: str,
        agent: str = "unknown",
        metadata: Optional[dict[str, Any]] = None,
        importance: float = 1.0
    ) -> None:
        """Add entry to short-term memory."""
        entry = MemoryEntry(
            content=content,
            metadata=metadata or {},
            agent=agent,
            importance=importance
        )
        self._memory.append(entry)

    def get_recent(self, n: int = 5) -> list[MemoryEntry]:
        """Get the n most recent memory entries."""
        entries = list(self._memory)
        return entries[-n:] if len(entries) >= n else entries

    def get_by_agent(self, agent: str) -> list[MemoryEntry]:
        """Get all entries from a specific agent."""
        return [e for e in self._memory if e.agent == agent]

    def get_context_string(self, n: int = 5) -> str:
        """Get recent context as formatted string for prompts."""
        recent = self.get_recent(n)
        if not recent:
            return "No previous context in this session."

        lines = [f"[Session context - {len(recent)} recent entries]"]
        for entry in recent:
            lines.append(f"- [{entry.agent}]: {entry.content[:200]}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all memory entries."""
        self._memory.clear()

    @property
    def size(self) -> int:
        """Number of entries currently stored."""
        return len(self._memory)

    def to_dict(self) -> dict[str, Any]:
        """Export memory as dictionary."""
        return {
            "session_id": self.session_id,
            "entry_count": self.size,
            "entries": [
                {
                    "content": e.content[:100],
                    "agent": e.agent,
                    "timestamp": e.timestamp
                }
                for e in self._memory
            ]
        }


# Session registry - maps session_id to ShortTermMemory instances
_sessions: dict[str, ShortTermMemory] = {}


def get_session_memory(session_id: str, max_entries: int = 50) -> ShortTermMemory:
    """Get or create memory for a session."""
    if session_id not in _sessions:
        _sessions[session_id] = ShortTermMemory(session_id, max_entries)
    return _sessions[session_id]


def clear_session(session_id: str) -> None:
    """Clear memory for a specific session."""
    if session_id in _sessions:
        del _sessions[session_id]
