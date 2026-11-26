from datetime import date
from html import escape
from math import ceil, exp, floor
from urllib.parse import quote

import streamlit as st

from services import db, targets as targets_service
from services.tdee_engine import calculate_tdee


# Each colour stands for one series wherever it appears (bars, chart, legend).
COLORS = {
    "calories": "#dc2a46",
    "protein": "#5aa9d6",
    "carbs": "#e2a640",
    "fat": "#9d8fd1",
    "bmr": "#5aa9d6",
    "neat": "#4cc38a",
    "eat": "#e2a640",
    "tef": "#9d8fd1",
}

NUTRIENTS = (
    ("Protein", "protein_g", COLORS["protein"], 4),
    ("Carbohydrates", "carbs_g", COLORS["carbs"], 4),
    ("Fat", "fat_g", COLORS["fat"], 9),
)

MEAL_SLOTS = (
    ("Breakfast", 0.25),
    ("Lunch", 0.35),
    ("Dinner", 0.30),
    ("Snacks", 0.10),
)

BASELINE_DAILY_DEFICIT = 500
WATER_SHIFT_KG_AT_BASELINE = 2.54
WATER_SHIFT_DECAY_RATE = 0.35
TISSUE_LOSS_KG_AT_BASELINE = 9.79
TISSUE_LOSS_DECAY_RATE = 0.0415
CHART_SAMPLES_PER_WEEK = 4
DASHBOARD_CSS = """
<style>
    .block-container { max-width:1440px; padding:2rem clamp(1rem,3vw,2rem) 3rem; }
    .st-key-dashboard_profile { padding:24px; border:1px solid var(--sustain-border);
        border-radius:16px; background:var(--sustain-surface); }
    .st-key-dashboard_edit button {
        min-height:40px; border:1px solid var(--sustain-border); border-radius:8px;
        background:var(--sustain-raised); color:var(--sustain-text); font-weight:500;
        transition:background-color .15s cubic-bezier(.22,1,.36,1);
    }
    .st-key-dashboard_edit button:hover { background:var(--sustain-hover-strong); border-color:var(--sustain-border);
        color:var(--sustain-text); }
    .sd, .sd * { box-sizing:border-box; }
    .sd { color:var(--sustain-text); font-family:inherit; }
    .sd strong { font-weight:600; }
    .sd-hero { padding:0 0 8px; }
    .sd-title { margin:0 0 4px; color:var(--sustain-text); font-size:2rem;
        line-height:1.15; font-weight:500; }
    .sd-subtitle,.sd-muted { color:var(--sustain-secondary); font-size:.875rem; line-height:1.5; }
    .sd-section { padding:32px 0; border-bottom:1px solid var(--sustain-border); }
    .sd-section-head { display:flex; align-items:flex-end; justify-content:space-between;
        flex-wrap:wrap; gap:12px; margin-bottom:16px; }
    .sd-heading { margin:0 0 4px; color:var(--sustain-text); font-size:1.375rem; line-height:1.3; font-weight:500; }
    .sd-kicker { color:var(--sustain-muted); font:400 .75rem/1.4 var(--sustain-mono); }
    .sd-profile-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:20px 32px; margin-top:20px; }
    .sd-profile-item { min-width:0; }
    .sd-profile-label { display:block; margin-bottom:4px; color:var(--sustain-muted); font-size:.8125rem; }
    .sd-profile-value { display:block; color:var(--sustain-text); font-size:1rem; line-height:1.45; font-weight:500; overflow-wrap:anywhere; }
    .sd-calorie-card { padding:24px; border:1px solid var(--sustain-border);
        border-radius:16px; background:var(--sustain-surface); }
    .sd-calorie-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
    .sd-calorie-title { color:var(--sustain-secondary); font-size:.875rem; font-weight:400; }
    .sd-calorie-value { display:block; margin:8px 0 4px; color:var(--sustain-text); font-size:3rem; line-height:1; font-weight:500; font-variant-numeric:tabular-nums; }
    .sd-calorie-subtitle { color:var(--sustain-secondary); font-size:.875rem; }
    .sd-target-list { display:grid; gap:16px; }
    .sd-target-head { display:flex; align-items:baseline; justify-content:space-between;
        flex-wrap:wrap; gap:4px 12px; }
    .sd-target-name { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
    .sd-label { color:var(--sustain-text); font-size:.9375rem; line-height:1.25; font-weight:500; }
    .sd-value { display:block; margin-top:8px; color:var(--sustain-text); font-size:1.75rem; line-height:1.1; font-weight:500; font-variant-numeric:tabular-nums; }
    .sd-subvalue { color:var(--sustain-muted); font:.75rem var(--sustain-mono); }
    .sd-track { position:relative; height:8px; overflow:visible; margin:12px 0 8px;
        border-radius:4px; background:var(--sustain-raised); }
    .sd-fill { height:100%; min-width:2px; border-radius:4px; }
    .sd-tick { position:absolute; z-index:2; top:-4px; height:16px; width:2px; border-radius:1px;
        background:var(--sustain-text); }
    .sd-tick-caption { display:flex; justify-content:space-between; color:var(--sustain-muted);
        font: .625rem var(--sustain-mono); }
    .sd-budget-head { display:flex; justify-content:space-between; flex-wrap:wrap;
        gap:8px; margin:32px 0 12px; }
    .sd-budget-head .sd-kicker { color:var(--sustain-text); font-family:inherit; font-size:.9375rem; font-weight:500; }
    .sd-macro-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; margin-top:16px; }
    .sd-macro-card { min-width:0; padding:20px; border:1px solid var(--sustain-border); border-radius:12px; background:var(--sustain-surface); }
    .sd-macro-head { display:flex; align-items:center; justify-content:space-between; gap:8px; }
    .sd-macro-share { font:.75rem var(--sustain-mono); font-variant-numeric:tabular-nums; }
    .sd-macro-energy { color:var(--sustain-secondary); font-size:.8125rem; font-variant-numeric:tabular-nums; }
    .sd-budget-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; }
    .sd-budget { min-width:0; padding:20px; border:1px solid var(--sustain-border); border-radius:12px; background:var(--sustain-surface); }
    .sd-budget-name { color:var(--sustain-secondary); font-size:.875rem; line-height:1.3; font-weight:400; }
    .sd-budget-cal { margin:8px 0; color:var(--sustain-text); font-size:1.25rem; font-weight:500; font-variant-numeric:tabular-nums; }
    .sd-budget-macros { color:var(--sustain-muted); font:.75rem/1.7 var(--sustain-mono); }
    .sd-insight-title { margin:0 0 12px; color:var(--sustain-text); font-size:1.375rem; line-height:1.3; font-weight:500; }
    .sd-copy { max-width:44rem; color:var(--sustain-secondary); font-size:.9375rem; line-height:1.65; }
    .sd-copy strong { color:var(--sustain-text); }
    .sd-pillars { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; margin:20px 0; }
    .sd-pillar { padding:16px 0 0; border-top:1px solid var(--sustain-border); }
    .sd-pillar-name { display:block; color:var(--sustain-text); font-size:.9375rem; font-weight:500; }
    .sd-pillar-copy { display:block; margin-top:4px; color:var(--sustain-secondary); font-size:.875rem; line-height:1.6; }
    .sd-coaching { margin-top:20px; padding:16px 20px; border:1px solid var(--sustain-border);
        border-radius:12px; background:var(--sustain-surface); }
    .sd-coaching-title { margin-bottom:8px; color:var(--sustain-text); font-size:.875rem; font-weight:500; }
    .sd-coaching ul { margin:0; padding-left:16px; color:var(--sustain-secondary); font-size:.875rem; line-height:1.7; }
    .sd-stats { display:grid; grid-template-columns:repeat(3,1fr); margin:16px 0;
        border-top:1px solid var(--sustain-border); border-bottom:1px solid var(--sustain-border); }
    .sd-stat { padding:12px 16px; }
    .sd-stat + .sd-stat { border-left:1px solid var(--sustain-border); }
    .sd-stat-label { display:block; color:var(--sustain-muted); font-size:.8125rem; }
    .sd-stat-value { display:block; margin-top:4px; color:var(--sustain-text);
        font-size:1.25rem; font-weight:500; font-variant-numeric:tabular-nums; }
    .sd-chart { padding:24px; border:1px solid var(--sustain-border); border-radius:16px; background:var(--sustain-surface); }
    .sd-chart-graph { display:grid; grid-template-columns:24px 48px minmax(0,1fr);
        align-items:stretch; gap:8px; }
    .sd-chart-y-title { display:flex; align-items:center; justify-content:center;
        color:var(--sustain-muted); font-size:.8125rem; font-weight:400;
        writing-mode:vertical-rl; transform:rotate(180deg); }
    .sd-chart-y-axis { display:flex; flex-direction:column; justify-content:space-between;
        height:300px; padding-right:4px; color:var(--sustain-muted); text-align:right;
        font:.75rem var(--sustain-mono); font-variant-numeric:tabular-nums; }
    .sd-chart-plot { position:relative; height:300px; margin:0 0 8px;
        border-bottom:1px solid var(--sustain-border-strong);
        background:repeating-linear-gradient(to bottom,transparent 0,transparent calc(33.333% - 1px),
        var(--sustain-grid) calc(33.333% - 1px),var(--sustain-grid) 33.333%); }
    .sd-chart-line { position:absolute; inset:0; width:100%; height:100%; overflow:visible; }
    .sd-chart-x-axis { display:flex; justify-content:space-between; margin-left:88px; color:var(--sustain-muted);
        font:.75rem var(--sustain-mono); }
    .sd-chart-note { display:flex; flex-wrap:wrap; justify-content:space-between;
        gap:8px; margin-top:16px; color:var(--sustain-muted); font-size:.8125rem; }
    .sd-chart-note strong { color:var(--sustain-text); font-weight:500; }
    .sd-chart-explanation { margin-top:16px; padding-top:16px;
        border-top:1px solid var(--sustain-border); color:var(--sustain-secondary); font-size:.875rem; line-height:1.65; }
    .sd-breakdown { margin:16px 0; padding:20px; border:1px solid var(--sustain-border);
        border-radius:12px; background:var(--sustain-surface); }
    .sd-breakdown-head { display:flex; justify-content:space-between; align-items:center;
        flex-wrap:wrap; gap:8px; margin-bottom:12px; }
    .sd-legend { display:flex; flex-wrap:wrap; gap:12px; color:var(--sustain-secondary); font-size:.8125rem; }
    .sd-legend-item { display:inline-flex; align-items:center; gap:6px; }
    .sd-legend-dot { display:inline-block; width:8px; height:8px; border-radius:50%; }
    .sd-ledger { border-top:1px solid var(--sustain-border); }
    .sd-ledger-row { display:flex; align-items:flex-start; justify-content:space-between;
        flex-wrap:wrap; gap:8px 16px; padding:12px 0; border-bottom:1px solid var(--sustain-border); }
    .sd-ledger-left { min-width:0; flex:1; }
    .sd-ledger-name { color:var(--sustain-text); font-size:.9375rem; font-weight:500; }
    .sd-ledger-desc { display:block; margin-top:4px; color:var(--sustain-secondary); font-size:.8125rem; line-height:1.6; }
    .sd-ledger-value { color:var(--sustain-text); font-size:.9375rem; font-weight:500; white-space:nowrap;
        font-variant-numeric:tabular-nums; }
    .sd-macro-conversions { display:flex; flex-wrap:wrap; gap:8px; padding:12px 0; }
    .sd-conversion { padding:4px 8px; border:1px solid var(--sustain-border); border-radius:6px;
        background:var(--sustain-surface); font:.75rem var(--sustain-mono); }
    @media(max-width:760px) {
        .sd-profile-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        .sd-macro-grid, .sd-pillars { grid-template-columns:1fr; }
        .sd-budget-strip { grid-template-columns:repeat(2,minmax(0,1fr)); }
    }
    @media(max-width:430px) {
        .sd-profile-grid,.sd-budget-strip { grid-template-columns:1fr; }
    }
</style>
"""


