"""Frozen timer transitions under a valid, writable variable-storage context.

The supplied delta uses the caller's time scale; this module does not assume
seconds or reproduce float32 arithmetic and the game scheduler bit for bit.
"""

from dataclasses import dataclass
from .values import MissingState, enum_number, number


@dataclass(frozen=True)
class TimerState:
    remaining: float
    active: bool

    def __post_init__(self):
        number(self.remaining)
        if type(self.active) is not bool:
            raise ValueError("计时器启用状态必须是布尔值")


def timer_operation(state, default, set_type, *, writable=True):
    """ACTIVATE resets; DEACTIVATE pauses; REACTIVATE keeps the value."""
    if type(writable) is not bool:
        raise MissingState("计时器是否可写未知")
    if not writable:
        return state
    kind = enum_number(set_type)
    if kind == 0:
        return TimerState(number(default), True)
    if kind == 1:
        return TimerState(state.remaining, False)
    if kind == 2:
        return TimerState(state.remaining, True)
    raise MissingState("未知计时器操作")


def advance_timer(state, delta):
    """Mirror the verified update: decrement active timers, clamp, then stop."""
    delta = number(delta)
    if delta < 0:
        raise ValueError("此接口只接受非负时间增量")
    if not state.active:
        return state
    remaining = max(number(state.remaining) - delta, 0)
    return TimerState(remaining, remaining > 0)
