"""
Build the ICU Step-Down Readiness architecture diagram (draw.io) for the deck.

Uses the Databricks-branded helpers from the `databricks-architecture-diagram`
skill (brand tokens: fe-databricks-branding / FEIP-5505), so no colours are
hardcoded here.

    python3 scripts/diagrams/build_architecture.py
    python3 ~/.claude/skills/databricks-architecture-diagram/references/render_diagram.py \
        deck/architecture.drawio

Outputs deck/architecture.drawio (editable in app.diagrams.net / draw.io).
"""

from __future__ import annotations

import sys
from pathlib import Path

HELPERS = Path.home() / ".claude/skills/databricks-architecture-diagram/references"
sys.path.insert(0, str(HELPERS))

from drawio_helpers import (  # noqa: E402
    ARROW_C, BRONZE_F, BRONZE_S, CARD_FILL, CARD_STROKE, GOLD_F, GOLD_S,
    PANEL_FILL, PANEL_HDR, PANEL_STROKE, RED, SILVER_F, SILVER_S, TEAL,
    TEAL_LIGHT, TEXT_DARK, TEXT_MED, DrawioDoc, arrow, badge, card, hdr,
    legend, platform_shell, rect, side_panel, text_cell, uc_bar,
)

OUT = Path(__file__).resolve().parents[2] / "deck" / "architecture.drawio"

# ── Canvas layout ────────────────────────────────────────────────────────────
SRC_X, SRC_W = 20, 210
PLAT_X, PLAT_Y, PLAT_W, PLAT_H = 260, 40, 1000, 620
CON_X, CON_W = 1290, 230
PANEL_Y, PANEL_H = 120, 300
CON_H = 420  # taller so Genie aligns with gold and the App with Lakebase


def two_way(id_: str, x1: float, y1: float, x2: float, y2: float, label: str) -> str:
    """Orthogonal edge with arrowheads at both ends (helper arrow() is one-way)."""
    style = (
        f"edgeStyle=orthogonalEdgeStyle;html=1;strokeColor={TEAL};strokeWidth=1.5;"
        f"endArrow=block;endFill=1;startArrow=block;startFill=1;dashed=1;"
        f"fontFamily=Arial;fontSize=10;fontColor={TEAL};labelBackgroundColor=none;"
    )
    return (
        f'<mxCell id="{id_}" value="{label}" style="{style}" edge="1" parent="1">\n'
        f'  <mxGeometry relative="1" as="geometry">\n'
        f'    <mxPoint x="{x1}" y="{y1}" as="sourcePoint" />\n'
        f'    <mxPoint x="{x2}" y="{y2}" as="targetPoint" />\n'
        f'  </mxGeometry>\n'
        f'</mxCell>'
    )


def medallion(doc: DrawioDoc, y: int) -> dict[str, tuple[int, int, int, int]]:
    """Bronze → Silver → Gold, each with a detail card underneath."""
    w, h, gap = 270, 62, 45
    start = PLAT_X + (PLAT_W - (3 * w + 2 * gap)) // 2
    layers = [
        ("bronze", BRONZE_F, BRONZE_S, "Bronze · streaming tables",
         "Delta Share history + live feed (2 append flows)<br/>Live cohort's final 24h held back for replay"),
        ("silver", SILVER_F, SILVER_S, "Silver · typed &amp; cleaned",
         "<b>DOB dropped</b> · age whole years, capped 90<br/>Expectations FAIL the update on violation"),
        ("gold", GOLD_F, GOLD_S, "Gold · features &amp; scores",
         "53 features · outcome label · <b>masked IDs</b><br/>pii_audit · census_scores (ai_query)"),
    ]
    boxes = {}
    for i, (key, fill, stroke, title, detail) in enumerate(layers):
        x = start + i * (w + gap)
        doc.add(rect(f"med_{key}", x, y, w, h, fill=fill, stroke=stroke, sw=2, rounded=1,
                     label=f"<b style='font-size:15px;color:{stroke};'>{title}</b>"))
        doc.add(rect(f"med_{key}_d", x, y + h + 6, w, 46, fill=CARD_FILL, stroke=CARD_STROKE,
                     rounded=1, font_size=10, font_color=TEXT_MED, label=detail))
        boxes[key] = (x, y, w, h)
    for a, b, color in (("bronze", "silver", BRONZE_S), ("silver", "gold", SILVER_S)):
        ax, ay, aw, ah = boxes[a]
        bx = boxes[b][0]
        doc.add(arrow(f"med_a_{a}", x1=ax + aw + 2, y1=ay + ah / 2, x2=bx - 2, y2=ay + ah / 2,
                      color=color, sw=2, orthogonal=False))
    return boxes


