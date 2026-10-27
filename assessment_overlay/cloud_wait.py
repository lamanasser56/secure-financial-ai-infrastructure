"""Bounded waits for cloud long-running operations and eventual consistency.

A cloud call can return before its effect is visible: the operation is still
running, or a new API, identity or IAM binding is still propagating. The
operator then polls the observable end state, or repeats an idempotent call,
until a deadline that never extends past the assessment deadline. Cleanup uses
a waiter without the assessment deadline, because it must run after it too.
"""
from datetime import datetime, timedelta, timezone
import time


def utcnow():
    return datetime.now(timezone.utc)


class Waiter:
    def __init__(self, deadline_at=None, *, clock=utcnow, sleep=time.sleep, interval=10):
        self.deadline = datetime.fromisoformat(deadline_at) if deadline_at else None
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError('assessment deadline must be timezone-aware')
        self.clock, self.sleep, self.interval = clock, sleep, interval

    def until(self, seconds):
        limit = self.clock() + timedelta(seconds=seconds)
        return limit if self.deadline is None else min(limit, self.deadline)

    def timeout(self, seconds):
        """Subprocess timeout for one blocking call, bounded by the deadline."""
        remaining = (self.until(seconds) - self.clock()).total_seconds()
        if remaining <= 0:
            raise RuntimeError('assessment:deadline_passed')
        return remaining

    def _pause(self, until):
        remaining = (until - self.clock()).total_seconds()
        self.sleep(max(1, min(self.interval, remaining)))

    def poll(self, check, *, seconds, what):
        """Return check()'s first truthy value; a RuntimeError counts as not yet visible."""
        until = self.until(seconds)
        while True:
            try:
                value = check()
            except RuntimeError:
                value = None
            if value:
                return value
            if self.clock() >= until:
                raise RuntimeError('assessment:wait_timeout:' + what)
            self._pause(until)

    def retry(self, action, *, seconds, what):
        """Repeat an idempotent action while its RuntimeError may be propagation delay."""
        until = self.until(seconds)
        while True:
            try:
                return action()
            except RuntimeError as error:
                if self.clock() >= until:
                    raise RuntimeError('assessment:retry_exhausted:' + what) from error
            self._pause(until)