def _escape(value):
    return escape(str(value), quote=True)


def _format_number(value):
    return f"{round(value):,}"


def _profile_summary(profile, tdee):
    height = profile.get("height_cm")
    weight = profile.get("weight_kg")
    units = profile.get("measurement_units", "Metric")
    if units == "Imperial":
        height_display = f"{height / 2.54:.1f} in" if height is not None else "Not set"
        weight_display = f"{weight * 2.2046226218:.1f} lb" if weight is not None else "Not set"
    else:
        height_display = f"{height:g} cm" if height is not None else "Not set"
        weight_display = f"{weight:g} kg" if weight is not None else "Not set"
    if height and weight:
        bmi = weight / ((height / 100) ** 2)
        body_summary = (
            f"Body fat {profile['body_fat_pct']:g}%"
            if profile.get("body_fat_pct") is not None
            else f"BMI {bmi:.1f}"
        )
    else:
        body_summary = "Not provided"

    sessions = profile.get("exercise_sessions") or []
    training = ", ".join(
        f"{item.get('sessions_per_week', 0):g}×/wk {item.get('type', 'training')}"
        for item in sessions
        if item.get("sessions_per_week", 0)
    ) or "No scheduled workouts"
    diets = ", ".join(profile.get("diets") or []) or "No diet preferences"
    allergens = ", ".join(profile.get("allergens") or []) or "No exclusions"
    step_count = profile.get("daily_steps", "Not set")
    details = (
        ("Goal", profile.get("fitness_goal", "Not set")),
        (
            "Age and sex",
            f"{profile.get('age', '—')} years · {profile.get('sex', 'Not set')}",
        ),
        ("Body measurements", f"{height_display} · {weight_display} · {body_summary}"),
        (
            "Daily activity",
            f"{profile.get('occupation_type', 'Not set')} · {step_count} steps/day",
        ),
        ("Training", training),
        ("Food preferences", f"{diets} · Excludes: {allergens}"),
        ("Cooking experience", profile.get("cooking_skill", "Not set")),
    )
    details_markup = "".join(
        f'<div class="sd-profile-item"><span class="sd-profile-label">{_escape(label)}</span>'
        f'<span class="sd-profile-value">{_escape(value)}</span></div>'
        for label, value in details
    )
    return f"""
        <div class="sd">
          <div class="sd-profile-grid">{details_markup}</div>
        </div>
    """


