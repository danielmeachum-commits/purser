"""Layout the 800x480 Inky image showing month-to-date spend + savings goals."""

from __future__ import annotations

import calendar
import io
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agent import queries
from api.eink.palette import (
    BLACK,
    BLUE,
    GREEN,
    ORANGE,
    RED,
    WHITE,
    YELLOW,
    quantize_to_inky,
)

W, H = 800, 480

_FONT_CANDIDATES: tuple[str, ...] = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/noto/NotoSans.ttf",
)


def _find_ttf() -> str | None:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return p
    # Last-ditch: scan a couple of common roots for *any* NotoSans/DejaVu.
    for root in ("/usr/share/fonts", "/nix/store"):
        r = Path(root)
        if not r.exists():
            continue
        for cand in r.rglob("NotoSans.ttf"):
            return str(cand)
        for cand in r.rglob("DejaVuSans.ttf"):
            return str(cand)
    return None


_TTF_PATH = _find_ttf()


def _font(size: int) -> ImageFont.ImageFont:
    if _TTF_PATH is None:
        return ImageFont.load_default()
    return ImageFont.truetype(_TTF_PATH, size=size)


def _fmt_money(value: Decimal, *, signed: bool = False) -> str:
    sign = ""
    n = value
    if value < 0:
        sign = "-"
        n = -value
    elif signed and value > 0:
        sign = "+"
    whole = int(n)
    return f"{sign}${whole:,}"


def _budget_color(ratio: float) -> tuple[int, int, int]:
    if ratio >= 1.0:
        return RED
    if ratio >= 0.9:
        return ORANGE
    if ratio >= 0.75:
        return YELLOW
    return GREEN


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    ratio: float,
    fill: tuple[int, int, int],
) -> None:
    """Draw a black-outlined bar filled `fill` to `ratio` of its width."""
    x0, y0, x1, y1 = box
    draw.rectangle(box, outline=BLACK, width=2, fill=WHITE)
    clamped = max(0.0, min(1.0, ratio))
    inner_w = max(0, int((x1 - x0 - 4) * clamped))
    if inner_w > 0:
        draw.rectangle(
            (x0 + 2, y0 + 2, x0 + 2 + inner_w, y1 - 2), fill=fill
        )


def _rollup_categories(cats: list[dict]) -> list[dict]:
    """Roll child categories' direct_net into their parents.

    Returns top-level (parent_id is None) expense categories only, with a
    `spent` field (positive Decimal, the magnitude of net outflow) and the
    parent's own monthly_budget.
    """
    by_id = {c["id"]: c for c in cats}
    rollup_net: dict[int, Decimal] = {}
    for c in cats:
        if c["type"] != "expense":
            continue
        # Walk up to the top-level parent.
        node = c
        while node["parent_id"] is not None and node["parent_id"] in by_id:
            node = by_id[node["parent_id"]]
        rollup_net[node["id"]] = rollup_net.get(node["id"], Decimal("0")) + Decimal(
            c["direct_net"]
        )

    rows: list[dict] = []
    for c in cats:
        if c["type"] != "expense" or c["parent_id"] is not None:
            continue
        net = rollup_net.get(c["id"], Decimal("0"))
        # Expense net is negative; spent is its magnitude.
        spent = -net if net < 0 else Decimal("0")
        rows.append(
            {
                "id": c["id"],
                "name": c["name"],
                "spent": spent,
                "monthly_budget": (
                    Decimal(c["monthly_budget"]) if c["monthly_budget"] else None
                ),
            }
        )
    return rows


def _pick_category_rows(rollup: list[dict], limit: int = 6) -> list[dict]:
    """Prefer budgeted rows, then biggest spenders, capped at `limit`."""
    budgeted = [r for r in rollup if r["monthly_budget"]]
    budgeted.sort(key=lambda r: r["spent"], reverse=True)
    if len(budgeted) >= limit:
        return budgeted[:limit]
    remaining = [r for r in rollup if not r["monthly_budget"] and r["spent"] > 0]
    remaining.sort(key=lambda r: r["spent"], reverse=True)
    return (budgeted + remaining)[:limit]


def _gather_data() -> dict:
    summary = queries.summarize_transactions(date_range="mtd", group_by=None)
    breakdown = queries.category_breakdown(date_range="mtd")
    goals = queries.list_savings_goals()
    return {"summary": summary, "breakdown": breakdown, "goals": goals}


