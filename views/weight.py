# Weight page: log weigh-ins, see them on a chart against the expected curve.
from datetime import date, timedelta
from html import escape
from time import time

import altair as alt
import pandas as pd
import streamlit as st

from services import db, targets as targets_service
from services.tdee_engine import calculate_tdee
from views.dashboard import _projected_weight

LB_PER_KG = 2.2046226218
# Within this many kcal of maintenance the expected weight is flat.
MAINTENANCE_BAND_KCAL = 25
GREEN, RED, BLUE = "#34d399", "#dc2a46", "#5aa9d6"
# Red trend line: needs this many logs to smooth, fits this share of them at a time.
TREND_MIN_LOGS = 6
TREND_MIN_NEIGHBOURS = 5
TREND_SHARE = 0.05
DOT_HIT_TARGET_SIZE = 300
# The chart can never be zoomed in past this many days (or out past the logged dates).
MIN_WINDOW_DAYS = 7
CHART_EDGE_PADDING = timedelta(days=1)
LINE_EDGE_GAP_FRACTION = 0.01
RANGES ={"7D": 7, "1M": 31, "6M": 183, "1Y": 365, "All": None}

WEIGHT_CSS = """
<style>
    .block-container { padding-top: 1.5rem !important; }
    .st-key-weight_form, .st-key-weight_history {
        padding: 20px 24px;
        border: 1px solid var(--sustain-border);
        border-radius: 16px;
        background: var(--sustain-surface);
    }
    .st-key-weight_form [data-testid="stForm"] {
        padding: 0;
        border: 0;
    }
    .st-key-weight_history button {
        min-height: 1.9rem;
        border: 0;
        background: transparent;
        color: var(--sustain-muted);
    }
    .st-key-weight_history button:hover {
        background: var(--sustain-negative-soft);
        color: var(--sustain-negative);
    }
    .st-key-weight_history [class*="st-key-weight_edit_"] button:hover {
        background: var(--sustain-hover);
        color: var(--sustain-text);
    }
    .st-key-weight_form { margin-bottom: 1.1rem; }
    .st-key-weight_history { width: 100%; }
    .wt-history-heading {
        display:flex;
        align-items:baseline;
        gap:.65rem;
        padding-bottom:.65rem;
        margin-bottom:.85rem;
        border-bottom:1px solid var(--sustain-border);
    }
    .wt-history-count { color:var(--sustain-secondary); font-size:.82rem; }
    @keyframes wt-popup-expire {
        0%, 94% { opacity:1; transform:translateY(0); }
        100% { opacity:0; transform:translateY(-4px); visibility:hidden; }
    }
    .wt-success-popup {
        width:max-content;
        max-width:80vw;
        margin:0 auto .45rem;
        padding:.55rem .7rem;
        border:1px solid var(--sustain-border);
        border-radius:.5rem;
        background:var(--sustain-surface);
        color:var(--sustain-positive);
        font-size:.78rem;
        line-height:1.35;
        text-align:center;
        white-space:nowrap;
        animation:wt-popup-expire 5s linear forwards;
    }
    .wt-head { display:flex; align-items:center; gap:.7rem; flex-wrap:wrap; }
    .wt-title { margin:0; font-size:2rem; font-weight:500; color:var(--sustain-text); }
    .wt-sub { margin:.2rem 0 1rem; color:var(--sustain-secondary); font-size:.9rem; }
    .wt-kpis { display:grid; grid-template-columns:repeat(4, 1fr); gap:16px; margin-bottom:16px; }
    @media (max-width: 1100px) { .wt-kpis { grid-template-columns:repeat(2, 1fr); } }
    .wt-kpi { display:flex; flex-direction:column; gap:.45rem; padding:20px;
        border:1px solid var(--sustain-border); border-radius:12px; background:var(--sustain-surface); }
    .wt-kpi-top { display:flex; justify-content:space-between; align-items:center; gap:.5rem; }
    .wt-kpi-label { color:var(--sustain-secondary); font-size:.8rem; font-weight:500; }
    .wt-badge { padding:.1rem .55rem; border:1px solid var(--sustain-border); border-radius:4px;
        background:transparent; color:var(--sustain-muted); font:.75rem var(--sustain-mono); }
    .wt-badge.green { color:var(--sustain-positive); }
    .wt-badge.blue { color:var(--sustain-info); }
    .wt-badge.red { color:var(--sustain-negative); }
    .wt-kpi-value { color:var(--sustain-text); font-size:1.75rem; line-height:1.15; font-weight:500; font-variant-numeric:tabular-nums; }
    .wt-kpi-foot { display:flex; justify-content:space-between; gap:.5rem; color:var(--sustain-muted);
        font-size:.76rem; font-variant-numeric:tabular-nums; }
    .wt-h { margin:0 0 .15rem; color:var(--sustain-text); font-size:1.0625rem; font-weight:500; }
    .wt-muted { color:var(--sustain-secondary); font-size:.82rem; }
    .st-key-weight_chart {
        margin-bottom: 1.1rem;
        padding: 20px 24px;
        border: 1px solid var(--sustain-border);
        border-radius: 16px;
        background: var(--sustain-surface);
    }
    .wt-legend { display:flex; flex-wrap:wrap; gap:.6rem; margin:.2rem 0 .8rem; }
    .wt-legend span { display:inline-flex; align-items:center; gap:.5rem; padding:.28rem .7rem;
        border:1px solid var(--sustain-border); border-radius:8px; background:transparent;
        color:var(--sustain-secondary); font-size:.8125rem; font-weight:400; }
    .wt-dot { width:.65rem; height:.65rem; border-radius:50%; display:inline-block; }
    .wt-bar { width:1rem; height:3px; border-radius:2px; display:inline-block; }
    .wt-dots { width:1.1rem; border-top:3px dotted; display:inline-block; }
    .wt-empty { padding:2.2rem 1rem; text-align:center; color:var(--sustain-secondary);
        border:1px solid var(--sustain-border); border-radius:14px; background:var(--sustain-surface); }
    .wt-estimates { display:grid; grid-template-columns:repeat(3,1fr); margin:1rem 0;
        border-top:1px solid var(--sustain-border); border-bottom:1px solid var(--sustain-border); }
    .wt-estimate { padding:.65rem .5rem; }
    .wt-estimate + .wt-estimate { border-left:1px solid var(--sustain-border); }
    .wt-estimate-label { display:block; color:var(--sustain-secondary); font-size:.8rem; }
    .wt-estimate-value { display:block; margin-top:.25rem; color:var(--sustain-text);
        font-size:1.25rem; font-weight:500; font-variant-numeric:tabular-nums; }
</style>
"""