def _energy_estimate(tdee):
    return (
        f'<div class="sd"><div class="sd-muted">Energy estimate: '
        f"{_escape(tdee['bmr_method'])}</div></div>"
    )


def _profile_heading():
    return """
        <div class="sd">
          <h2 class="sd-heading">Your nutrition profile</h2>
          <div class="sd-muted">Personalized from the information you shared</div>
        </div>
    """


def _nutrition_section(targets, tdee, goal_delta):
    if goal_delta < -25:
        badge = f"{_format_number(abs(goal_delta))} kcal deficit"
    elif goal_delta > 25:
        badge = f"+{_format_number(goal_delta)} kcal surplus"
    else:
        badge = "Maintenance"
    scale = max(targets["calories"], tdee["tdee_kcal"], 1)
    calorie_fill = min(targets["calories"] / scale * 100, 100)
    maintenance_tick = min(tdee["tdee_kcal"] / scale * 100, 100)

    content = f"""
        <section class="sd-section">
          <div class="sd-section-head">
            <div>
              <h2 class="sd-heading">Daily nutrition targets</h2>
              <div class="sd-muted">Your calorie goal and how it splits across protein, carbs and fat</div>
            </div>
            <span class="sd-kicker">4 · 4 · 9 kcal per gram</span>
          </div>
          <div class="sd-calorie-card">
            <div class="sd-calorie-head">
              <div>
                <div class="sd-calorie-title">Daily calorie target</div>
                <span class="sd-calorie-value">{_format_number(targets['calories'])}</span>
                <span class="sd-calorie-subtitle">kcal per day · {_escape(badge)}</span>
              </div>
            </div>
            <div class="sd-track" aria-label="Calorie target compared with maintenance">
              <span class="sd-tick" style="left:{maintenance_tick:.2f}%;"
                title="Estimated maintenance: {_format_number(tdee['tdee_kcal'])} kcal"></span>
              <div class="sd-fill" style="width:{calorie_fill:.2f}%;background:{COLORS['calories']}"></div>
            </div>
            <div class="sd-muted">Estimated maintenance: {_format_number(tdee['tdee_kcal'])} kcal/day</div>
          </div>
          <div class="sd-macro-grid">
    """
    macro_energy = sum(targets[key] * factor for _, key, _, factor in NUTRIENTS)
    for label, key, color, factor in NUTRIENTS:
        grams = targets[key]
        macro_kcal = grams * factor
        share = macro_kcal / max(macro_energy, 1) * 100
        content += f"""
            <div class="sd-macro-card">
              <div class="sd-macro-head">
                <span class="sd-label">{_escape(label)}</span>
                <span class="sd-macro-share" style="color:{color}">{share:.0f}%</span>
              </div>
              <span class="sd-value">{_format_number(grams)} g</span>
              <div class="sd-macro-energy">{_format_number(macro_kcal)} kcal</div>
              <div class="sd-track" aria-label="{_escape(label)} target: {share:.0f}% of macro calories">
                <div class="sd-fill" style="width:{share:.2f}%;background:{color}"></div>
              </div>
            </div>
        """
    content += """
          </div>
          <div class="sd-budget-head">
            <span class="sd-kicker">Suggested budget per meal</span>
            <span class="sd-muted">A guide for planning meals in your diary</span>
          </div>
          <div class="sd-budget-strip">
    """
    for slot, share in MEAL_SLOTS:
        content += f"""
            <div class="sd-budget">
              <div class="sd-budget-name">{slot} · {share:.0%}</div>
              <div class="sd-budget-cal">{_format_number(targets['calories'] * share)} kcal</div>
              <div class="sd-budget-macros">
                P {round(targets['protein_g'] * share)}g ·
                C {round(targets['carbs_g'] * share)}g ·
                F {round(targets['fat_g'] * share)}g
              </div>
            </div>
        """
    return content + "</div></section>"


