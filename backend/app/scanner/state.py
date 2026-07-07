"""Re-arm state machine per (scan, symbol, side) — ARCHITECTURE §3.2.

    armed + all true  → FIRE, state=fired
    fired + any false → state=armed   (re-armed, no signal)
    fired + all true  → no-op         (prevents duplicate alerts)
    armed + any false → no-op
"""

ARMED = "armed"
FIRED = "fired"


def transition(state: str, conditions_true: bool) -> tuple[str, bool]:
    """Returns (new_state, should_fire)."""
    if state == ARMED and conditions_true:
        return FIRED, True
    if state == FIRED and not conditions_true:
        return ARMED, False
    return state, False