def expected_weights(start_date, start_kg, end_date, daily_delta_kcal):
    """Expected weight (kg) for every day from start_date to end_date.

    Uses the same loss curve as the dashboard projection, starting from the
    first logged weight. A calorie surplus gives the mirror-image gain curve.
    """
    deficit = abs(daily_delta_kcal) if abs(daily_delta_kcal) > MAINTENANCE_BAND_KCAL else 0
    direction = -1 if daily_delta_kcal < 0 else 1
    days = (end_date - start_date).days
    series = []
    for offset in range(days + 1):
        change = start_kg - _projected_weight(start_kg, deficit, offset / 7)
        series.append(
            {
                "d": (start_date + timedelta(days=offset)).isoformat(),
                "kg": round(start_kg + direction * change, 3),
            }
        )
    return series


def trend_line(entries):
    """A smoothed weight (kg) for every log: a local straight-line fit over the
    nearest logs, so the red line follows the dots and passes through them
    when there are too few logs to smooth."""
    weights = [e["weight_kg"] for e in entries]
    if len(entries) < TREND_MIN_LOGS:
        return weights
    days = [date.fromisoformat(e["log_date"]).toordinal() for e in entries]
    neighbours = max(TREND_MIN_NEIGHBOURS, round(len(entries) * TREND_SHARE))
    fitted = []
    for day in days:
        nearest = sorted(range(len(days)), key=lambda i: abs(days[i] - day))[:neighbours]
        reach = max(abs(days[nearest[-1]] - day), 1) * 1.0001
        w = [(1 - (abs(days[i] - day) / reach) ** 3) ** 3 for i in nearest]
        total = sum(w)
        mean_x = sum(wi * days[i] for wi, i in zip(w, nearest)) / total
        mean_y = sum(wi * weights[i] for wi, i in zip(w, nearest)) / total
        spread = sum(wi * (days[i] - mean_x) ** 2 for wi, i in zip(w, nearest))
        slope = (
            sum(wi * (days[i] - mean_x) * (weights[i] - mean_y) for wi, i in zip(w, nearest))
            / spread
            if spread > 1e-9
            else 0.0
        )
        fitted.append(mean_y + slope * (day - mean_x))
    return fitted