def _projected_weight(start_weight, daily_deficit, week):
    deficit_scale = max(daily_deficit, 0) / BASELINE_DAILY_DEFICIT
    water_shift = WATER_SHIFT_KG_AT_BASELINE * (
        1 - exp(-WATER_SHIFT_DECAY_RATE * week)
    )
    tissue_loss = TISSUE_LOSS_KG_AT_BASELINE * (
        1 - exp(-TISSUE_LOSS_DECAY_RATE * week)
    )
    return start_weight - deficit_scale * (water_shift + tissue_loss)


def _trajectory_chart(
    weight, daily_deficit, measurement_units="Metric", metric="Weight", calorie_target=0
):
    is_weight = metric == "Weight"
    weight_factor = 2.2046226218 if measurement_units == "Imperial" else 1
    unit = "lb" if measurement_units == "Imperial" else "kg"
    if is_weight:
        values = [
            _projected_weight(weight, daily_deficit, week) * weight_factor
            for week in range(25)
        ]
        axis_title = f"Weight ({unit})"
        tooltip_unit = unit
        axis_color = COLORS["protein"]
    else:
        values = [float(calorie_target)] * 25
        axis_title = "Calories (kcal/day)"
        tooltip_unit = "kcal/day"
        axis_color = COLORS["calories"]

    low = floor(min(values))
    high = ceil(max(values))
    if high == low:
        padding = max(1, round(abs(high) * 0.05))
        low -= padding
        high += padding

    # One continuous SVG path sampled every quarter-week, so the dotted line
    # is smooth and its dots are evenly spaced. The SVG stretches to fill the
    # plot; non-scaling-stroke keeps the dots round at any size.
    view_width, view_height = 1000, 300
    samples = CHART_SAMPLES_PER_WEEK * 24
    if is_weight:
        curve = [
            _projected_weight(weight, daily_deficit, step / CHART_SAMPLES_PER_WEEK)
            * weight_factor
            for step in range(samples + 1)
        ]
    else:
        curve = [values[0]] * (samples + 1)
    points = " ".join(
        f"{step / samples * view_width:.2f},"
        f"{(high - value) / (high - low) * view_height:.2f}"
        for step, value in enumerate(curve)
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_width} {view_height}" '
        'preserveAspectRatio="none" overflow="visible">'
        f'<polyline points="{points}" fill="none" stroke="{axis_color}" '
        'stroke-width="4" stroke-linecap="round" stroke-linejoin="round" '
        'stroke-dasharray="0 9" vector-effect="non-scaling-stroke"/></svg>'
    )
    # st.html strips inline <svg>, so the line is embedded as an image instead.
    line = (
        f'<img class="sd-chart-line" alt="" aria-hidden="true" '
        f'src="data:image/svg+xml,{quote(svg)}">'
    )
    y_ticks = "".join(
        f"<span>{high - (high - low) * tick / 3:.0f}</span>"
        for tick in range(4)
    )
    return f"""
        <div class="sd-chart-graph">
          <div class="sd-chart-y-title">{axis_title}</div>
          <div class="sd-chart-y-axis" aria-hidden="true">{y_ticks}</div>
          <div class="sd-chart-plot" role="group"
            aria-label="24-week {axis_title.lower()} estimate: {values[0]:.1f} {tooltip_unit} at week 0 to {values[-1]:.1f} {tooltip_unit} at week 24.">
            {line}
          </div>
        </div>
        <div class="sd-chart-x-axis">
          <span>Week 0</span><span>Week 4</span><span>Week 8</span>
          <span>Week 12</span><span>Week 16</span><span>Week 20</span><span>Week 24</span>
        </div>
    """


