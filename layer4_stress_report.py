# ARIA v5 - Layer 4: Weekly Stress Report (PDF)
# Institutional-grade risk report generated automatically
# Runs every Sunday 3AM UTC via systemd timer

import psycopg2
import numpy as np
import json
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import warnings
warnings.filterwarnings('ignore')

HETZNER_DB = {
    'host': '65.108.217.183', 'port': 5432,
    'dbname': 'aria_db', 'user': 'postgres',
    'password': 'aria_secure_2026'
}

OUTPUT_PATH = f"/root/ARIA_Stress_Report_{datetime.now().strftime('%Y%m%d')}.pdf"

# ── COLORS ────────────────────────────────────────────────
DARK_BG    = colors.HexColor('#0a0a0a')
ARIA_GREEN = colors.HexColor('#00ff88')
ARIA_RED   = colors.HexColor('#ff4444')
ARIA_BLUE  = colors.HexColor('#4488ff')
ARIA_GOLD  = colors.HexColor('#ffaa00')
WHITE      = colors.white
GRAY       = colors.HexColor('#888888')
DARK_GRAY  = colors.HexColor('#1a1a1a')

def get_all_data():
    conn = psycopg2.connect(**HETZNER_DB)
    cur = conn.cursor()

    cur.execute("SELECT symbol, var_99, expected_shortfall, threshold, shape_param FROM evt_tail_risk ORDER BY var_99 DESC")
    evt = cur.fetchall()

    cur.execute("""
        SELECT DISTINCT ON (asset_a, asset_b)
            asset_a, asset_b, normal_correlation,
            crisis_correlation, tail_dependence_coeff
        FROM tail_dependence ORDER BY asset_a, asset_b, created_at DESC
    """)
    tail_dep = cur.fetchall()

    cur.execute("SELECT assets_affected, max_drawdown FROM black_swan_scenarios ORDER BY max_drawdown ASC LIMIT 5")
    scenarios = cur.fetchall()

    cur.execute("SELECT symbol, position_size, weight FROM risk_parity_sizes WHERE regime='SIDEWAYS' ORDER BY weight DESC")
    sizes = cur.fetchall()

    cur.execute("SELECT hedge_positions, protection_analysis, red_alerts, crisis_level FROM guardian_state ORDER BY created_at DESC LIMIT 1")
    guardian = cur.fetchone()

    cur.execute("SELECT alert_level, pair, live_correlation, tail_dep_threshold FROM correlation_alerts ORDER BY created_at DESC LIMIT 15")
    alerts = cur.fetchall()

    cur.close()
    conn.close()
    return evt, tail_dep, scenarios, sizes, guardian, alerts

