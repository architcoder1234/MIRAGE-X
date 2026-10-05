"""
MIRAGE-X — Incident Report Export.

Generates a one-page PDF summary of an incident using ReportLab (pure
Python, no external service). Every number on the page comes straight from
the incident dict main.py already built for the dashboard — this module
does formatting only, no independent computation, so the report can never
disagree with the dashboard.
"""
import os
import tempfile
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from xml.sax.saxutils import escape as _xml_escape

SEVERITY_COLORS = {
    "CRITICAL": colors.HexColor("#ff5c5c"),
    "HIGH": colors.HexColor("#ff9f43"),
    "MEDIUM": colors.HexColor("#f5d76e"),
    "LOW": colors.HexColor("#4fd17e"),
    "INFO": colors.HexColor("#8a97a8"),
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name="MXTitle", fontSize=18, leading=22, spaceAfter=4,
                           textColor=colors.HexColor("#0d1117")))
    ss.add(ParagraphStyle(name="MXSub", fontSize=10, leading=14,
                           textColor=colors.HexColor("#5a6472")))
    ss.add(ParagraphStyle(name="MXHeading", fontSize=12, leading=16, spaceBefore=14, spaceAfter=6,
                           textColor=colors.HexColor("#0d1117")))
    ss.add(ParagraphStyle(name="MXBody", fontSize=9.5, leading=14, alignment=TA_LEFT,
                           textColor=colors.HexColor("#1a1f27")))
    return ss


def _esc(text):
    """Escape for ReportLab's mini-XML markup — '&' breaks Paragraph parsing otherwise."""
    return _xml_escape(str(text))


def _cell(text, style):
    """Wrap text in a Paragraph so it wraps inside a Table cell instead of overflowing the page."""
    return Paragraph(_esc(text), style)


