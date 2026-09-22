"""每个计算线程独立的进度与合作式取消反馈。"""

from contextlib import contextmanager
from contextvars import ContextVar

_feedback = ContextVar("processing_feedback", default=None)


class ProcessingCancelled(RuntimeError):
    pass


def check():
    feedback = _feedback.get()
    if feedback and feedback[1]():
        raise ProcessingCancelled("任务已取消。")


def report(fraction):
    check()
    feedback = _feedback.get()
    if feedback:
        feedback[0](float(fraction))


def gdal_callback(fraction, message, data):
    try:
        report(fraction)
        return 1
    except ProcessingCancelled:
        return 0


@contextmanager
def feedback_scope(progress, cancelled):
    token = _feedback.set((progress, cancelled))
    try:
        check()
        yield
        check()
    finally:
        _feedback.reset(token)
