from datetime import date
from html import escape
from math import atan2, ceil, degrees, exp, floor

import streamlit as st

from services import db, targets as targets_service
from services.tdee_engine import calculate_tdee


COLORS = {
    "calories": "#ff4b4b",
    "protein": "#38bdf8",
    "carbs": "#fbbf24",
    "fat": "#a78bfa",
    "bmr": "#38bdf8",
    "neat": "#34d399",
    "eat": "#fbbf24",
    "tef": "#a78bfa",
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
DASHBOARD_CSS = """
<style>
    [data-testid="stAppViewContainer"] { background:#0e1117; color:#e2e8f0; }
    [data-testid="stHeader"] { background:rgba(14,17,23,.94); }
    [data-testid="stSidebar"] { background:#11151e; }
    [data-testid="stSidebar"] { width:232px !important; min-width:232px !important; }
    .block-container { max-width:1080px; padding:2rem clamp(1rem,2vw,1.5rem) 3rem; }
    .st-key-dashboard_edit button {
        min-height:40px; border:1px solid #343b4e; border-radius:8px;
        margin-top:.35rem; margin-bottom:.75rem;
        background:#1e222d; color:#e2e8f0;
    }
    .st-key-dashboard_edit button:hover {
        border-color:rgba(255,75,75,.65); background:#262c3a; color:#fff;
    }
    .st-key-dashboard_diary button {
        min-height:40px; border:1px solid #ff4b4b; border-radius:8px;
        margin-top:.35rem; margin-bottom:.75rem;
        background:#ff4b4b; color:#fff;
    }
    .st-key-dashboard_diary button:hover {
        border-color:#ff6363; background:#ff6363; color:#fff;
    }
    .sd, .sd * { box-sizing:border-box; }
    .sd { color:#e2e8f0; font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    .sd-hero { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap;
        gap:1rem; padding:.1rem 0 .45rem; }
    .sd-brand { display:flex; align-items:center; gap:.75rem; }
    .sd-logo { width:42px; height:42px; display:grid; place-items:center; border-radius:11px;
        color:#fff; font-size:1.25rem; font-weight:800;
        background:linear-gradient(135deg,#ff6363,#ff334b); }
    .sd-brand-name { color:#fff; font-size:1.2rem; font-weight:800; letter-spacing:-.03em; }
    .sd-status { display:inline-flex; align-items:center; gap:.4rem; border-radius:999px;
        padding:.32rem .62rem; color:#34d399; font-size:.8rem; font-weight:700;
        background:rgba(52,211,153,.1); border:1px solid rgba(52,211,153,.3); }
    .sd-title { margin:.75rem 0 .25rem; color:#fff; font-size:clamp(1.75rem,3vw,2rem);
        line-height:1.2; letter-spacing:-.04em; font-weight:800; }
    .sd-subtitle,.sd-muted { color:#b0bdcf; font-size:.9rem; line-height:1.55; }
    .sd-section { padding:2rem 0; border-bottom:1px solid #262c3a; }
    .sd-section-head { display:flex; align-items:flex-end; justify-content:space-between;
        flex-wrap:wrap; gap:.65rem; margin-bottom:1rem; }
    .sd-heading { margin:0; color:#fff; font-size:1.35rem; line-height:1.35; font-weight:750; }
    .sd-kicker { color:#b0bdcf; font: .78rem ui-monospace,SFMono-Regular,Consolas,monospace;
        letter-spacing:.08em; text-transform:uppercase; }
    .sd-profile-card { padding:1.25rem; border:1px solid #343b4e; border-radius:14px; background:#161b26; }
    .sd-profile-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1.25rem 2rem; }
    .sd-profile-item { min-width:0; }
    .sd-profile-label { display:block; margin-bottom:.3rem; color:#b0bdcf; font-size:.82rem; }
    .sd-profile-value { display:block; color:#f8fafc; font-size:1rem; line-height:1.45; font-weight:650; overflow-wrap:anywhere; }
    .sd-calorie-card { padding:1.35rem 1.5rem; border:1px solid rgba(255,75,75,.4);
        border-radius:14px; background:linear-gradient(110deg,rgba(255,75,75,.13),#161b26 70%); }
    .sd-calorie-head { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
    .sd-calorie-title { color:#fff; font-size:1.05rem; font-weight:700; }
    .sd-calorie-value { display:block; margin:.35rem 0; color:#fff; font-size:2rem; line-height:1.2; font-weight:800; font-variant-numeric:tabular-nums; }
    .sd-calorie-subtitle { color:#b0bdcf; font-size:.9rem; }
    .sd-target-list { display:grid; gap:1rem; }
    .sd-target-head { display:flex; align-items:baseline; justify-content:space-between;
        flex-wrap:wrap; gap:.35rem .8rem; }
    .sd-target-name { display:flex; align-items:center; flex-wrap:wrap; gap:.5rem; }
    .sd-label { color:#f8fafc; font-size:1.05rem; line-height:1.25; font-weight:700; }
    .sd-value { color:#fff; font-size:1.55rem; font-weight:800; font-variant-numeric:tabular-nums; }
    .sd-subvalue { color:#b0bdcf; font:.78rem ui-monospace,SFMono-Regular,Consolas,monospace; }
    .sd-track { position:relative; height:16px; overflow:visible; margin:.65rem 0 .25rem;
        border:1px solid #262c3a; border-radius:999px;
        background:repeating-linear-gradient(90deg,#1e222d 0,#1e222d calc(25% - 1px),#303543 25%); }
    .sd-fill { height:100%; min-width:2px; border-radius:999px; }
    .sd-tick { position:absolute; z-index:2; top:-4px; height:20px; width:2px; background:#e2e8f0; }
    .sd-tick-caption { display:flex; justify-content:space-between; color:#94a3b8;
        font: .62rem ui-monospace,SFMono-Regular,Consolas,monospace; }
    .sd-budget-head { display:flex; justify-content:space-between; flex-wrap:wrap;
        gap:.4rem; margin:1.25rem 0 .55rem; }
    .sd-macro-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1rem; margin-top:1rem; }
    .sd-macro-card { min-width:0; padding:1rem; border:1px solid #343b4e; border-radius:12px; background:#161b26; }
    .sd-macro-head { display:flex; align-items:center; justify-content:space-between; gap:.5rem; }
    .sd-macro-share { padding:.2rem .55rem; border-radius:999px; font-size:.8rem; font-weight:750; background:#1e293b; }
    .sd-macro-energy { color:#b0bdcf; font-size:.85rem; }
    .sd-budget-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1rem; }
    .sd-budget { min-width:0; padding:1rem; border:1px solid #343b4e; border-radius:12px; background:#161b26; }
    .sd-budget-name { color:#f8fafc; font-size:1.05rem; line-height:1.3; font-weight:700; }
    .sd-budget-cal { margin:.5rem 0; color:#fff; font-size:1.2rem; font-weight:800; }
    .sd-budget-macros { color:#b0bdcf; font-size:.83rem; line-height:1.7; }
    .sd-insight-title { margin:0 0 .75rem; color:#fff; font-size:1.4rem; line-height:1.3; font-weight:750; }
    .sd-copy { color:#d5deeb; font-size:.92rem; line-height:1.7; }
    .sd-pillars { display:grid; gap:.7rem; margin:1rem 0; }
    .sd-pillar { padding-left:.75rem; border-left:2px solid #ff4b4b; }
    .sd-pillar:nth-child(2) { border-color:#38bdf8; }
    .sd-pillar:nth-child(3) { border-color:#34d399; }
    .sd-pillar-name { display:block; color:#f8fafc; font-size:.9rem; font-weight:700; }
    .sd-pillar-copy { display:block; margin-top:.15rem; color:#b0bdcf; font-size:.85rem; line-height:1.6; }
    .sd-coaching { margin-top:1rem; padding:.85rem 1rem; border:1px solid #262c3a;
        border-left:4px solid #fbbf24; border-radius:10px; background:#161b26; }
    .sd-coaching-title { margin-bottom:.4rem; color:#fbbf24; font-size:.85rem;
        font-weight:750; letter-spacing:.08em; text-transform:uppercase; }
    .sd-coaching ul { margin:0; padding-left:1rem; color:#d5deeb; font-size:.88rem; line-height:1.7; }
    .sd-stats { display:grid; grid-template-columns:repeat(3,1fr); margin:1rem 0;
        border-top:1px solid #262c3a; border-bottom:1px solid #262c3a; }
    .sd-stat { padding:.65rem .5rem; }
    .sd-stat + .sd-stat { border-left:1px solid #262c3a; }
    .sd-stat-label { display:block; color:#b0bdcf; font-size:.8rem; }
    .sd-stat-value { display:block; margin-top:.25rem; color:#f8fafc;
        font-size:1.1rem; font-weight:800; font-variant-numeric:tabular-nums; }
    .sd-chart { padding:1rem; border:1px solid #343b4e; border-radius:12px; background:#161b26; }
    .sd-chart-graph { display:grid; grid-template-columns:1.5rem 3rem minmax(0,1fr);
        align-items:stretch; gap:.45rem; }
    .sd-chart-y-title { display:flex; align-items:center; justify-content:center;
        color:#e2e8f0; font-size:.88rem; font-weight:650;
        writing-mode:vertical-rl; transform:rotate(180deg); }
    .sd-chart-y-axis { display:flex; flex-direction:column; justify-content:space-between;
        height:300px; padding-right:.3rem; color:#c0ccdc; text-align:right;
        font:.82rem ui-monospace,SFMono-Regular,Consolas,monospace; }
    .sd-chart-plot { position:relative; height:300px; margin:0 0 .45rem;
        border-bottom:1px solid #384052;
        background:repeating-linear-gradient(to bottom,transparent 0,transparent calc(33.333% - 1px),
        #343b4e calc(33.333% - 1px),#343b4e 33.333%); }
    .sd-chart-segment { position:absolute; height:4px; transform-origin:left center;
        border-radius:999px; }
    .sd-chart-point { position:absolute; z-index:1; width:12px; height:12px;
        transform:translate(-50%,-50%); border:2px solid #161b26; border-radius:50%;
        cursor:crosshair; transition:transform .12s ease, box-shadow .12s ease; }
    .sd-chart-point:hover,.sd-chart-point:focus { z-index:2; transform:translate(-50%,-50%) scale(1.45);
        outline:2px solid #fff; outline-offset:2px; }
    .sd-chart-x-axis { display:flex; justify-content:space-between; color:#c0ccdc;
        font:.82rem ui-monospace,SFMono-Regular,Consolas,monospace; }
    .sd-chart-note { display:flex; flex-wrap:wrap; justify-content:space-between;
        gap:.5rem; margin-top:.65rem; color:#b0bdcf; font-size:.82rem; }
    .sd-chart-explanation { margin-top:.85rem; padding:.85rem;
        border-top:1px solid #262c3a; color:#d5deeb; font-size:.9rem; line-height:1.65; }
    .sd-breakdown { margin:.85rem 0; padding:1rem; border:1px solid #262c3a;
        border-radius:10px; background:#161b26; }
    .sd-breakdown-head { display:flex; justify-content:space-between; align-items:center;
        flex-wrap:wrap; gap:.5rem; margin-bottom:.7rem; }
    .sd-legend { display:flex; flex-wrap:wrap; gap:.7rem; color:#d5deeb; font-size:.8rem; }
    .sd-legend-item { display:inline-flex; align-items:center; gap:.3rem; }
    .sd-legend-dot { display:inline-block; width:8px; height:8px; border-radius:50%; }
    .sd-ledger { border-top:1px solid #262c3a; }
    .sd-ledger-row { display:flex; align-items:flex-start; justify-content:space-between;
        flex-wrap:wrap; gap:.45rem 1rem; padding:.75rem 0; border-bottom:1px solid #262c3a; }
    .sd-ledger-left { min-width:0; flex:1; }
    .sd-ledger-name { color:#f8fafc; font-size:.9rem; font-weight:700; }
    .sd-ledger-desc { display:block; margin-top:.2rem; color:#b0bdcf; font-size:.82rem; line-height:1.6; }
    .sd-ledger-value { color:#fff; font-size:.9rem; font-weight:800; white-space:nowrap; }
    .sd-macro-conversions { display:flex; flex-wrap:wrap; gap:.4rem; padding:.6rem 0; }
    .sd-conversion { padding:.28rem .5rem; border-radius:6px; background:#1e222d;
        font:.8rem ui-monospace,SFMono-Regular,Consolas,monospace; }
    @media(max-width:760px) {
        .sd-profile-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        .sd-macro-grid { grid-template-columns:1fr; }
        .sd-budget-strip { grid-template-columns:repeat(2,minmax(0,1fr)); }
    }
    @media(max-width:430px) {
        [data-testid="stSidebar"] { width:min(80vw,232px) !important; min-width:min(80vw,232px) !important; }
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
        <section class="sd-section sd-profile-card">
          <div class="sd-section-head">
            <div>
              <h2 class="sd-heading">Your nutrition profile</h2>
              <div class="sd-muted">Personalized from the information you shared</div>
            </div>
            <span class="sd-status">Complete</span>
          </div>
          <div class="sd-profile-grid">{details_markup}</div>
          <div class="sd-muted" style="margin-top:1.25rem">Energy estimate: {_escape(tdee['bmr_method'])}</div>
        </section>
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
              <h2 class="sd-heading">Daily Nutrition Targets</h2>
              <div class="sd-muted">Your daily calorie goal and proportional macronutrient distribution</div>
            </div>
            <span class="sd-kicker">4 · 4 · 9 Atwater energy split</span>
          </div>
          <div class="sd-calorie-card">
            <div class="sd-calorie-head">
              <div>
                <div class="sd-calorie-title">Daily calorie target</div>
                <span class="sd-calorie-value">{_format_number(targets['calories'])}</span>
                <span class="sd-calorie-subtitle">kcal per day · {_escape(badge)}</span>
              </div>
              <span class="sd-status">Daily goal</span>
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
            <span class="sd-kicker">Suggested meal-slot macro budget</span>
            <span class="sd-muted">A guide for planning meals in your Food Diary</span>
          </div>
          <div class="sd-budget-strip">
    """
    for slot, share in MEAL_SLOTS:
        content += f"""
            <div class="sd-budget">
              <div class="sd-budget-name">{slot} · {share:.0%}</div>
              <div class="sd-budget-cal">{_format_number(targets['calories'] * share)} kcal</div>
              <div class="sd-budget-macros">
                <span style="color:{COLORS['protein']}">P {round(targets['protein_g'] * share)}g</span> ·
                <span style="color:{COLORS['carbs']}">C {round(targets['carbs_g'] * share)}g</span> ·
                <span style="color:{COLORS['fat']}">F {round(targets['fat_g'] * share)}g</span>
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

    plot_width, plot_height = 760, 300

    def y_percent(value):
        return (high - value) / (high - low) * 100

    segments = []
    for week in range(24):
        x_percent = week / 24 * 100
        y_value = y_percent(values[week])
        next_y = y_percent(values[week + 1])
        delta_y = (next_y - y_value) / 100 * plot_height
        angle = degrees(atan2(delta_y, plot_width / 24))
        segments.append(
            f'<span class="sd-chart-segment" style="left:{x_percent:.3f}%;'
            f'top:{y_value:.3f}%;width:{100 / 24:.3f}%;'
            f'transform:rotate({angle:.3f}deg);background:{axis_color}"></span>'
        )
    points = "".join(
        f'<span class="sd-chart-point" tabindex="0" role="img" '
        f'aria-label="Week {week}: {value:.1f} {tooltip_unit}'
        f'{" estimated weight" if is_weight else " calorie target"}" '
        f'style="left:{week / 24 * 100:.3f}%;top:{y_percent(value):.3f}%;'
        f'background:{axis_color}" title="Week {week}: {value:.1f} {tooltip_unit}'
        f'{" estimated weight" if is_weight else " calorie target"}"></span>'
        for week, value in enumerate(values)
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
            aria-label="24-week {axis_title.lower()} estimate. Focus or hover over weekly points for exact values.">
            {''.join(segments)}
            {points}
          </div>
        </div>
        <div class="sd-chart-x-axis">
          <span>Week 0</span><span>Week 4</span><span>Week 8</span>
          <span>Week 12</span><span>Week 16</span><span>Week 20</span><span>Week 24</span>
        </div>
    """


def _projection_markup(profile, goal_delta, metric="Weight", calorie_target=0):
    weight = profile.get("weight_kg")
    if weight is None:
        return '<div class="sd-muted">Add a current weight in Settings to show a trend estimate.</div>'
    measurement_units = profile.get("measurement_units", "Metric")
    factor = 2.2046226218 if measurement_units == "Imperial" else 1
    unit = "lb" if measurement_units == "Imperial" else "kg"
    daily_deficit = max(-goal_delta, 0)
    week_1 = _projected_weight(weight, daily_deficit, 1) * factor
    week_12 = _projected_weight(weight, daily_deficit, 12) * factor
    week_24 = _projected_weight(weight, daily_deficit, 24) * factor
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
        stats = f"""
          <div class="sd-stat"><span class="sd-stat-label">1-week estimate</span>
            <span class="sd-stat-value">{week_1:.1f} {unit}</span></div>
          <div class="sd-stat"><span class="sd-stat-label">12-week estimate</span>
            <span class="sd-stat-value" style="color:#34d399">{week_12:.1f} {unit}</span></div>
          <div class="sd-stat"><span class="sd-stat-label">24-week estimate</span>
            <span class="sd-stat-value" style="color:#34d399">{week_24:.1f} {unit}</span></div>
        """
        weekly_change_label = f"Expected change next week: {weekly_change_text}"
    return f"""
        <div class="sd-stats">{stats}</div>
        <div class="sd-chart">
          {_trajectory_chart(
              weight, daily_deficit, measurement_units, metric, calorie_target
          )}
          <div class="sd-chart-note">
            <strong>{weekly_change_label}</strong>
            <span>Illustrative estimate at a {_format_number(daily_deficit)} kcal/day deficit.</span>
            <span>Values are not a forecast or medical advice.</span>
          </div>
          <div class="sd-chart-explanation">{explanation}</div>
        </div>
    """


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
        <h2 class="sd-insight-title">Plan Strategy &amp; Tailored Guidance</h2>
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
          <div class="sd-coaching-title">💡 Coaching &amp; estimate notes</div>
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
            <span class="sd-ledger-name"><span style="color:{color}">●</span> {_escape(title)}</span>
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
            f'<span class="sd-conversion" style="color:{color}">'
            f'{name[0]}: {kcal:,} ÷ {factor} = {targets[key]}g</span>'
        )
    macro_energy = sum(targets[key] * factor for _, key, _, factor in NUTRIENTS)
    return f"""
        <section class="sd-section">
          <div class="sd-section-head">
            <div>
              <h2 class="sd-heading">How Your Calories &amp; Macros Were Calculated</h2>
              <div class="sd-muted">Transparent estimate: TDEE = BMR + NEAT + EAT + TEF</div>
            </div>
            <span class="sd-kicker">Maintenance {_format_number(tdee['tdee_kcal'])} kcal
              → Target {_format_number(targets['calories'])} kcal</span>
          </div>
          <div class="sd-breakdown">
            <div class="sd-breakdown-head">
              <span class="sd-kicker">Daily energy expenditure composition</span>
              <span class="sd-legend">{legend}</span>
            </div>
            <div style="display:flex;height:16px;overflow:hidden;border:1px solid #262c3a;
              border-radius:999px;background:#0e1117">{segments}</div>
          </div>
          <div class="sd-ledger">
            {ledger_rows}
            <div class="sd-ledger-row">
              <div class="sd-ledger-left">
                <span class="sd-ledger-name"><span style="color:{COLORS['calories']}">●</span>
                  Goal adjustment &amp; macro energy</span>
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
          <div>
            <div class="sd-brand">
              <span class="sd-logo">S</span>
              <span class="sd-brand-name">Sustain</span>
              <span class="sd-status">● Onboarding complete</span>
            </div>
            <h1 class="sd-title">Your Personalized Nutrition Plan</h1>
            <div class="sd-subtitle">Welcome, {_escape(username)} ·
              {_escape(date.today().strftime('%A, %d %B %Y'))} · Ready for meal planning</div>
          </div>
        </header>
    """


def _dashboard_markup(profile, targets, tdee, goal_delta):
    return f"""
        <main class="sd">
          {_profile_summary(profile, tdee)}
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
    edit_column, diary_column, spacer_column = st.columns(
        [2.4, 3, 4], vertical_alignment="center", gap="small"
    )
    with spacer_column:
        st.empty()
    with edit_column:
        if st.button(
            "Edit onboarding inputs",
            key="dashboard_edit",
            use_container_width=True,
        ):
            st.session_state["navigation_target"] = "Settings"
            st.rerun()
    with diary_column:
        if st.button(
            "Continue to Food Diary →",
            key="dashboard_diary",
            type="primary",
            use_container_width=True,
        ):
            st.session_state["navigation_target"] = "Diary"
            st.rerun()

    st.html(_dashboard_markup(profile, targets, tdee, goal_delta))

    st.html(
        f'{DASHBOARD_CSS}<main class="sd"><section class="sd-section">'
        f'{_strategy_markup(profile, targets, tdee, goal_delta)}'
        "</section></main>"
    )
    st.html(
        f'{DASHBOARD_CSS}<main class="sd"><section class="sd-section">'
        '<h2 class="sd-insight-title">24-Week Expected Trajectory</h2>'
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