def clamp_window(start, end, first, last):
    """Keep a chart window inside the logged dates and at least MIN_WINDOW_DAYS wide."""
    if (last - first).days < MIN_WINDOW_DAYS - 1:
        return first, last
    start, end = max(start, first), min(end, last)
    if (end - start).days < MIN_WINDOW_DAYS - 1:
        end = min(last, start + timedelta(days=MIN_WINDOW_DAYS - 1))
        start = end - timedelta(days=MIN_WINDOW_DAYS - 1)
    return start, end


def _available_ranges(logged_days):
    thresholds = {"1M": 7, "6M": 30, "1Y": 183}
    return [
        label
        for label in RANGES
        if label == "All"
        or (label == "7D" and logged_days >= MIN_WINDOW_DAYS - 1)
        or (label in thresholds and logged_days > thresholds[label])
    ]


def _line_window(data, value_column, line_start, line_end, stop_at_last_value=False):
    """Extend a line close to the window edges, optionally stopping at its last value."""
    if data.empty:
        return data

    values = data.set_index("date")[value_column].sort_index()
    if stop_at_last_value:
        line_end = min(line_end, values.index[-1])
    if line_end < line_start:
        return data.iloc[0:0]
    dates = values.index.union(pd.DatetimeIndex([line_start, line_end]))
    window = values.reindex(dates).interpolate(method="time")

    if line_start < values.index[0]:
        if len(values) > 1:
            slope = (values.iloc[1] - values.iloc[0]) / (
                values.index[1] - values.index[0]
            ).total_seconds()
            window.loc[line_start] = values.iloc[0] + slope * (
                line_start - values.index[0]
            ).total_seconds()
        else:
            window.loc[line_start] = values.iloc[0]
    if line_end > values.index[-1]:
        if len(values) > 1:
            slope = (values.iloc[-1] - values.iloc[-2]) / (
                values.index[-1] - values.index[-2]
            ).total_seconds()
            window.loc[line_end] = values.iloc[-1] + slope * (
                line_end - values.index[-1]
            ).total_seconds()
        else:
            window.loc[line_end] = values.iloc[-1]

    return (
        window.loc[line_start:line_end]
        .dropna()
        .rename(value_column)
        .rename_axis("date")
        .reset_index()
    )