def render_eink_image() -> Image.Image:
    """Build the 800x480 PIL image (quantized to Inky's 7-color palette)."""
    data = _gather_data()
    summary = data["summary"]
    breakdown = data["breakdown"]
    goals = data["goals"]

    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    # --- Header --------------------------------------------------------
    f_label = _font(18)
    f_huge = _font(56)
    f_small = _font(16)
    f_row = _font(22)
    f_section = _font(20)

    net = Decimal(summary.get("net", "0"))
    net_color = GREEN if net >= 0 else RED

    d.text((20, 14), "MONTH-TO-DATE NET", font=f_label, fill=BLACK)
    d.text((20, 36), _fmt_money(net, signed=True), font=f_huge, fill=net_color)

    today = datetime.now()
    month_label = today.strftime("%B %Y")
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    subtitle = f"{month_label}  ·  day {today.day}/{days_in_month}"
    d.text((W - 20 - int(d.textlength(subtitle, font=f_small)), 18), subtitle,
           font=f_small, fill=BLACK)

    inflow = Decimal(summary.get("inflow", "0"))
    outflow = Decimal(summary.get("outflow", "0"))  # already negative
    inout = f"in {_fmt_money(inflow)}   out {_fmt_money(-outflow)}"
    d.text((W - 20 - int(d.textlength(inout, font=f_small)), 42), inout,
           font=f_small, fill=BLACK)

    d.line((20, 100, W - 20, 100), fill=BLACK, width=2)

    # --- Categories ----------------------------------------------------
    d.text((20, 110), "BUDGETS", font=f_section, fill=BLACK)
    rows = _pick_category_rows(_rollup_categories(breakdown.get("categories", [])))
    row_y = 140
    row_h = 36
    name_x = 20
    bar_x0 = 200
    bar_x1 = 560
    value_x = 580
    for row in rows[:5]:
        spent = row["spent"]
        budget = row["monthly_budget"]
        ratio = float(spent / budget) if budget and budget > 0 else 0.0
        color = _budget_color(ratio) if budget else BLUE
        name = row["name"]
        # Truncate long names.
        max_name_w = bar_x0 - name_x - 10
        while d.textlength(name, font=f_row) > max_name_w and len(name) > 1:
            name = name[:-1]
        if name != row["name"]:
            name = name[:-1] + "…"
        d.text((name_x, row_y), name, font=f_row, fill=BLACK)
        _draw_progress_bar(d, (bar_x0, row_y + 6, bar_x1, row_y + 24), ratio, color)
        if budget:
            txt = f"{_fmt_money(spent)} / {_fmt_money(budget)}"
        else:
            txt = _fmt_money(spent)
        d.text((value_x, row_y), txt, font=f_row, fill=BLACK)
        row_y += row_h

    # --- Savings goals -------------------------------------------------
    section_y = 340
    d.line((20, section_y - 4, W - 20, section_y - 4), fill=BLACK, width=2)
    d.text((20, section_y), "SAVINGS GOALS", font=f_section, fill=BLACK)
    g_y = section_y + 30
    g_h = 36
    for g in goals[:3]:
        target = Decimal(g["target_amount"])
        allocated = Decimal(g["allocated_amount"])
        ratio = float(allocated / target) if target > 0 else 0.0
        name = g["name"]
        max_name_w = bar_x0 - name_x - 10
        while d.textlength(name, font=f_row) > max_name_w and len(name) > 1:
            name = name[:-1]
        if name != g["name"]:
            name = name[:-1] + "…"
        d.text((name_x, g_y), name, font=f_row, fill=BLACK)
        _draw_progress_bar(d, (bar_x0, g_y + 6, bar_x1, g_y + 24), ratio, BLUE)
        txt = f"{_fmt_money(allocated)} / {_fmt_money(target)}"
        d.text((value_x, g_y), txt, font=f_row, fill=BLACK)
        g_y += g_h

    if not goals:
        d.text((name_x, g_y), "(no goals yet)", font=f_row, fill=BLACK)

    # --- Footer --------------------------------------------------------
    updated = f"updated {today.strftime('%Y-%m-%d %H:%M')}"
    d.text(
        (W - 20 - int(d.textlength(updated, font=f_small)), H - 22),
        updated,
        font=f_small,
        fill=BLACK,
    )

    return quantize_to_inky(img)


def render_eink_png() -> bytes:
    """Return the rendered eink image as PNG bytes."""
    buf = io.BytesIO()
    render_eink_image().save(buf, format="PNG")
    return buf.getvalue()
