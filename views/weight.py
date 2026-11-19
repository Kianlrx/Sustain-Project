# Weight page: log weigh-ins, see them on a chart against the expected curve.
from datetime import date, timedelta
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from services import db, targets as targets_service
from services.tdee_engine import calculate_tdee
from views.dashboard import _projected_weight

LB_PER_KG = 2.2046226218
# Within this many kcal of maintenance the expected weight is flat.
MAINTENANCE_BAND_KCAL = 25
GREEN, RED, BLUE = "#34d399", "#ff4b4b", "#38bdf8"
# Red trend line: needs this many logs to smooth, fits this share of them at a time.
TREND_MIN_LOGS = 6
TREND_MIN_NEIGHBOURS = 5
TREND_SHARE = 0.05
# The chart can never be zoomed in past this many days (or out past the logged dates).
MIN_WINDOW_DAYS = 7
RANGES ={"7D": 7, "1M": 31, "6M": 183, "1Y": 365, "All": None}

WEIGHT_CSS = """
<style>
    .st-key-weight_form, .st-key-weight_history {
        padding: 1.1rem 1.25rem;
        border: 1px solid #262d3d;
        border-radius: 14px;
        background: #161b24;
    }
    .st-key-weight_form [data-testid="stForm"] {
        padding: 0;
        border: 0;
    }
    .st-key-weight_history button {
        min-height: 1.9rem;
        border: 0;
        background: transparent;
        color: #64748b;
    }
    .st-key-weight_history button:hover {
        background: rgba(255, 75, 75, .14);
        color: #ff4b4b;
    }
    .wt-head { display:flex; align-items:center; gap:.7rem; flex-wrap:wrap; }
    .wt-title { margin:0; font-size:1.9rem; font-weight:750; letter-spacing:-.02em; color:#f8fafc; }
    .wt-sub { margin:.2rem 0 1rem; color:#94a3b8; font-size:.9rem; }
    .wt-kpis { display:grid; grid-template-columns:repeat(4, 1fr); gap:.9rem; margin-bottom:1.1rem; }
    @media (max-width: 1100px) { .wt-kpis { grid-template-columns:repeat(2, 1fr); } }
    .wt-kpi { display:flex; flex-direction:column; gap:.45rem; padding:1rem 1.15rem;
        border:1px solid #262d3d; border-radius:12px; background:#161b24; }
    .wt-kpi-top { display:flex; justify-content:space-between; align-items:center; gap:.5rem; }
    .wt-kpi-label { color:#94a3b8; font-size:.8rem; font-weight:500; }
    .wt-badge { padding:.1rem .55rem; border:1px solid #262d3d; border-radius:999px;
        background:#1e222d; color:#94a3b8; font-size:.72rem; font-weight:650; }
    .wt-badge.green { color:#34d399; background:rgba(52,211,153,.12); border-color:rgba(52,211,153,.28); }
    .wt-badge.blue { color:#38bdf8; background:rgba(56,189,248,.12); border-color:rgba(56,189,248,.28); }
    .wt-badge.red { color:#ff4b4b; background:rgba(255,75,75,.12); border-color:rgba(255,75,75,.28); }
    .wt-kpi-value { color:#f8fafc; font-size:1.7rem; line-height:1.15; font-weight:750;
        letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
    .wt-kpi-foot { display:flex; justify-content:space-between; gap:.5rem; color:#64748b;
        font-size:.76rem; font-variant-numeric:tabular-nums; }
    .wt-h { margin:0 0 .15rem; color:#f8fafc; font-size:1.05rem; font-weight:650; }
    .wt-muted { color:#94a3b8; font-size:.82rem; }
    .st-key-weight_chart {
        margin-bottom: 1.1rem;
        padding: 1.1rem 1.25rem;
        border: 1px solid #262d3d;
        border-radius: 14px;
        background: #161b24;
    }
    .wt-legend { display:flex; flex-wrap:wrap; gap:.6rem; margin:.2rem 0 .8rem; }
    .wt-legend span { display:inline-flex; align-items:center; gap:.5rem; padding:.28rem .7rem;
        border:1px solid #262d3d; border-radius:8px; background:#1e222d;
        color:#f8fafc; font-size:.78rem; font-weight:500; }
    .wt-dot { width:.65rem; height:.65rem; border-radius:50%; display:inline-block; }
    .wt-bar { width:1rem; height:3px; border-radius:2px; display:inline-block; }
    .wt-dots { width:1.1rem; border-top:3px dotted; display:inline-block; }
    .wt-empty { padding:2.2rem 1rem; text-align:center; color:#94a3b8;
        border:1px dashed #262d3d; border-radius:14px; background:#161b24; }
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
    logs = logs[(logs["date"] >= start_ts) & (logs["date"] <= end_ts)]
    plan = plan[(plan["date"] >= start_ts) & (plan["date"] <= end_ts)]

    x = alt.X(
        "date:T",
        title=None,
        scale=alt.Scale(
            domain=[
                (start_ts - pd.Timedelta(hours=10)).isoformat(),
                (end_ts + pd.Timedelta(hours=10)).isoformat(),
            ]
        ),
        axis=alt.Axis(format="%b %d", labelColor="#64748b", grid=False, domainColor="#262d3d"),
    )
    y = alt.Y(
        "weight:Q",
        title=f"Weight ({unit})",
        scale=alt.Scale(zero=False, nice=True, padding=12),
        axis=alt.Axis(labelColor="#64748b", titleColor="#94a3b8", gridColor="#1e2433", domain=False),
    )
    hover = alt.selection_point(on="pointerover", nearest=True, fields=["date"], empty=False)

    expected_line = (
        alt.Chart(plan)
        .mark_line(color=BLUE, strokeWidth=2.6, strokeDash=[1, 7], strokeCap="round")
        .encode(x=x, y=y)
    )
    average_line = (
        alt.Chart(logs)
        .mark_line(color=RED, strokeWidth=2.4)
        .encode(x=x, y=alt.Y("average:Q", scale=alt.Scale(zero=False, nice=True, padding=12)))
    )
    dots = (
        alt.Chart(logs)
        .mark_circle(color=GREEN, stroke="#0e1117", strokeWidth=1.5, opacity=1)
        .encode(
            x=x,
            y=y,
            size=alt.condition(hover, alt.value(190), alt.value(70)),
            tooltip=[
                alt.Tooltip("date:T", title="Date", format="%a, %b %d, %Y"),
                alt.Tooltip("weight:Q", title=f"Weight ({unit})", format=".1f"),
                alt.Tooltip("note:N", title="Note"),
            ],
        )
        .add_params(hover)
    )
    return (
        alt.layer(expected_line, average_line, dots)
        .properties(height=340, background="#161b24")
        .configure_view(stroke=None)
    )


def _kpi(label, badge, badge_class, value, left, right, value_color="#f8fafc"):
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
        '<div class="wt-head"><h1 class="wt-title">Weight Logging</h1></div>'
        '<p class="wt-sub">Log your weight and compare it with the expected '
        "curve for your calorie target.</p>",
        unsafe_allow_html=True,
    )
    if message := st.session_state.pop("weight_message", None):
        st.success(message)

    entries = db.get_weight_entries(user["id"])
    tdee = calculate_tdee(profile, macros=targets)
    goal_delta = targets["calories"] - tdee["tdee_kcal"]

    if entries:
        first, latest = entries[0], entries[-1]
        end_date = max(date.fromisoformat(latest["log_date"]), date.today())
        expected = expected_weights(
            date.fromisoformat(first["log_date"]),
            first["weight_kg"],
            end_date,
            goal_delta,
        )
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
                    value_color="#34d399" if period <= 0 else "#fbbf24",
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

    if len(entries) >= 2:
        with st.container(key="weight_chart"):
            heading, ranges = st.columns([2, 3], vertical_alignment="center")
            heading.markdown(
                '<p class="wt-h">Weight Trajectory</p>'
                '<p class="wt-muted">Hover a green dot for its date and weight.'
                "<br>Use the range buttons or slider to zoom.</p>",
                unsafe_allow_html=True,
            )
            first_day = date.fromisoformat(entries[0]["log_date"])
            last_day = max(date.fromisoformat(entries[-1]["log_date"]), date.today())

            def pick_range():
                days = RANGES[st.session_state.weight_range or "All"]
                st.session_state.weight_window = (
                    (first_day if days is None else max(first_day, last_day - timedelta(days=days - 1))),
                    last_day,
                )

            ranges.segmented_control(
                "Range",
                list(RANGES),
                default="All",
                key="weight_range",
                on_change=pick_range,
                label_visibility="collapsed",
            )
            if "weight_window" not in st.session_state:
                pick_range()
            # Re-clamp every run: the slider can't leave the logged dates, and the
            # window can't shrink below MIN_WINDOW_DAYS.
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
    elif entries:
        st.markdown(
            '<div class="wt-empty">Log at least one more weigh-in on a different '
            "day to see your chart.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="wt-empty">No weigh-ins yet. Log your first one below to '
            "start your chart.</div>",
            unsafe_allow_html=True,
        )

    form_col, history_col = st.columns([1, 1.8], gap="medium")
    with form_col:
        with st.container(key="weight_form"):
            st.markdown(
                '<p class="wt-h">Quick Weigh-In</p>'
                '<p class="wt-muted">One weigh-in per day. Logging the same day again '
                "replaces it.</p>",
                unsafe_allow_html=True,
            )
            default_kg = entries[-1]["weight_kg"] if entries else profile.get("weight_kg", 70.0)
            with st.form("weight_log_form", border=False):
                weight = st.number_input(
                    f"Body weight ({unit})",
                    min_value=20.0 * factor,
                    max_value=500.0 * factor,
                    value=round(default_kg * factor, 1),
                    step=0.1,
                    format="%.1f",
                )
                log_date = st.date_input("Date", value=date.today(), max_value=date.today())
                note = st.text_input("Note (optional)", max_chars=60)
                if st.form_submit_button("Log weight", type="primary", use_container_width=True):
                    db.save_weight_entry(
                        user["id"], log_date.isoformat(), round(weight / factor, 2), note.strip()
                    )
                    st.session_state.weight_message = (
                        f"Logged {weight:.1f} {unit} for {log_date.strftime('%b %d, %Y')}."
                    )
                    st.rerun()

    with history_col:
        with st.container(key="weight_history"):
            st.markdown(
                '<p class="wt-h">Weigh-In History</p>'
                f'<p class="wt-muted">Latest {min(len(entries), 12)} of {len(entries)} logs</p>',
                unsafe_allow_html=True,
            )
            if not entries:
                st.caption("Nothing logged yet.")
            previous = {
                entry["id"]: entries[index - 1]["weight_kg"] if index else None
                for index, entry in enumerate(entries)
            }
            for entry in reversed(entries[-12:]):
                date_col, weight_col, change_col, note_col, delete_col = st.columns(
                    [2.2, 1.3, 1.2, 2.4, 0.6], vertical_alignment="center"
                )
                date_col.markdown(f"**{_long_date(entry['log_date'])}**")
                weight_col.markdown(
                    f'<span style="color:#34d399">●</span> {show(entry["weight_kg"])}',
                    unsafe_allow_html=True,
                )
                before = previous[entry["id"]]
                if before is None:
                    change_col.caption("—")
                else:
                    diff = entry["weight_kg"] - before
                    color = "#34d399" if diff < 0 else "#fbbf24" if diff > 0 else "#94a3b8"
                    change_col.markdown(
                        f'<span style="color:{color}">{show(diff, signed=True)}</span>',
                        unsafe_allow_html=True,
                    )
                note_col.caption(escape(entry["note"]) if entry["note"] else "—")
                if delete_col.button(
                    "", icon=":material/close:", key=f"weight_delete_{entry['id']}",
                    help="Delete this weigh-in",
                ):
                    db.delete_weight_entry(user["id"], entry["id"])
                    st.rerun()