def _weight_chart(entries, expected, unit, factor, start, end):
    """Altair chart of [start, end]: green log dots, red trend, blue dotted expected."""
    logs = pd.DataFrame(
        {
            "date": pd.to_datetime([e["log_date"] for e in entries]),
            "weight": [e["weight_kg"] * factor for e in entries],
            "average": [a * factor for a in trend_line(entries)],
            "note": [e["note"] for e in entries],
        }
    )
    plan = pd.DataFrame(
        {
            "date": pd.to_datetime([p["d"] for p in expected]),
            "weight": [p["kg"] * factor for p in expected],
        }
    )
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    domain_start = start_ts - pd.Timedelta(CHART_EDGE_PADDING)
    domain_end = end_ts + pd.Timedelta(CHART_EDGE_PADDING)
    edge_gap = (domain_end - domain_start) * LINE_EDGE_GAP_FRACTION
    line_start = domain_start + edge_gap
    line_end = domain_end - edge_gap
    trend = logs.set_index("date")["average"].sort_index()
    average_logs = _line_window(
        trend.rename_axis("date").reset_index(),
        "average",
        line_start,
        line_end,
        stop_at_last_value=True,
    )
    plan = _line_window(plan, "weight", line_start, line_end)
    logs = logs[logs["date"].between(start_ts, end_ts)]

    x = alt.X(
        "date:T",
        title=None,
        scale=alt.Scale(
            domain=[domain_start.isoformat(), domain_end.isoformat()]
        ),
        axis=alt.Axis(
            format="%b %d",
            tickCount={"interval": "day", "step": 1},
            labelColor="#8a8a90",
            grid=False,
            domainColor="rgba(138, 138, 144, .3)",
        ),
    )
    y = alt.Y(
        "weight:Q",
        title=f"Weight ({unit})",
        scale=alt.Scale(zero=False, nice=True, padding=12),
        axis=alt.Axis(labelColor="#8a8a90", titleColor="#8a8a90", gridColor="rgba(138, 138, 144, .15)", domain=False),
    )
    hover = alt.selection_point(on="pointerover", fields=["date"], empty=False)

    expected_line = (
        alt.Chart(plan)
        .mark_line(color=BLUE, strokeWidth=2.6, strokeDash=[1, 7], strokeCap="round", clip=True)
        .encode(x=x, y=y)
    )
    average_line = (
        alt.Chart(average_logs)
        .mark_line(color=RED, strokeWidth=2.4, clip=True)
        .encode(x=x, y=alt.Y("average:Q", scale=alt.Scale(zero=False, nice=True, padding=12)))
    )
    dots = (
        alt.Chart(logs)
        .mark_circle(color=GREEN, strokeWidth=0, opacity=1)
        .encode(
            x=x,
            y=y,
            size=alt.condition(hover, alt.value(190), alt.value(70)),
        )
    )
    hover_targets = (
        alt.Chart(logs)
        .mark_circle(size=DOT_HIT_TARGET_SIZE, opacity=0.001)
        .encode(
            x=x,
            y=y,
            tooltip=[
                alt.Tooltip("date:T", title="Date", format="%a, %b %d, %Y"),
                alt.Tooltip("weight:Q", title=f"Weight ({unit})", format=".1f"),
                alt.Tooltip("note:N", title="Note"),
            ],
        )
        .add_params(hover)
    )
    return (
        alt.layer(expected_line, average_line, dots, hover_targets)
        .properties(height=340, background="transparent")
        .configure_view(stroke=None)
    )


def _kpi(label, badge, badge_class, value, left, right, value_color="var(--sustain-text)"):
    return (
        '<div class="wt-kpi"><div class="wt-kpi-top">'
        f'<span class="wt-kpi-label">{label}</span>'
        f'<span class="wt-badge {badge_class}">{badge}</span></div>'
        f'<div class="wt-kpi-value" style="color:{value_color}">{value}</div>'
        f'<div class="wt-kpi-foot"><span>{left}</span><span>{right}</span></div></div>'
    )


def _long_date(iso):
    return date.fromisoformat(iso).strftime("%a, %b %d, %Y").replace(" 0", " ")