def build_pdf(evt, tail_dep, scenarios, sizes, guardian, alerts):
    doc = SimpleDocTemplate(OUTPUT_PATH, pagesize=A4,
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []

    # ── TITLE ─────────────────────────────────────────────
    title_style = ParagraphStyle('title', parent=styles['Normal'],
                                fontSize=24, textColor=ARIA_GREEN,
                                alignment=TA_CENTER, spaceAfter=6)
    sub_style = ParagraphStyle('sub', parent=styles['Normal'],
                               fontSize=11, textColor=GRAY,
                               alignment=TA_CENTER, spaceAfter=4)
    body_style = ParagraphStyle('body', parent=styles['Normal'],
                                fontSize=9, textColor=WHITE, spaceAfter=4)
    section_style = ParagraphStyle('section', parent=styles['Normal'],
                                   fontSize=13, textColor=ARIA_GOLD,
                                   spaceBefore=12, spaceAfter=6)
    metric_style = ParagraphStyle('metric', parent=styles['Normal'],
                                  fontSize=9, textColor=GRAY)

    story.append(Paragraph("ARIA INSTITUTIONAL RISK REPORT", title_style))
    story.append(Paragraph("Advanced Retail Intelligence & Analytics — v5", sub_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M UTC')}", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=ARIA_GREEN))
    story.append(Spacer(1, 0.2*inch))

    # ── EXECUTIVE SUMMARY ─────────────────────────────────
    story.append(Paragraph("EXECUTIVE SUMMARY", section_style))
    red_count = sum(1 for a in alerts if a[0] == 'RED')
    crisis_level = guardian[3] if guardian else 'UNKNOWN'
    protection = guardian[1] if guardian else {}

    summary_data = [
        ['Metric', 'Value', 'Status'],
        ['Crisis Level', crisis_level, '🔴 CRITICAL' if crisis_level == 'CRITICAL' else '🟡 ELEVATED'],
        ['RED Alerts', str(red_count), f'{red_count}/15 pairs'],
        ['Portfolio Protection', f"{protection.get('protection_pct', 0):.1f}%", 'Guardian Active'],
        ['Worst GAN Scenario', f"{protection.get('worst_scenario_drawdown', 0):.2f}%", 'Stress Tested'],
        ['Total Hedge Cost', f"${protection.get('total_hedge_cost', 0):.2f}", 'Auto-sized'],
    ]
    t = Table(summary_data, colWidths=[2.2*inch, 1.8*inch, 2.5*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), ARIA_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('BACKGROUND', (0,1), (-1,-1), DARK_GRAY),
        ('TEXTCOLOR', (0,1), (-1,-1), WHITE),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, GRAY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [DARK_GRAY, colors.HexColor('#222222')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.15*inch))

    # ── EVT TAIL RISK ─────────────────────────────────────
    story.append(Paragraph("EXTREME VALUE THEORY — TAIL RISK (POT/GPD Method)", section_style))
    story.append(Paragraph(
        "Using Peaks-Over-Threshold with Generalized Pareto Distribution. "
        "VaR99 = worst expected loss on 1 in 100 trading days. "
        "Expected Shortfall = average loss beyond VaR99.",
        metric_style))
    story.append(Spacer(1, 0.05*inch))

    evt_data = [['Asset', 'Threshold', 'VaR 99%', 'Exp. Shortfall', 'Shape (ξ)', 'Risk Level']]
    for row in evt:
        symbol, var99, es, threshold, shape = row
        risk = 'EXTREME' if var99 > 9 else 'HIGH' if var99 > 6 else 'MODERATE'
        evt_data.append([symbol, f"{threshold:.2f}%", f"{var99:.2f}%",
                        f"{es:.2f}%", f"{shape:.4f}", risk])
    t = Table(evt_data, colWidths=[0.8*inch, 1.0*inch, 0.9*inch, 1.2*inch, 1.0*inch, 1.0*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), ARIA_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('BACKGROUND', (0,1), (-1,-1), DARK_GRAY),
        ('TEXTCOLOR', (0,1), (-1,-1), WHITE),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, GRAY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [DARK_GRAY, colors.HexColor('#222222')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.15*inch))

    # ── TAIL DEPENDENCE ───────────────────────────────────
    story.append(Paragraph("TAIL DEPENDENCE — CRISIS CORRELATIONS", section_style))
    story.append(Paragraph(
        "Tail dependence measures how assets co-move during extreme events. "
        "Crisis correlation shows actual correlation during worst 20% market days. "
        "Higher tail dependence = more dangerous to hold both assets simultaneously.",
        metric_style))
    story.append(Spacer(1, 0.05*inch))

    td_data = [['Pair', 'Normal Corr', 'Crisis Corr', 'Tail Dep Coeff', 'Diversification']]
    for row in tail_dep[:10]:
        a, b, norm, crisis, td = row
        div = 'POOR' if td > 0.4 else 'MODERATE' if td > 0.2 else 'GOOD'
        td_data.append([f"{a}/{b}", f"{norm:+.3f}", f"{crisis:+.3f}", f"{td:.3f}", div])
    t = Table(td_data, colWidths=[1.0*inch, 1.0*inch, 1.0*inch, 1.2*inch, 1.2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), ARIA_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('BACKGROUND', (0,1), (-1,-1), DARK_GRAY),
        ('TEXTCOLOR', (0,1), (-1,-1), WHITE),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, GRAY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [DARK_GRAY, colors.HexColor('#222222')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.15*inch))

    # ── GAN SCENARIOS ─────────────────────────────────────
    story.append(Paragraph("GAN STRESS SCENARIOS — TOP 5 WORST CASES", section_style))
    story.append(Paragraph(
        "10,000 synthetic crisis scenarios generated by Generative Adversarial Network "
        "trained on historical crisis periods. No Tanh constraint — true outlier generation enabled.",
        metric_style))
    story.append(Spacer(1, 0.05*inch))

    gan_data = [['Scenario', 'Max Drawdown', 'BTC', 'ETH', 'AAPL', 'NVDA', 'TSLA', 'GLD']]
    for i, (assets, max_dd) in enumerate(scenarios):
        if isinstance(assets, str):
            assets = json.loads(assets)
        gan_data.append([
            f"Scenario {i+1}",
            f"{max_dd:.2f}%",
            f"{assets.get('BTC', 0):.1f}%",
            f"{assets.get('ETH', 0):.1f}%",
            f"{assets.get('AAPL', 0):.1f}%",
            f"{assets.get('NVDA', 0):.1f}%",
            f"{assets.get('TSLA', 0):.1f}%",
            f"{assets.get('GLD', 0):.1f}%",
        ])
    t = Table(gan_data, colWidths=[0.9*inch, 1.0*inch, 0.7*inch, 0.7*inch, 0.7*inch, 0.7*inch, 0.7*inch, 0.7*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), ARIA_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('BACKGROUND', (0,1), (-1,-1), DARK_GRAY),
        ('TEXTCOLOR', (0,1), (-1,-1), ARIA_RED),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, GRAY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [DARK_GRAY, colors.HexColor('#222222')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.15*inch))

    # ── RISK PARITY SIZES ─────────────────────────────────
    story.append(Paragraph("LAYER 1 — RISK PARITY POSITION SIZING", section_style))
    story.append(Paragraph(
        "Position sizes calculated using inverse Expected Shortfall (Risk Parity). "
        "Assets with higher tail risk receive proportionally smaller allocations. "
        "Formula: Position ∝ 1/ES × Regime_Multiplier × Kelly_Fraction",
        metric_style))
    story.append(Spacer(1, 0.05*inch))

    rp_data = [['Asset', 'Position Size', 'Weight', 'Regime']]
    for row in sizes:
        rp_data.append([row[0], f"${row[1]:.2f}", f"{row[2]:.3f}", 'SIDEWAYS'])
    t = Table(rp_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), ARIA_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('BACKGROUND', (0,1), (-1,-1), DARK_GRAY),
        ('TEXTCOLOR', (0,1), (-1,-1), WHITE),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, GRAY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [DARK_GRAY, colors.HexColor('#222222')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.15*inch))

    # ── GUARDIAN ANALYSIS ─────────────────────────────────
    story.append(Paragraph("LAYER 3 — GUARDIAN AGENT PROTECTION ANALYSIS", section_style))
    if guardian and protection:
        guard_data = [
            ['Metric', 'Value'],
            ['Crisis Level', guardian[3]],
            ['RED Alerts', str(guardian[2])],
            ['Worst Scenario', f"{protection.get('worst_scenario_drawdown', 0):.2f}%"],
            ['Loss Without Hedge', f"${protection.get('portfolio_loss_no_hedge', 0):.2f}"],
            ['Guardian Hedge Profit', f"${protection.get('hedge_profit', 0):.2f}"],
            ['Net Loss With Guardian', f"${protection.get('net_loss_with_hedge', 0):.2f}"],
            ['Protection Coverage', f"{protection.get('protection_pct', 0):.1f}%"],
            ['Total Hedge Cost', f"${protection.get('total_hedge_cost', 0):.2f}"],
        ]
        t = Table(guard_data, colWidths=[3*inch, 3*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), ARIA_BLUE),
            ('TEXTCOLOR', (0,0), (-1,0), WHITE),
            ('BACKGROUND', (0,1), (-1,-1), DARK_GRAY),
            ('TEXTCOLOR', (0,1), (-1,-1), WHITE),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.5, GRAY),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [DARK_GRAY, colors.HexColor('#222222')]),
        ]))
        story.append(t)
    story.append(Spacer(1, 0.15*inch))

    # ── FOOTER ────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=ARIA_GREEN))
    footer_style = ParagraphStyle('footer', parent=styles['Normal'],
                                  fontSize=7, textColor=GRAY, alignment=TA_CENTER)
    story.append(Paragraph(
        "ARIA v5 Institutional Risk Framework | "
        "Problem C: Black Swan Defense System | "
        "GAN + EVT (POT/GPD) + Tail Dependence + Guardian Agent | "
        "DMU MSc Data Analytics 2026",
        footer_style))

    doc.build(story)
    print(f"PDF saved: {OUTPUT_PATH}")

if __name__ == "__main__":
    print("="*60)
    print("ARIA v5 - LAYER 4: STRESS REPORT PDF")
    print("="*60)
    evt, tail_dep, scenarios, sizes, guardian, alerts = get_all_data()
    build_pdf(evt, tail_dep, scenarios, sizes, guardian, alerts)
    print("="*60)
    print("LAYER 4 COMPLETE")
    print("="*60)