def _projection_markup(
    profile, goal_delta, metric="Weight", calorie_target=0,
    stats_below_chart=False, estimate_weeks=(1, 12, 24),
):
    weight = profile.get("weight_kg")
    if weight is None:
        return '<div class="sd-muted">Add a current weight in Settings to show a trend estimate.</div>'
    measurement_units = profile.get("measurement_units", "Metric")
    factor = 2.2046226218 if measurement_units == "Imperial" else 1
    unit = "lb" if measurement_units == "Imperial" else "kg"
    daily_deficit = max(-goal_delta, 0)
    estimates = {
        week: _projected_weight(weight, daily_deficit, week) * factor
        for week in estimate_weeks
    }
    week_1 = estimates.get(1, estimates[estimate_weeks[0]])
    weekly_change = week_1 - weight * factor
    weekly_change_text = f"{weekly_change:+.1f} {unit}"
    explanation = (
        "Weight change is not perfectly linear. Early changes may be faster as "
        "glycogen and its associated water shift; after that, the expected rate "
        "gradually slows as body weight and energy needs change. This curve is "
        "an illustration, not a promise - real results vary."
        if daily_deficit > 0
        else "This weight-loss curve is shown for a calorie deficit. Your current "
        "target is at or above estimated maintenance, so the chart stays level."
    )
    if metric == "Calories":
        stats = f"""
          <div class="sd-stat"><span class="sd-stat-label">Daily target</span>
            <span class="sd-stat-value">{_format_number(calorie_target)} kcal</span></div>
          <div class="sd-stat"><span class="sd-stat-label">Week 12 target</span>
            <span class="sd-stat-value">{_format_number(calorie_target)} kcal</span></div>
          <div class="sd-stat"><span class="sd-stat-label">Week 24 target</span>
            <span class="sd-stat-value">{_format_number(calorie_target)} kcal</span></div>
        """
        weekly_change_label = f"Expected weight change next week: {weekly_change_text}"
    else:
        stats = "".join(
            f'<div class="sd-stat"><span class="sd-stat-label">{week}-week estimate</span>'
            '<span class="sd-stat-value">'
            f'{estimates[week]:.1f} {unit}</span></div>'
            for week in estimate_weeks
        )
        weekly_change_label = f"Expected change next week: {weekly_change_text}"
    stats_markup = f'<div class="sd-stats">{stats}</div>'
    chart_markup = f"""
        <div class="sd-chart">
          {_trajectory_chart(
              weight, daily_deficit, measurement_units, metric, calorie_target
          )}
          <div class="sd-chart-note">
            <strong>{weekly_change_label}</strong>
            <span>Illustrative estimate at a {_format_number(daily_deficit)} kcal/day deficit</span>
            <span>Not a forecast or medical advice</span>
          </div>
          <div class="sd-chart-explanation">{explanation}</div>
        </div>
    """
    return (
        f"{chart_markup}{stats_markup}"
        if stats_below_chart
        else f"{stats_markup}{chart_markup}"
    )


