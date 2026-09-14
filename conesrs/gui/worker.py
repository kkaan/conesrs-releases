"""Run a callable on a QThreadPool and deliver its result on the UI thread.

Two details matter here and are covered by tests/gui/test_worker.py:

* The runnable (and its signal object) must be kept alive by Python until the
  result has been delivered. QThreadPool only owns the C++ side; if the Python
  wrapper is collected the job silently never runs.
* The result is delivered through a QObject slot that lives in the thread
  that called schedule(), so an emit from the worker thread is queued back
  onto the UI thread and on_done runs there.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _Signals(QObject):
    done = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable, signals: _Signals):
        super().__init__()
        self.setAutoDelete(False)
        self._fn = fn
        self._signals = signals

    def run(self):
        self._signals.done.emit(self._fn())


class _Receiver(QObject):
    """Lives in the scheduling thread; its slot runs there."""

    def __init__(self, on_done: Callable, release: Callable):
        super().__init__()
        self._on_done = on_done
        self._release = release

    @Slot(object)
    def deliver(self, value):
        self._release()
        self._on_done(value)


def make_qt_scheduler(pool: QThreadPool | None = None) -> Callable:
    """Return a schedule(fn, on_done) that runs fn off-thread, on_done on the UI thread."""
    pool = pool or QThreadPool.globalInstance()
    live: set = set()

    def schedule(fn: Callable, on_done: Callable) -> None:
        signals = _Signals()
        task = _Task(fn, signals)
        holder = (task, signals)
        receiver = _Receiver(on_done, lambda: live.discard(holder_ref[0]))
        holder_ref = [(task, signals, receiver)]
        live.add(holder_ref[0])
        signals.done.connect(receiver.deliver)
        pool.start(task)

    return schedule