def render_weight_page():
    user = st.session_state.user
    profile = db.get_profile(user["id"])
    if profile is None:
        st.info("Complete onboarding to start logging your weight.")
        return
    targets = targets_service.recalibrate(user["id"])
    if targets is None:
        st.info("Your nutrition targets are not available yet. Please check your profile.")
        return

    imperial = profile.get("measurement_units") == "Imperial"
    unit, factor = ("lb", LB_PER_KG) if imperial else ("kg", 1.0)

    def show(kg, signed=False):
        value = kg * factor
        return f"{value:+.1f} {unit}" if signed else f"{value:.1f} {unit}"

    st.markdown(WEIGHT_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="wt-head"><h1 class="wt-title">Weight Logging</h1></div>',
        unsafe_allow_html=True,
    )
    entries = db.get_weight_entries(user["id"])
    tdee = calculate_tdee(profile, macros=targets)
    goal_delta = targets["calories"] - tdee["tdee_kcal"]

    with st.container(key="weight_form"):

        default_kg = entries[-1]["weight_kg"] if entries else profile.get("weight_kg", 70.0)
        with st.form("weight_log_form", border=False):
            weight_col, date_col, note_col, submit_col = st.columns(
                [1.1, 1.15, 3.2, 1], vertical_alignment="bottom"
            )
            weight = weight_col.number_input(
                f"Body weight ({unit})",
                min_value=20.0 * factor,
                max_value=500.0 * factor,
                value=round(default_kg * factor, 1),
                step=0.1,
                format="%.1f",
            )
            log_date = date_col.date_input("Date", value=date.today(), max_value=date.today())
            note = note_col.text_input("Note (optional)", max_chars=60)
            popup = st.session_state.get("weight_message")
            if popup:
                elapsed = time() - popup["created_at"]
                if elapsed >= 5:
                    st.session_state.pop("weight_message", None)
                else:
                    submit_col.markdown(
                        f'<div class="wt-success-popup" role="status" '
                        f'style="animation-delay:-{elapsed:.3f}s">'
                        f'{escape(popup["text"])}</div>',
                        unsafe_allow_html=True,
                    )
            if submit_col.form_submit_button(
                "Log weight", type="primary", use_container_width=True
            ):
                db.save_weight_entry(
                    user["id"], log_date.isoformat(), round(weight / factor, 2), note.strip()
                )
                st.session_state.weight_message = {
                    "text": (
                        f"Logged {weight:.1f} {unit} for "
                        f"{log_date.strftime('%b %d, %Y')}."
                    ),
                    "created_at": time(),
                }
                st.rerun()

    if entries:
        first, latest = entries[0], entries[-1]
        logged_days = (
            date.fromisoformat(latest["log_date"])
            - date.fromisoformat(first["log_date"])
        ).days
        end_date = max(date.fromisoformat(latest["log_date"]), date.today())
        expected = expected_weights(
            date.fromisoformat(first["log_date"]), first["weight_kg"], end_date, goal_delta
        )
    else:
        first = latest = None
        logged_days = 0
        end_date = date.today() + timedelta(weeks=24)
        expected = expected_weights(
            date.today(), profile["weight_kg"], end_date, goal_delta
        )

    with st.container(key="weight_chart"):
        heading, ranges = st.columns([2, 3], vertical_alignment="center")
        heading.markdown(
            '<p class="wt-h">Weight Trajectory</p>'
            "<br>Use the range buttons or slider to zoom.</p>",
            unsafe_allow_html=True,
        )
        first_day = date.fromisoformat(expected[0]["d"])
        last_day = date.fromisoformat(expected[-1]["d"])

        available_ranges = _available_ranges(logged_days)
        selected_range = st.session_state.get("weight_range", "All")
        if selected_range not in available_ranges:
            selected_range = "All"
            st.session_state.pop("weight_window", None)
        st.session_state.weight_range = selected_range
        st.session_state.weight_range_allowed = selected_range

        def pick_range():
            range_label = st.session_state.weight_range or "All"
            if range_label not in available_ranges:
                st.session_state.weight_range = st.session_state.weight_range_allowed
                return
            st.session_state.weight_range_allowed = range_label
            days = RANGES[range_label]
            st.session_state.weight_window = (
                (first_day if days is None else max(first_day, last_day - timedelta(days=days - 1))),
                last_day,
            )

        disabled_range_positions = [
            index + 1
            for index, label in enumerate(RANGES)
            if label not in available_ranges
        ]
        if disabled_range_positions:
            selectors = ", ".join(
                f'.st-key-weight_ranges [data-testid="stSegmentedControl"] '
                f'button:nth-of-type({position})'
                for position in disabled_range_positions
            )
            st.markdown(
                f"<style>{selectors} {{ opacity:.38; cursor:not-allowed; "
                "pointer-events:none; }</style>",
                unsafe_allow_html=True,
            )
        with ranges:
            st.container(key="weight_ranges").segmented_control(
                "Range",
                list(RANGES),
                default="All",
                key="weight_range",
                on_change=pick_range,
                label_visibility="collapsed",
            )
        if "weight_window" not in st.session_state:
            pick_range()
        st.session_state.weight_window = clamp_window(
            *st.session_state.weight_window, first_day, last_day
        )
        if (last_day - first_day).days >= MIN_WINDOW_DAYS:
            st.slider(
                "Visible dates",
                min_value=first_day,
                max_value=last_day,
                key="weight_window",
                format="MMM D, YYYY",
                label_visibility="collapsed",
            )
            window_start, window_end = clamp_window(
                *st.session_state.weight_window, first_day, last_day
            )
        else:
            window_start, window_end = first_day, last_day
        st.markdown(
            '<div class="wt-legend">'
            f'<span><i class="wt-dot" style="background:{GREEN}"></i>Individual weight log</span>'
            f'<span><i class="wt-bar" style="background:{RED}"></i>Average weight trend</span>'
            f'<span><i class="wt-dots" style="border-color:{BLUE}"></i>Expected weight</span>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.altair_chart(
            _weight_chart(entries, expected, unit, factor, window_start, window_end),
            use_container_width=True,
            theme=None,
        )
        daily_deficit = max(-goal_delta, 0)
        estimates = "".join(
            '<div class="wt-estimate">'
            f'<span class="wt-estimate-label">{week}-week estimate</span>'
            f'<span class="wt-estimate-value">'
            f'{_projected_weight(profile["weight_kg"], daily_deficit, week) * factor:.1f} '
            f'{unit}</span></div>'
            for week in (4, 12, 24)
        )
        st.markdown(
            f'<div class="wt-estimates">{estimates}</div>',
            unsafe_allow_html=True,
        )

    if entries:
        expected_by_date = {point["d"]: point["kg"] for point in expected}
        expected_latest = expected_by_date[latest["log_date"]]

        overall = latest["weight_kg"] - first["weight_kg"]
        cutoff = (date.fromisoformat(latest["log_date"]) - timedelta(days=30)).isoformat()
        recent = [e for e in entries if e["log_date"] >= cutoff]
        period = latest["weight_kg"] - recent[0]["weight_kg"]
        last7 = entries[-7:]
        avg7 = sum(e["weight_kg"] for e in last7) / len(last7)
        off_plan = latest["weight_kg"] - expected_latest

        cards = "".join(
            (
                _kpi(
                    "Current Weight", "Latest Log", "green", show(latest["weight_kg"]),
                    _long_date(latest["log_date"]),
                    f"{'↓' if overall <= 0 else '↑'} {show(abs(overall))} overall",
                ),
                _kpi(
                    "Period Change", "Last 30 days", "", show(period, signed=True),
                    f"{show(recent[0]['weight_kg'])} → {show(latest['weight_kg'])}",
                    f"{len(recent)} logs",
                    value_color="var(--sustain-positive)" if period <= 0 else "var(--sustain-caution)",
                ),
                _kpi(
                    "Rolling Average", "Last 7 logs", "red", show(avg7),
                    "Smoothed baseline",
                    f"{show(latest['weight_kg'] - avg7, signed=True)} vs latest",
                ),
                _kpi(
                    "Expected Weight", "Projection", "blue", show(expected_latest),
                    "On your calorie target",
                    f"{show(off_plan, signed=True)} vs expected",
                ),
            )
        )
        st.markdown(f'<div class="wt-kpis">{cards}</div>', unsafe_allow_html=True)

    with st.container(key="weight_history"):
        st.markdown(
            '<div class="wt-history-heading">'
            '<p class="wt-h">History</p>'
            f'<span class="wt-history-count">{len(entries)} logged weigh-ins</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        previous = {
            entry["id"]: entries[index - 1]["weight_kg"] if index else None
            for index, entry in enumerate(entries)
        }
        for entry in reversed(entries):
            date_col, weight_col, change_col, note_col, _, edit_col, delete_col = st.columns(
                [1.25, 0.9, 0.85, 0.65, 6.0, 0.55, 0.55],
                vertical_alignment="center",
            )
            display_date = date.fromisoformat(entry["log_date"]).strftime("%b %d, %Y").replace(
                " 0", " "
            )
            date_col.markdown(f"**{display_date}**")
            weight_col.markdown(
                f'<span style="color:var(--sustain-accent)">●</span> {show(entry["weight_kg"])}',
                unsafe_allow_html=True,
            )
            before = previous[entry["id"]]
            if before is None:
                change_col.caption("—")
            else:
                diff = entry["weight_kg"] - before
                color = "var(--sustain-positive)" if diff < 0 else "var(--sustain-caution)" if diff > 0 else "var(--sustain-muted)"
                change_col.markdown(
                    f'<span style="color:{color}">{show(diff, signed=True)}</span>',
                    unsafe_allow_html=True,
                )
            note_col.caption(escape(entry["note"]) if entry["note"] else "—")
            if edit_col.button(
                "", icon=":material/edit:", key=f"weight_edit_{entry['id']}"
            ):
                st.session_state.weight_edit_id = entry["id"]
                for field in ("date", "value", "note"):
                    st.session_state.pop(f"weight_edit_{field}_{entry['id']}", None)
                st.rerun()
            if delete_col.button(
                "", icon=":material/close:", key=f"weight_delete_{entry['id']}",
            ):
                db.delete_weight_entry(user["id"], entry["id"])
                if st.session_state.get("weight_edit_id") == entry["id"]:
                    st.session_state.pop("weight_edit_id", None)
                st.rerun()
            if st.session_state.get("weight_edit_id") == entry["id"]:
                with st.form(f"weight_edit_form_{entry['id']}", border=False):
                    edit_date_col, edit_weight_col, edit_note_col = st.columns(
                        [1.2, 1.1, 3.2], vertical_alignment="bottom"
                    )
                    edit_date = edit_date_col.date_input(
                        "Date",
                        value=date.fromisoformat(entry["log_date"]),
                        max_value=date.today(),
                        key=f"weight_edit_date_{entry['id']}",
                    )
                    edit_weight = edit_weight_col.number_input(
                        f"Body weight ({unit})",
                        min_value=20.0 * factor,
                        max_value=500.0 * factor,
                        value=round(entry["weight_kg"] * factor, 1),
                        step=0.1,
                        format="%.1f",
                        key=f"weight_edit_value_{entry['id']}",
                    )
                    edit_note = edit_note_col.text_input(
                        "Note (optional)",
                        value=entry["note"],
                        max_chars=60,
                        key=f"weight_edit_note_{entry['id']}",
                    )
                    save_col, cancel_col = st.columns([1, 1])
                    save_edit = save_col.form_submit_button("Save")
                    cancel_edit = cancel_col.form_submit_button("Cancel")
                    if save_edit:
                        try:
                            db.update_weight_entry(
                                user["id"],
                                entry["id"],
                                edit_date.isoformat(),
                                round(edit_weight / factor, 2),
                                edit_note.strip(),
                            )
                        except db.IntegrityError:
                            st.error(
                                "Another weigh-in is already logged for that date. "
                                "Choose a different date."
                            )
                        else:
                            st.session_state.pop("weight_edit_id", None)
                            st.rerun()
                    elif cancel_edit:
                        st.session_state.pop("weight_edit_id", None)
                        st.rerun()