def section(doc: DrawioDoc, key: str, x: int, y: int, w: int, title: str,
            cards: list[tuple[str, str]], header_fill: str) -> tuple[int, int, int, int]:
    """Section body + header bar + stacked component cards."""
    card_h, pad = 50, 10
    h = 30 + pad + len(cards) * (card_h + pad)
    doc.add(rect(f"sec_{key}", x, y, w, h, fill=CARD_FILL, stroke=CARD_STROKE, sw=1))
    doc.add(hdr(f"sec_{key}_h", x, y, w, 30, title, fill=header_fill, font_size=13))
    for i, (ctitle, cdesc) in enumerate(cards):
        doc.add(card(f"sec_{key}_c{i}", x + pad, y + 30 + pad + i * (card_h + pad),
                     w - 2 * pad, card_h, title=ctitle, desc=cdesc, fill=CARD_FILL,
                     title_size=12, desc_size=10))
    return (x, y, w, h)


def build() -> DrawioDoc:
    doc = DrawioDoc("ICU Step-Down Readiness — Architecture")

    doc.add(text_cell("title", PLAT_X, 2, PLAT_W, 30,
                      "ICU Step-Down Readiness — governed, streaming, AI-scored",
                      font_size=18, font_color=TEXT_DARK, bold=True))

    # 1 · Sources
    for c in side_panel("src", SRC_X, PANEL_Y, SRC_W, PANEL_H, "Data sources", "1", [
        ("", "MIMIC-III (Delta Share)", "61.5k de-identified ICU stays<br/>shared WITH HISTORY"),
        ("", "Live vitals replay", "Real final-24h events released<br/>hour by hour (landing feed)"),
        ("", "Pilot: EHR / ADT feed", "Clarity / HL7 / FHIR replaces<br/>the replay — bronze only"),
    ]):
        doc.add(c)

    # Platform shell + continuous pipeline sub-bar
    for c in platform_shell("plat", PLAT_X, PLAT_Y, PLAT_W, PLAT_H,
                            sub_label="Lakeflow Declarative Pipeline · CONTINUOUS · serverless"):
        doc.add(c)

    # 2 · Medallion
    med = medallion(doc, 120)

    # 7 · Ops & GenAI (left) · 3 · Mosaic AI (middle) · 4 · Lakebase (right, under gold)
    sy, sw_, gap = 330, 300, 35
    sx = PLAT_X + (PLAT_W - (3 * sw_ + 2 * gap)) // 2
    ops = section(doc, "ops", sx, sy, sw_, "Ops &amp; GenAI", [
        ("Foundation Model API", "Llama 3.3 70B clinical summary"),
        ("Drift job · daily", "PSI / KS vs training baseline"),
        ("Safety guardrail", "Life support (24h) → never Ready"),
    ], header_fill=PANEL_HDR)
    mosaic = section(doc, "ml", sx + sw_ + gap, sy, sw_, "Mosaic AI", [
        ("Training job · MLflow", "LightGBM, 53 features · AUC 0.89"),
        ("UC model · readiness_model v6", "Versioned, lineage to gold"),
        ("Serving · icu-readiness", "Scores + SHAP for app and pipeline"),
    ], header_fill=TEAL)
    lake = section(doc, "lb", sx + 2 * (sw_ + gap), sy, sw_, "Lakebase (Postgres)", [
        ("gold.*_serving", "IDs stored as P- pseudonyms"),
        ("Snapshot synced tables", "census · features · vitals · drift"),
        ("App read path", "0 raw identifiers in Postgres"),
    ], header_fill=TEAL)

    # 5 · Unity Catalog governance bar
    uc_y = PLAT_Y + PLAT_H - 72
    for c in uc_bar("uc", PLAT_X + 30, uc_y, PLAT_W - 60, 58,
                    subtitle="Column masks on IDs · care-unit row-level views · PII tags · lineage · "
                             "expectations + pii_audit"):
        doc.add(c)

    # 6 · Consumers
    for c in side_panel("con", CON_X, PANEL_Y, CON_W, CON_H, "Consumers", "6", [
        ("", "Genie space", "Plain-English Q&amp;A on live<br/>scores, care-unit scoped"),
        ("", "Databricks App", "React + FastAPI: census,<br/>patient detail, analytics"),
        ("", "Clinicians &amp; ops", "Charge nurse, intensivist,<br/>bed management"),
    ]):
        doc.add(c)

    # ── Arrows ───────────────────────────────────────────────────────────────
    bx, by, bw, bh = med["bronze"]
    gx, gy, gw, gh = med["gold"]
    gold_detail_bottom = gy + gh + 6 + 46
    con_item_h = (CON_H - 38) // 3
    genie_y = PANEL_Y + 38 + con_item_h // 2
    app_y = PANEL_Y + 38 + con_item_h + con_item_h // 2
    doc.add(arrow("a_src", x1=SRC_X + SRC_W, y1=by + bh / 2, x2=bx - 2, y2=by + bh / 2,
                  label="stream", color=ARROW_C, sw=2, orthogonal=False))
    mx, my, mw, mh = mosaic
    lx, ly, lw, lh = lake
    # gold ↔ Mosaic AI: train from gold, scores written back via ai_query
    doc.add(two_way("a_ml", gx + 30, gold_detail_bottom + 2, mx + mw - 40, my - 2, ""))
    doc.add(text_cell("a_ml_lbl", mx + mw - 30, gold_detail_bottom + 30, 170, 34,
                      "train ↓<br/>ai_query scores ↑", font_size=10, font_color=TEAL,
                      align="left"))
    # gold → Lakebase (straight down: Lakebase sits under gold)
    doc.add(arrow("a_sync", x1=lx + lw / 2, y1=gold_detail_bottom + 2, x2=lx + lw / 2, y2=ly - 2,
                  label="snapshot sync", color=ARROW_C, sw=1.5, orthogonal=False))
    # gold → Genie, Lakebase → App (short hops into the consumers panel)
    doc.add(arrow("a_genie", x1=gx + gw + 2, y1=genie_y, x2=CON_X - 2, y2=genie_y,
                  label="governed views", color=ARROW_C, sw=2, orthogonal=False))
    doc.add(arrow("a_app", x1=lx + lw + 2, y1=app_y, x2=CON_X - 2, y2=app_y,
                  label="app reads", color=ARROW_C, sw=2, orthogonal=False))

    # ── Badges on section edges ──────────────────────────────────────────────
    doc.add(badge("b2", bx - 14, by - 14, "2"))
    doc.add(badge("b3", mx - 13, my - 13, "3"))
    doc.add(badge("b4", lx - 13, ly - 13, "4"))
    ox, oy, _, _ = ops
    doc.add(badge("b7", ox - 13, oy - 13, "7"))
    doc.add(badge("b5", PLAT_X + 30 - 13, uc_y - 13, "5"))

    # Legend (outside all containers, left column under the sources panel)
    for c in legend("leg", SRC_X, PANEL_Y + PANEL_H + 30, SRC_W + 20, [
        ("1", "Sources", "Delta Share history + live replay feed"),
        ("2", "Continuous medallion", "Streaming bronze → silver → gold"),
        ("3", "Mosaic AI", "Train, register, serve; scores via ai_query"),
        ("4", "Lakebase", "Pseudonymised copies for the app"),
        ("5", "Unity Catalog", "Masks, row-level access, PII audit"),
        ("6", "Consumers", "App, Genie, care teams"),
        ("7", "Ops & GenAI", "Narrative, drift, safety guardrail"),
    ], flow_numbers="1 → 2 → 3 / 4 → 6", flow_labels="Feed → Pipeline → AI / Lakebase → Users"):
        doc.add(c)

    return doc


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    build().save(str(OUT))
    print(f"wrote {OUT}")