def generate_incident_report(incident: dict, advisory: dict = None) -> str:
    """Builds the PDF into a temp file and returns its path."""
    ss = _styles()
    cell_style = ParagraphStyle(name="MXCell", fontSize=9, leading=12,
                                 textColor=colors.HexColor("#1a1f27"))
    label_style = ParagraphStyle(name="MXLabel", fontSize=9, leading=12,
                                  fontName="Helvetica-Bold", textColor=colors.HexColor("#5a6472"))
    fd, path = tempfile.mkstemp(suffix=f"_{incident['incident_id']}_report.pdf")
    os.close(fd)

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )
    story = []

    story.append(Paragraph(_esc(f"MIRAGE-X Incident Report — {incident['incident_id']}"), ss["MXTitle"]))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(_esc(f"Generated {generated} · Adaptive Cyber Defense Platform"), ss["MXSub"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#dfe3e8")))
    story.append(Spacer(1, 10))

    # --- Summary table ---
    alert = incident.get("soc_alert") or {}
    sev = alert.get("severity", "INFO")
    summary_rows = [
        [_cell("Risk Score", label_style),
         _cell(f"{incident['risk_score']}/100 ({incident['confidence']} memory confidence)", cell_style)],
        [_cell("SOC Severity", label_style),
         _cell(sev + ("  —  WOULD PAGE ANALYST" if alert.get("would_page") else "  —  no page, queued for review"), cell_style)],
        [_cell("Decoy Deployed", label_style),
         _cell(incident.get("decoy_deployed") or "None", cell_style)],
        [_cell("Behavior Sequence", label_style),
         _cell(" \u2192 ".join(incident.get("behavior_sequence", [])) or "—", cell_style)],
    ]
    top_match = incident.get("similarity_top_match")
    if top_match:
        summary_rows.append([
            _cell("Closest Historical Match", label_style),
            _cell(
                f"{top_match['incident_id']} (score {top_match['score']}, matched on "
                f"{', '.join(top_match['matched_features']) or 'none'})",
                cell_style,
            ),
        ])
    path_pred = incident.get("predicted_path") or {}
    if path_pred.get("predicted_next_label"):
        summary_rows.append([_cell("Predicted Next Target", label_style),
                              _cell(path_pred["predicted_next_label"], cell_style)])
    quality = incident.get("decoy_quality_metrics") or {}
    if quality:
        quality_text = (
            f"Dwell {quality.get('dwell_time_s', 0)}s; "
            f"{quality.get('interaction_count', 0)} interaction(s); "
            f"{quality.get('distinct_evidence_types', 0)} evidence type(s); "
            f"path {'stayed' if quality.get('stayed_on_predicted_path') else 'diverged or unknown'}."
        )
        summary_rows.append([_cell("Decoy Quality", label_style), _cell(quality_text, cell_style)])

    tbl = Table(summary_rows, colWidths=[42 * mm, 118 * mm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#eef0f3")),
        ("BACKGROUND", (1, 1), (1, 1), SEVERITY_COLORS.get(sev, colors.white)),
    ]))
    story.append(tbl)

    # --- Explainable summary ---
    story.append(Paragraph("Explainable AI Defender Summary", ss["MXHeading"]))
    story.append(Paragraph(_esc(incident.get("summary", "")).replace("-&gt;", "\u2192"), ss["MXBody"]))

    # --- AI Advisor (optional — sits on top of the rule-based engine above,
    # never replaces it; labeled clearly so the source of each number is
    # never ambiguous). Renders whether the advisor used a live LLM call or
    # its rule-based fallback, since both are useful on the page.
    if advisory:
        mode_label = "AI-Generated" if advisory.get("mode") == "llm" else "Rule-Based (no AI key configured or call unavailable)"
        story.append(Paragraph(_esc(f"Advisor Recommendation — {mode_label}"), ss["MXHeading"]))
        if advisory.get("plain_summary"):
            story.append(Paragraph(_esc(advisory["plain_summary"]), ss["MXBody"]))
        actions = advisory.get("recommended_actions") or []
        if actions:
            story.append(Spacer(1, 4))
            for a in actions:
                story.append(Paragraph(_esc(f"\u2022 {a}"), ss["MXBody"]))
        if advisory.get("analyst_note"):
            story.append(Spacer(1, 4))
            story.append(Paragraph(_esc(f"Analyst note: {advisory['analyst_note']}").replace("-&gt;", "\u2192"), ss["MXBody"]))

    # --- MITRE ATT&CK techniques ---
    techniques = incident.get("mitre_techniques") or []
    if techniques:
        story.append(Paragraph(_esc("MITRE ATT&CK Techniques Observed"), ss["MXHeading"]))
        header_style = ParagraphStyle(name="MXTHead", fontSize=8.5, leading=11,
                                       fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1f27"))
        row_style = ParagraphStyle(name="MXTRow", fontSize=8.5, leading=11,
                                    textColor=colors.HexColor("#1a1f27"))
        rows = [[_cell("Event", header_style), _cell("Technique", header_style), _cell("Tactic", header_style)]] + [
            [_cell(t["event_type"], row_style),
             _cell(f"{t['technique_id']} — {t['technique_name']}", row_style),
             _cell(t["tactic"], row_style)]
            for t in techniques
        ]
        mtbl = Table(rows, colWidths=[36 * mm, 84 * mm, 40 * mm])
        mtbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f4f7")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e3e6ea")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(mtbl)

    # --- Decoy evidence ---
    evidence = incident.get("decoy_evidence") or []
    if evidence:
        story.append(Paragraph("Decoy Evidence Log", ss["MXHeading"]))
        ehead = ParagraphStyle(name="MXEHead", fontSize=8, leading=10,
                                fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1f27"))
        erow = ParagraphStyle(name="MXERow", fontSize=8, leading=10,
                               textColor=colors.HexColor("#1a1f27"))
        rows = [[_cell("Decoy", ehead), _cell("Source IP", ehead), _cell("Observation", ehead)]] + [
            [_cell(e["decoy"], erow), _cell(e["src_ip"], erow), _cell(e["command"], erow)]
            for e in evidence[-15:]  # last 15, keep it to one page
        ]
        etbl = Table(rows, colWidths=[26 * mm, 26 * mm, 108 * mm])
        etbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f4f7")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e3e6ea")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(etbl)

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#dfe3e8")))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Generated automatically from simulated/lab evidence. Isolated demo environment — "
        "no real infrastructure, no real credentials.",
        ss["MXSub"],
    ))

    doc.build(story)
    return path
