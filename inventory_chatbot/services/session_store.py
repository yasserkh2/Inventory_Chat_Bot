from __future__ import annotations

from inventory_chatbot.models.domain import SessionState, SessionTurn


class SessionStore:
    def __init__(self, max_turns_per_session: int = 10) -> None:
        self._max_turns_per_session = max_turns_per_session
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        session = self._sessions.get(session_id)
        if session is None:
            session = SessionState(session_id=session_id)
            self._sessions[session_id] = session
        return session

    def append_turn(self, session_id: str, turn: SessionTurn) -> SessionState:
        session = self.get(session_id)
        session.turns.append(turn)
        if len(session.turns) > self._max_turns_per_session:
            session.turns = session.turns[-self._max_turns_per_session :]
        return session

