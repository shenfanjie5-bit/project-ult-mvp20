"""Shared test fakes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Condition

from graph_engine.models import Neo4jGraphStatus


class InMemoryStatusState:
    """Shared in-memory status row used by distinct StatusStore fakes."""

    def __init__(self, status: Neo4jGraphStatus | None = None) -> None:
        self.status = status
        self.condition = Condition()
        self.ready_readers = 0
        self.writer_active = False


class InMemoryStatusStore:
    """In-memory StatusStore fake with write and CAS observability."""

    def __init__(
        self,
        status: Neo4jGraphStatus | None = None,
        *,
        state: InMemoryStatusState | None = None,
    ) -> None:
        self._state = state or InMemoryStatusState(status)
        self.writes: list[Neo4jGraphStatus] = []
        self.compare_calls: list[tuple[Neo4jGraphStatus | None, Neo4jGraphStatus]] = []

    @property
    def graph_status(self) -> Neo4jGraphStatus | None:
        return self.status

    @graph_status.setter
    def graph_status(self, status: Neo4jGraphStatus | None) -> None:
        self.status = status

    @property
    def status(self) -> Neo4jGraphStatus | None:
        return self._state.status

    @status.setter
    def status(self, status: Neo4jGraphStatus | None) -> None:
        self._state.status = status

    @contextmanager
    def ready_read_lock(self) -> Iterator[None]:
        with self._state.condition:
            while self._state.writer_active:
                self._state.condition.wait()
            self._state.ready_readers += 1
        try:
            yield
        finally:
            with self._state.condition:
                self._state.ready_readers -= 1
                if self._state.ready_readers == 0:
                    self._state.condition.notify_all()

    def read_current_status(self) -> Neo4jGraphStatus | None:
        return self.status

    def write_current_status(self, status: Neo4jGraphStatus) -> None:
        with self._write_lock():
            self.status = status
            self.writes.append(status)

    def compare_and_write_current_status(
        self,
        *,
        expected_status: Neo4jGraphStatus | None,
        next_status: Neo4jGraphStatus,
    ) -> bool:
        if isinstance(self.compare_calls, list):
            self.compare_calls.append((expected_status, next_status))
        with self._write_lock():
            if self.status != expected_status:
                return False
            self.status = next_status
            self.writes.append(next_status)
            return True

    @contextmanager
    def _write_lock(self) -> Iterator[None]:
        with self._state.condition:
            while self._state.writer_active or self._state.ready_readers > 0:
                self._state.condition.wait()
            self._state.writer_active = True
        try:
            yield
        finally:
            with self._state.condition:
                self._state.writer_active = False
                self._state.condition.notify_all()
