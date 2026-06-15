"""Long-Term Memory for AgentFlow

Persists agent learnings across sessions.
This is a stub implementation - production version would use a vector database.

See docs/limitations.md for full discussion of memory limitations.
"""

import json
import time
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class LongTermEntry:
    """A persisted memory entry."""
    id: str
    content: str
    embedding: list[float] = field(default_factory=list)  # stub: empty
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)


class LongTermMemory:
    """File-based long-term memory (stub implementation).

    Production version would use:
    - ChromaDB or Pinecone for vector storage
    - Semantic search via embeddings
    - Automatic summarization of old entries
    - Importance-based retention policies

    This stub uses JSON files for simplicity.
    """

    def __init__(self, storage_path: str = "memory/store"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self.storage_path / "index.json"
        self._entries: dict[str, LongTermEntry] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load existing entries from disk."""
        if self._index_path.exists():
            try:
                with open(self._index_path) as f:
                    data = json.load(f)
                for entry_data in data.get("entries", []):
                    entry = LongTermEntry(**entry_data)
                    self._entries[entry.id] = entry
            except Exception:
                pass  # Start fresh if index is corrupted

    def _save_index(self) -> None:
        """Persist entries to disk."""
        try:
            data = {
                "version": "1.0",
                "entry_count": len(self._entries),
                "entries": [asdict(e) for e in self._entries.values()]
            }
            with open(self._index_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # Graceful failure if we can't save

    def store(
        self,
        content: str,
        entry_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> str:
        """Store a new long-term memory entry.

        Note: In production, this would generate embeddings for
        semantic search. Here we just store the text.
        """
        if entry_id is None:
            entry_id = f"mem_{int(time.time() * 1000)}"

        entry = LongTermEntry(
            id=entry_id,
            content=content,
            metadata=metadata or {}
        )
        self._entries[entry_id] = entry
        self._save_index()
        return entry_id

    def retrieve(
        self,
        query: str,
        limit: int = 5
    ) -> list[LongTermEntry]:
        """Retrieve relevant memories.

        Stub: Returns most recent entries (not semantically relevant).
        Production: Would use cosine similarity on embeddings.
        """
        # Update access counts
        entries = sorted(
            self._entries.values(),
            key=lambda e: e.created_at,
            reverse=True
        )[:limit]

        for entry in entries:
            entry.access_count += 1
            entry.last_accessed = time.time()

        self._save_index()
        return entries

    def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._save_index()
            return True
        return False

    def clear_all(self) -> None:
        """Clear all long-term memory."""
        self._entries.clear()
        if self._index_path.exists():
            self._index_path.unlink()

    @property
    def size(self) -> int:
        """Total number of stored entries."""
        return len(self._entries)

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        return {
            "total_entries": self.size,
            "storage_path": str(self.storage_path),
            "implementation": "stub_file_based",
            "note": "Production version would use vector database for semantic search"
        }
