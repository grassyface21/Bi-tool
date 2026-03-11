import uuid
import time
import sqlite3
import threading
import logging
from typing import Optional
import pandas as pd

from config import SESSION_TIMEOUT

logger = logging.getLogger(__name__)


class SessionData:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at: float = time.time()
        self.last_accessed: float = time.time()
        self.dataframes: dict[str, pd.DataFrame] = {}
        self.schema: dict = {}
        # SQL schema string (CREATE TABLE + stats + sample rows) for LLM prompt
        self.sql_schema: str = ""
        # In-memory SQLite database — single connection shared across queries
        self.sqlite_conn: Optional[sqlite3.Connection] = None
        self.sqlite_lock: threading.Lock = threading.Lock()
        self.conversation_history: list[dict] = []

    def is_expired(self) -> bool:
        return (time.time() - self.last_accessed) > SESSION_TIMEOUT

    def touch(self):
        self.last_accessed = time.time()


class SessionStore:
    _instance: Optional["SessionStore"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "SessionStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._sessions: dict[str, SessionData] = {}
                    cls._instance._sessions_lock = threading.Lock()
        return cls._instance

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        with self._sessions_lock:
            self._sessions[session_id] = SessionData(session_id)
        logger.info(f"Created session: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionData]:
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired():
                del self._sessions[session_id]
                logger.info(f"Session expired on access: {session_id}")
                return None
            session.touch()
            return session

    def add_dataframes(self, session_id: str, dataframes: dict[str, pd.DataFrame]) -> bool:
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.dataframes.update(dataframes)
            session.touch()
            return True

    def set_schema(self, session_id: str, schema: dict) -> bool:
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.schema = schema
            session.touch()
            return True

    def set_sqlite(
        self,
        session_id: str,
        conn: sqlite3.Connection,
        sql_schema: str,
    ) -> bool:
        """Store the SQLite connection and pre-built schema prompt string."""
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.sqlite_conn = conn
            session.sql_schema = sql_schema
            session.touch()
            return True

    def add_message(self, session_id: str, role: str, content: dict) -> bool:
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.conversation_history.append({"role": role, "content": content})
            session.touch()
            return True

    def cleanup_expired_sessions(self) -> int:
        """Remove all expired sessions. Returns count of removed sessions."""
        expired_ids = []
        with self._sessions_lock:
            for session_id, session in list(self._sessions.items()):
                if session.is_expired():
                    expired_ids.append(session_id)
            for session_id in expired_ids:
                del self._sessions[session_id]
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired sessions")
        return len(expired_ids)

    def session_count(self) -> int:
        with self._sessions_lock:
            return len(self._sessions)


# Singleton instance
session_store = SessionStore()
