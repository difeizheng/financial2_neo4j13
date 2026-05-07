"""Chat history persistence using SQLite."""
from __future__ import annotations
import sqlite3
import os
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tasks.db")


@dataclass
class ChatMessage:
    id: int
    task_id: str
    role: str  # "user" or "assistant"
    content: str
    created_at: str
    metadata: dict = None  # Additional info (retrieval contexts, etc)


class ChatHistoryDB:
    """Persistent storage for chat conversations."""
    
    def __init__(self, db_path: str = _DEFAULT_DB):
        self.db_path = os.path.abspath(db_path)
        self._init_table()
    
    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def _init_table(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    session_id TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_task 
                ON chat_history(task_id, created_at)
            """)
    
    def save_message(
        self,
        task_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> int:
        """Save a chat message to database.
        
        Returns:
            Message ID
        """
        with self._conn() as conn:
            created_at = datetime.now().isoformat()
            metadata_json = json.dumps(metadata) if metadata else None
            
            cursor = conn.execute("""
                INSERT INTO chat_history 
                (task_id, role, content, created_at, metadata, session_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, role, content, created_at, metadata_json, session_id))
            
            return cursor.lastrowid
    
    def load_history(
        self,
        task_id: str,
        limit: int = 100,
        session_id: Optional[str] = None,
    ) -> list[ChatMessage]:
        """Load chat history for a task.
        
        Args:
            task_id: Task ID
            limit: Maximum messages to load
            session_id: Optional session filter
            
        Returns:
            List of ChatMessage objects
        """
        with self._conn() as conn:
            if session_id:
                cursor = conn.execute("""
                    SELECT * FROM chat_history
                    WHERE task_id = ? AND session_id = ?
                    ORDER BY created_at ASC
                    LIMIT ?
                """, (task_id, session_id, limit))
            else:
                cursor = conn.execute("""
                    SELECT * FROM chat_history
                    WHERE task_id = ?
                    ORDER BY created_at ASC
                    LIMIT ?
                """, (task_id, limit))
            
            messages = []
            for row in cursor.fetchall():
                metadata = json.loads(row["metadata"]) if row["metadata"] else None
                messages.append(ChatMessage(
                    id=row["id"],
                    task_id=row["task_id"],
                    role=row["role"],
                    content=row["content"],
                    created_at=row["created_at"],
                    metadata=metadata,
                ))
            
            return messages
    
    def clear_history(self, task_id: str, session_id: Optional[str] = None):
        """Clear chat history for a task/session."""
        with self._conn() as conn:
            if session_id:
                conn.execute("""
                    DELETE FROM chat_history
                    WHERE task_id = ? AND session_id = ?
                """, (task_id, session_id))
            else:
                conn.execute("""
                    DELETE FROM chat_history WHERE task_id = ?
                """, (task_id,))
    
    def format_for_llm(self, messages: list[ChatMessage]) -> list[dict]:
        """Format chat history for LLM API.
        
        Returns:
            List of {"role": ..., "content": ...} dicts
        """
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]