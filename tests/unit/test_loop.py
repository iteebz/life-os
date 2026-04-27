from life.loop import LoopState, require_real_world_closure, update_loop_state


def test_gate_triggers_after_two_code_only_sessions():
    state = LoopState()
    update_loop_state(
        state,
        shipped_code=True,
        shipped_life=False,
        flags=[],
        required_task_id=None,
        outcome="code_only",
    )
    update_loop_state(
        state,
        shipped_code=True,
        shipped_life=False,
        flags=[],
        required_task_id=None,
        outcome="code_only",
    )
    assert require_real_world_closure(state) is True


def test_life_closure_resets_streak():
    state = LoopState(consecutive_code_only_sessions=3)
    update_loop_state(
        state,
        shipped_code=True,
        shipped_life=True,
        flags=["stuck_task_protocol"],
        required_task_id="abc",
        outcome="ok",
    )
    assert state.consecutive_code_only_sessions == 0
    assert state.last_required_task_id == "abc"
    assert state.last_flags == ["stuck_task_protocol"]