def _strategy_markup(profile, targets, tdee, goal_delta):
    if goal_delta < -25:
        energy_strategy = (
            f"About {_format_number(abs(goal_delta))} kcal/day below estimated "
            "maintenance. Actual progress varies."
        )
    elif goal_delta > 25:
        energy_strategy = (
            f"About {_format_number(goal_delta)} kcal/day above estimated maintenance. "
            "Actual outcomes vary."
        )
    else:
        energy_strategy = "Targets are set close to estimated maintenance."
    weight = profile.get("weight_kg")
    protein_basis = (
        f"About {targets['protein_g'] / weight:.1f} g/kg of current bodyweight."
        if weight else "Based on your saved profile."
    )
    return f"""
        <h2 class="sd-insight-title">How the plan works</h2>
        <p class="sd-copy">
          Your <strong>{_escape(profile.get('fitness_goal', 'selected goal'))}</strong>
          nutrition plan is based on your saved profile and estimated energy needs.
          Targets are a starting point, not a guarantee of results.
        </p>
        <div class="sd-pillars">
          <div class="sd-pillar"><span class="sd-pillar-name">Energy strategy</span>
            <span class="sd-pillar-copy">{_escape(energy_strategy)}</span></div>
          <div class="sd-pillar"><span class="sd-pillar-name">Lean-mass support</span>
            <span class="sd-pillar-copy">{targets['protein_g']} g protein/day. {_escape(protein_basis)}</span></div>
          <div class="sd-pillar"><span class="sd-pillar-name">Recipe &amp; skill tailoring</span>
            <span class="sd-pillar-copy">Recipes can account for your {_escape(profile.get('cooking_skill', 'selected'))}
              cooking skill, diet preferences, and saved exclusions.</span></div>
        </div>
        <div class="sd-coaching">
          <div class="sd-coaching-title">About these estimates</div>
          <ul>
            <li>Energy and macro targets are estimates based on the information you provided.</li>
            <li>Activity estimates and step ranges may differ from your actual expenditure.</li>
            <li>Consult a qualified professional for medical or individualized nutrition needs.</li>
          </ul>
        </div>
    """


