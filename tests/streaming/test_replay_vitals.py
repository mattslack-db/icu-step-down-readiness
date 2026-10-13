"""Unit tests for the live-vitals replay planner (src/streaming/replay_vitals.py)."""

import pytest

from src.streaming.replay_vitals import (
    REPLAY_WINDOW_HOURS,
    ReleasePlan,
    build_release_sql,
    plan_release,
)


class TestPlanRelease:
    def test_first_run_releases_the_initial_hours(self) -> None:
        plan = plan_release(hours_released=None, initial_hours=12.0, step_hours=1.0)
        assert plan == ReleasePlan(start_hours=0.0, end_hours=12.0, is_final=False)

    def test_subsequent_run_advances_by_one_step(self) -> None:
        plan = plan_release(hours_released=12.0, initial_hours=12.0, step_hours=1.0)
        assert plan == ReleasePlan(start_hours=12.0, end_hours=13.0, is_final=False)

    def test_last_step_is_clamped_to_the_window_and_marked_final(self) -> None:
        plan = plan_release(hours_released=23.5, initial_hours=12.0, step_hours=1.0)
        assert plan == ReleasePlan(start_hours=23.5, end_hours=REPLAY_WINDOW_HOURS, is_final=True)

    def test_returns_none_when_replay_is_complete(self) -> None:
        assert plan_release(hours_released=REPLAY_WINDOW_HOURS, initial_hours=12.0, step_hours=1.0) is None

    @pytest.mark.parametrize("step", [0.0, -1.0])
    def test_rejects_non_positive_step(self, step: float) -> None:
        with pytest.raises(ValueError, match="step_hours"):
            plan_release(hours_released=None, initial_hours=12.0, step_hours=step)

    @pytest.mark.parametrize("initial", [-1.0, REPLAY_WINDOW_HOURS + 1])
    def test_rejects_initial_hours_outside_window(self, initial: float) -> None:
        with pytest.raises(ValueError, match="initial_hours"):
            plan_release(hours_released=None, initial_hours=initial, step_hours=1.0)


class TestBuildReleaseSql:
    def test_selects_only_cohort_events_inside_the_release_slice(self) -> None:
        sql = build_release_sql(ReleasePlan(start_hours=12.0, end_hours=13.0, is_final=False))
        assert "INSERT INTO icu_step_down.landing.chart_events_feed" in sql
        assert "JOIN icu_step_down.landing.live_cohort" in sql
        assert "c.window_start + make_interval(0, 0, 0, 0, 0, 0, 43200.0)" in sql
        assert "c.window_start + make_interval(0, 0, 0, 0, 0, 0, 46800.0)" in sql

    def test_scopes_to_the_bronze_chart_itemids(self) -> None:
        sql = build_release_sql(ReleasePlan(start_hours=0.0, end_hours=12.0, is_final=False))
        # heart rate (CareVue + MetaVision) and the MetaVision ventilator mode
        for itemid in ("211", "220045", "223849"):
            assert itemid in sql

    def test_slice_is_half_open_so_events_are_never_released_twice(self) -> None:
        sql = build_release_sql(ReleasePlan(start_hours=12.0, end_hours=13.0, is_final=False))
        assert ">= c.window_start" in sql
        assert "< c.window_start" in sql
