"""Daily summary package (T11): build/aggregate the per-client daily digest."""

from app.summaries.builder import build_daily_summary, day_window, today_in

__all__ = ["build_daily_summary", "day_window", "today_in"]