def _tdee_markup(profile, targets, tdee, goal_delta):
    components = (
        ("BMR", "bmr_kcal", COLORS["bmr"]),
        ("NEAT", "neat_kcal", COLORS["neat"]),
        ("EAT", "eat_kcal", COLORS["eat"]),
        ("TEF", "tef_kcal", COLORS["tef"]),
    )
    total = max(sum(tdee[key] for _, key, _ in components), 1)
    segments = "".join(
        f'<span title="{name}: {_format_number(tdee[key])} kcal" '
        f'style="display:block;width:{max(tdee[key] / total * 100, 0):.3f}%;'
        f'background:{color}"></span>'
        for name, key, color in components
    )
    legend = "".join(
        f'<span class="sd-legend-item"><i class="sd-legend-dot" '
        f'style="background:{color}"></i>{name}</span>'
        for name, _, color in components
    )
    if tdee["bmr_method"] == "Katch-McArdle":
        lean_mass = profile["weight_kg"] * (1 - profile["body_fat_pct"] / 100)
        bmr_desc = f"Katch-McArdle: 370 + (21.6 × {lean_mass:.1f} kg lean mass)."
    else:
        bmr_desc = "Mifflin-St Jeor equation; uses age, sex, height, and weight."

    sessions = tdee["exercise_sessions_used"]
    if sessions:
        session_summary = ", ".join(
            f"{item['sessions_per_week']:g} × {item['duration_minutes']:g} min "
            f"(MET {item['met']:g})"
            for item in sessions
            if item["sessions_per_week"]
        )
        eat_desc = f"Net-MET exercise estimate averaged over seven days: {session_summary}."
    else:
        eat_desc = "No structured exercise sessions were included in this estimate."

    rows = (
        ("Basal Metabolic Rate (BMR)", bmr_desc, "bmr_kcal", COLORS["bmr"]),
        (
            "Non-Exercise Activity (NEAT)",
            f"{profile.get('occupation_type', 'Selected occupation')} plus step-based movement; "
            f"approximately {tdee['step_count_used']:,} steps/day used.",
            "neat_kcal",
            COLORS["neat"],
        ),
        ("Exercise Activity (EAT)", eat_desc, "eat_kcal", COLORS["eat"]),
        (
            "Thermic Effect of Food (TEF)",
            f"(P × 1.0) + (C × 0.30) + (F × 0.135) using the saved macro targets.",
            "tef_kcal",
            COLORS["tef"],
        ),
    )
    ledger_rows = "".join(
        f"""
        <div class="sd-ledger-row">
          <div class="sd-ledger-left">
            <span class="sd-ledger-name"><i class="sd-legend-dot" style="background:{color};margin-right:8px"></i>{_escape(title)}</span>
            <span class="sd-ledger-desc">{_escape(description)}</span>
          </div>
          <span class="sd-ledger-value">{_format_number(tdee[key])} kcal</span>
        </div>
        """
        for title, description, key, color in rows
    )
    if goal_delta < -25:
        adjustment = f"−{_format_number(abs(goal_delta))} kcal estimated deficit"
    elif goal_delta > 25:
        adjustment = f"+{_format_number(goal_delta)} kcal estimated surplus"
    else:
        adjustment = "No material adjustment from estimated maintenance"

    conversions = []
    for name, key, color, factor in NUTRIENTS:
        kcal = targets[key] * factor
        conversions.append(
            f'<span class="sd-conversion">'
            f'{name[0]}: {kcal:,} ÷ {factor} = {targets[key]}g</span>'
        )
    macro_energy = sum(targets[key] * factor for _, key, _, factor in NUTRIENTS)
    return f"""
        <section class="sd-section">
          <div class="sd-section-head">
            <div>
              <h2 class="sd-heading">How your calories and macros are calculated</h2>
              <div class="sd-muted">Total daily energy (TDEE) = BMR + NEAT + EAT + TEF</div>
            </div>
            <span class="sd-kicker">Maintenance {_format_number(tdee['tdee_kcal'])} kcal
              → Target {_format_number(targets['calories'])} kcal</span>
          </div>
          <div class="sd-breakdown">
            <div class="sd-breakdown-head">
              <span class="sd-label">Where your daily energy goes</span>
              <span class="sd-legend">{legend}</span>
            </div>
            <div style="display:flex;gap:2px;height:12px;overflow:hidden;
              border-radius:4px;background:var(--sustain-raised)">{segments}</div>
          </div>
          <div class="sd-ledger">
            {ledger_rows}
            <div class="sd-ledger-row">
              <div class="sd-ledger-left">
                <span class="sd-ledger-name"><i class="sd-legend-dot"
                  style="background:{COLORS['calories']};margin-right:8px"></i>Goal adjustment and macro energy</span>
                <span class="sd-ledger-desc">{adjustment} · Target {targets['calories']:,} kcal.
                  Macro conversion uses 4 kcal/g for protein and carbs, and 9 kcal/g for fat;
                  rounded values may differ slightly.</span>
              </div>
              <span class="sd-ledger-value">{macro_energy:,} kcal from macros</span>
            </div>
          </div>
          <div class="sd-macro-conversions">{''.join(conversions)}</div>
        </section>
    """


def _dashboard_header(username):
    return f"""
        <header class="sd-hero">
          <h1 class="sd-title">Nutrition plan</h1>
          <div class="sd-subtitle">{_escape(username)} ·
            {_escape(date.today().strftime('%A, %d %B %Y'))}</div>
        </header>
    """


def _dashboard_markup(profile, targets, tdee, goal_delta):
    return f"""
        <main class="sd">
          {_nutrition_section(targets, tdee, goal_delta)}
        </main>
    """


def render_dashboard_page():
    user = st.session_state.user
    profile = db.get_profile(user["id"])
    if profile is None:
        st.info("Complete onboarding to create your personalized dashboard.")
        return

    targets = targets_service.recalibrate(user["id"])
    if targets is None:
        st.info("Your nutrition targets are not available yet. Please check your profile.")
        return

    tdee = calculate_tdee(profile, macros=targets)
    goal_delta = targets["calories"] - tdee["tdee_kcal"]

    header = (
        f'{DASHBOARD_CSS}<main class="sd">'
        f'{_dashboard_header(user["username"])}</main>'
    )
    st.html(header)
    with st.container(key="dashboard_profile"):
        st.html(_profile_heading())
        st.html(f"{DASHBOARD_CSS}{_profile_summary(profile, tdee)}")
        estimate_column, edit_column = st.columns(
            [5, 1.6], vertical_alignment="center"
        )
        estimate_column.html(_energy_estimate(tdee))
        with edit_column:
            if st.button(
                "Edit profile",
                key="dashboard_edit",
                icon=":material/edit:",
                use_container_width=True,
            ):
                st.session_state["navigation_target"] = "Settings"
                st.rerun()

    st.html(_dashboard_markup(profile, targets, tdee, goal_delta))

    st.html(
        f'{DASHBOARD_CSS}<main class="sd"><section class="sd-section">'
        f'{_strategy_markup(profile, targets, tdee, goal_delta)}'
        "</section></main>"
    )
    st.html(
        f'{DASHBOARD_CSS}<main class="sd"><section class="sd-section">'
        '<h2 class="sd-insight-title">Expected trajectory over 24 weeks</h2>'
        "</section></main>"
    )
    metric = st.segmented_control(
        "Trajectory metric",
        ["Weight", "Calories"],
        default="Weight",
        key="dashboard_trajectory_metric",
        label_visibility="collapsed",
    )
    st.html(
        f'{DASHBOARD_CSS}<main class="sd">'
        f'{_projection_markup(profile, goal_delta, metric or "Weight", targets["calories"])}'
        "</main>"
    )
    st.html(
        f'{DASHBOARD_CSS}<main class="sd">'
        f'{_tdee_markup(profile, targets, tdee, goal_delta)}'
        "</main>"
    )
