#!/usr/bin/env python3
"""Generate an interactive accessibility report from WAVE JSON output."""

import json
import os
from pathlib import Path
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

OUTPUT_DIR = Path("./output")
REPORT_PATH = OUTPUT_DIR / "accessibility-report.html"

# ─── Colours ──────────────────────────────────────────────────────────────────

CAT_COLORS = {
    "error":    "#ef4444",
    "contrast": "#f97316",
    "alert":    "#eab308",
    "feature":  "#22c55e",
    "structure":"#3b82f6",
    "aria":     "#8b5cf6",
}
SR_COLORS = {
    "critical": "#dc2626",
    "high":     "#ea580c",
    "medium":   "#ca8a04",
    "low":      "#16a34a",
}
POUR_COLORS = {
    "perceivable":    "#3b82f6",
    "operable":       "#8b5cf6",
    "understandable": "#ec4899",
    "robust":         "#14b8a6",
}

POUR_PT = {
    "perceivable": "Perceptível",
    "operable": "Operável",
    "understandable": "Compreensível",
    "robust": "Robusto",
}
SR_PT = {
    "critical": "Crítico",
    "high": "Alto",
    "medium": "Médio",
    "low": "Baixo",
}
CAT_PT = {
    "error": "Erros",
    "contrast": "Contraste",
    "alert": "Alertas",
    "feature": "Funcionalidades",
    "structure": "Estrutura",
    "aria": "ARIA",
}


def aim_color(score):
    if score is None:
        return "#94a3b8"
    if score < 5:
        return "#ef4444"
    if score < 7:
        return "#f97316"
    if score < 8.5:
        return "#eab308"
    return "#22c55e"


def page_name(filename: str) -> str:
    name = filename.replace(".html", "").replace(".htm", "")
    parts = name.split("-", 1)
    name = parts[1] if len(parts) > 1 else name
    return name.replace("-", " ").replace("_", " ")


# ─── Data loading ─────────────────────────────────────────────────────────────

def load_flows() -> list[dict]:
    flows = []
    for d in sorted(OUTPUT_DIR.iterdir()):
        if not d.is_dir():
            continue
        report_path = d / "wave-report.json"
        if not report_path.exists():
            continue
        pages = json.loads(report_path.read_text())
        flows.append({"name": d.name, "pages": pages})
    return flows


def flow_label(name: str) -> str:
    import re
    return re.sub(r"([A-Z])", r" \1", name).strip()


# ─── DataFrames ───────────────────────────────────────────────────────────────

def build_summary_df(flows: list[dict]) -> pd.DataFrame:
    rows = []
    for flow in flows:
        for page in flow["pages"]:
            s = page["summary"]
            pb = s.get("pour_breakdown") or {}
            sr = s.get("sr_relevance_breakdown") or {}
            rows.append({
                "flow":             flow["name"],
                "flow_label":       flow_label(flow["name"]),
                "source_file":      page["source_file"],
                "page":             page_name(page["source_file"]),
                "aim_score":        s.get("aim_score"),
                "errors":           s.get("errors", 0),
                "contrast_errors":  s.get("contrast_errors", 0),
                "alerts":           s.get("alerts", 0),
                "features":         s.get("features", 0),
                "structure":        s.get("structure", 0),
                "aria":             s.get("aria", 0),
                "pour_perceivable":    pb.get("perceivable", 0),
                "pour_operable":       pb.get("operable", 0),
                "pour_understandable": pb.get("understandable", 0),
                "pour_robust":         pb.get("robust", 0),
                "sr_critical": sr.get("critical", 0),
                "sr_high":     sr.get("high", 0),
                "sr_medium":   sr.get("medium", 0),
                "sr_low":      sr.get("low", 0),
            })
    return pd.DataFrame(rows)


def build_issues_df(flows: list[dict]) -> pd.DataFrame:
    rows = []
    for flow in flows:
        for page in flow["pages"]:
            for cat in page.get("categories", []):
                for t in cat.get("types", []):
                    rows.append({
                        "flow":           flow["name"],
                        "flow_label":     flow_label(flow["name"]),
                        "page":           page_name(page["source_file"]),
                        "category":       cat["category"],
                        "category_label": CAT_PT.get(cat["category"], cat["category"]),
                        "type_id":        t["type_id"],
                        "type_label":     t["type_label"],
                        "count":          t.get("count", 0),
                        "wcag_criteria":  ", ".join(t["wcag_criteria"]) if t.get("wcag_criteria") else "",
                        "wcag_level":     t.get("wcag_level") or "",
                        "pour_dimensions": ", ".join(t["pour_dimensions"]) if t.get("pour_dimensions") else "",
                        "sr_relevance":   t.get("sr_relevance") or "",
                    })
    return pd.DataFrame(rows)


# ─── Chart builders ───────────────────────────────────────────────────────────

CHART_CONFIG = {"displaylogo": False, "responsive": True}
LAYOUT_BASE = dict(
    paper_bgcolor="white",
    plot_bgcolor="#f8fafc",
    font=dict(family="system-ui, sans-serif", size=12, color="#1e293b"),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def chart_aim_all(df: pd.DataFrame) -> str:
    labels = df["flow_label"] + " — " + df["page"]
    colors = df["aim_score"].apply(aim_color).tolist()

    fig = go.Figure(go.Bar(
        x=df["aim_score"],
        y=labels,
        orientation="h",
        marker_color=colors,
        text=df["aim_score"],
        textposition="outside",
        hovertemplate="%{y}<br>AIM: %{x}<extra></extra>",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title="Pontuação AIM por página (0–10, maior é melhor)",
        height=max(300, len(df) * 36),
        xaxis=dict(range=[0, 10.5], title="AIM Score"),
        yaxis=dict(autorange="reversed"),
        showlegend=False,
    )
    return fig.to_html(full_html=False, config=CHART_CONFIG, include_plotlyjs=False)


def chart_issues_stacked(df: pd.DataFrame, title: str) -> str:
    fig = go.Figure()
    for cat, label in [("errors", "Erros"), ("contrast_errors", "Contraste"), ("alerts", "Alertas")]:
        fig.add_trace(go.Bar(
            name=label,
            x=df["page"],
            y=df[cat],
            marker_color=CAT_COLORS[{"errors": "error", "contrast_errors": "contrast", "alerts": "alert"}[cat]],
            hovertemplate=f"{label}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(
        **LAYOUT_BASE, title=title, barmode="stack", height=320,
        xaxis=dict(tickangle=-25),
    )
    return fig.to_html(full_html=False, config=CHART_CONFIG, include_plotlyjs=False)


def chart_positive_stacked(df: pd.DataFrame, title: str) -> str:
    fig = go.Figure()
    for col, label, color in [
        ("features",  "Funcionalidades", CAT_COLORS["feature"]),
        ("structure", "Estrutura",        CAT_COLORS["structure"]),
        ("aria",      "ARIA",             CAT_COLORS["aria"]),
    ]:
        fig.add_trace(go.Bar(
            name=label, x=df["page"], y=df[col],
            marker_color=color,
            hovertemplate=f"{label}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(
        **LAYOUT_BASE, title=title, barmode="stack", height=320,
        xaxis=dict(tickangle=-25),
    )
    return fig.to_html(full_html=False, config=CHART_CONFIG, include_plotlyjs=False)


def chart_pour(df: pd.DataFrame, title: str) -> str:
    fig = go.Figure()
    for dim, label in POUR_PT.items():
        fig.add_trace(go.Bar(
            name=label, x=df["page"], y=df[f"pour_{dim}"],
            marker_color=POUR_COLORS[dim],
            hovertemplate=f"{label}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(
        **LAYOUT_BASE, title=title, barmode="stack", height=320,
        xaxis=dict(tickangle=-25),
    )
    return fig.to_html(full_html=False, config=CHART_CONFIG, include_plotlyjs=False)


def chart_sr(df: pd.DataFrame, title: str) -> str:
    fig = go.Figure()
    for key, label in SR_PT.items():
        fig.add_trace(go.Bar(
            name=label, x=df["page"], y=df[f"sr_{key}"],
            marker_color=SR_COLORS[key],
            hovertemplate=f"{label}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(
        **LAYOUT_BASE, title=title, barmode="stack", height=320,
        xaxis=dict(tickangle=-25),
    )
    return fig.to_html(full_html=False, config=CHART_CONFIG, include_plotlyjs=False)


def chart_top_issues(issues_df: pd.DataFrame, title: str, n: int = 15) -> str:
    neg = issues_df[issues_df["category"].isin(["error", "contrast", "alert"])]
    top = (
        neg.groupby(["type_id", "type_label", "category"])["count"]
        .sum().reset_index()
        .sort_values("count", ascending=False)
        .head(n)
    )
    colors = top["category"].map(CAT_COLORS).fillna("#94a3b8").tolist()
    fig = go.Figure(go.Bar(
        x=top["count"],
        y=top["type_label"],
        orientation="h",
        marker_color=colors,
        text=top["count"],
        textposition="outside",
        hovertemplate="%{y}<br>%{x} ocorrências<extra></extra>",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=title,
        height=max(280, n * 28),
        xaxis=dict(title="Total de ocorrências"),
        yaxis=dict(autorange="reversed"),
        showlegend=False,
    )
    return fig.to_html(full_html=False, config=CHART_CONFIG, include_plotlyjs=False)


# ─── Table builders ───────────────────────────────────────────────────────────

SR_BADGE = {
    "critical": '<span class="badge badge-critical">Crítico</span>',
    "high":     '<span class="badge badge-high">Alto</span>',
    "medium":   '<span class="badge badge-medium">Médio</span>',
    "low":      '<span class="badge badge-low">Baixo</span>',
    "positive":       '<span class="badge badge-positive">Positivo</span>',
    "informational":  '<span class="badge badge-info">Informativo</span>',
    "":         "—",
}
CAT_BADGE = {
    "error":     '<span class="badge badge-error">Erro</span>',
    "contrast":  '<span class="badge badge-contrast">Contraste</span>',
    "alert":     '<span class="badge badge-alert">Alerta</span>',
    "feature":   '<span class="badge badge-feature">Funcionalidade</span>',
    "structure": '<span class="badge badge-structure">Estrutura</span>',
    "aria":      '<span class="badge badge-aria">ARIA</span>',
}


def summary_table(df: pd.DataFrame) -> str:
    display = df[["page", "aim_score", "errors", "contrast_errors", "alerts",
                  "features", "structure", "aria",
                  "sr_critical", "sr_high", "sr_medium", "sr_low"]].copy()

    def aim_cell(v):
        c = aim_color(v)
        return f'<span style="color:{c};font-weight:700">{v if v is not None else "—"}</span>'

    display["aim_score"] = display["aim_score"].apply(aim_cell)
    display.columns = ["Página", "AIM", "Erros", "Contraste", "Alertas",
                       "Funcionalidades", "Estrutura", "ARIA",
                       "LS Crítico", "LS Alto", "LS Médio", "LS Baixo"]
    return display.to_html(
        index=False, escape=False,
        classes="data-table", border=0,
    )


def top_issues_table(issues_df: pd.DataFrame, n: int = 20) -> str:
    neg = issues_df[issues_df["category"].isin(["error", "contrast", "alert"])]
    agg = (
        neg.groupby(["type_id", "type_label", "category", "wcag_criteria",
                     "wcag_level", "pour_dimensions", "sr_relevance"])
        .agg(total_count=("count", "sum"), page_count=("page", "nunique"))
        .reset_index()
        .sort_values("total_count", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
    agg.index += 1

    display = agg[["category", "type_label", "type_id", "total_count", "page_count",
                   "wcag_criteria", "wcag_level", "pour_dimensions", "sr_relevance"]].copy()
    display["category"]     = display["category"].map(lambda x: CAT_BADGE.get(x, x))
    display["sr_relevance"] = display["sr_relevance"].map(lambda x: SR_BADGE.get(x, x or "—"))
    display["type_label"]   = display.apply(
        lambda r: f'<strong>{r["type_label"]}</strong><br><small class="muted">{r["type_id"]}</small>', axis=1
    )
    display = display.drop(columns=["type_id"])
    display.columns = ["Tipo", "Problema", "Ocorrências", "Páginas",
                       "WCAG", "Nível", "POUR", "Impacto LS"]
    return display.to_html(
        index=True, escape=False,
        classes="data-table", border=0,
    )


def sr_page_cards(flow: dict) -> str:
    cards = []
    for page in flow["pages"]:
        name = page_name(page["source_file"])
        s = page["summary"]
        sr = s.get("sr_relevance_breakdown") or {}
        score = s.get("aim_score")
        color = aim_color(score)

        critical_types = []
        high_types = []
        for cat in page.get("categories", []):
            for t in cat.get("types", []):
                entry = {
                    "category":   CAT_BADGE.get(cat["category"], cat["category"]),
                    "type_label": t["type_label"],
                    "count":      t.get("count", 0),
                    "sr":         SR_BADGE.get(t.get("sr_relevance") or "", "—"),
                    "wcag":       ", ".join(t["wcag_criteria"]) if t.get("wcag_criteria") else "—",
                    "pour":       ", ".join(t["pour_dimensions"]) if t.get("pour_dimensions") else "—",
                }
                if t.get("sr_relevance") == "critical":
                    critical_types.append(entry)
                elif t.get("sr_relevance") == "high":
                    high_types.append(entry)

        issue_rows = ""
        for t in critical_types + high_types:
            issue_rows += f"""
            <tr>
              <td>{t['category']}</td>
              <td>{t['type_label']}</td>
              <td class="num">{t['count']}</td>
              <td>{t['sr']}</td>
              <td>{t['wcag']}</td>
              <td>{t['pour']}</td>
            </tr>"""

        table_html = f"""
        <div class="table-wrap" style="margin-top:0.75rem">
          <table class="data-table compact">
            <thead><tr><th>Tipo</th><th>Problema</th><th>Qtd</th>
              <th>Impacto LS</th><th>WCAG</th><th>POUR</th></tr></thead>
            <tbody>{issue_rows}</tbody>
          </table>
        </div>""" if issue_rows else '<p class="muted" style="margin-top:0.75rem">Nenhum problema crítico ou alto para leitores de tela.</p>'

        cards.append(f"""
<div class="page-card">
  <div class="page-card-header">
    <div>
      <h4>{name}</h4>
      <small class="muted">{page['source_file']}</small>
    </div>
    <div class="aim-badge" style="background:{color}22;border:2px solid {color}">
      <span style="color:{color};font-weight:700;font-size:1.5rem">{score if score is not None else '—'}</span>
      <span class="muted" style="font-size:0.75rem">/ 10 AIM</span>
    </div>
  </div>
  <div class="sr-summary-row">
    <span class="sr-chip sr-critical">🔴 {sr.get('critical',0)} críticos</span>
    <span class="sr-chip sr-high">🟠 {sr.get('high',0)} altos</span>
    <span class="sr-chip sr-medium">🟡 {sr.get('medium',0)} médios</span>
    <span class="sr-chip sr-low">🟢 {sr.get('low',0)} baixos</span>
    <span class="sr-chip" style="background:#f0f9ff;color:#0369a1">Erros: {s.get('errors',0)}</span>
    <span class="sr-chip" style="background:#fff7ed;color:#c2410c">Contraste: {s.get('contrast_errors',0)}</span>
    <span class="sr-chip" style="background:#fefce8;color:#a16207">Alertas: {s.get('alerts',0)}</span>
  </div>
  {table_html}
</div>""")
    return "\n".join(cards)


# ─── HTML assembly ────────────────────────────────────────────────────────────

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.5; }

.app-header { background: #1e293b; color: #f8fafc; padding: 1.25rem 2rem; }
.app-header h1 { font-size: 1.5rem; font-weight: 700; }
.app-header p { color: #94a3b8; font-size: 0.875rem; margin-top: 0.25rem; }

.nav-bar { background: #fff; border-bottom: 1px solid #e2e8f0; padding: 0.75rem 2rem;
  display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;
  position: sticky; top: 0; z-index: 10; }
.nav-btn { padding: 0.375rem 0.875rem; border-radius: 0.375rem; border: 1px solid #e2e8f0;
  background: transparent; cursor: pointer; font-size: 0.875rem; color: #475569;
  transition: all 0.15s; white-space: nowrap; }
.nav-btn:hover, .nav-btn.active { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.nav-divider { width: 1px; height: 24px; background: #e2e8f0; margin: 0 0.25rem; }

.main { max-width: 1400px; margin: 0 auto; padding: 2rem; }
.section { display: none; }
.section.active { display: block; }
.section > h2 { font-size: 1.5rem; font-weight: 700; margin-bottom: 1rem; color: #0f172a;
  border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }
.section h3 { font-size: 1.125rem; font-weight: 600; margin: 1.5rem 0 0.75rem; color: #1e293b; }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 1rem; margin-bottom: 2rem; }
.kpi-card { background: #fff; border-radius: 0.75rem; padding: 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.kpi-icon { font-size: 1.5rem; margin-bottom: 0.5rem; }
.kpi-value { font-size: 2rem; font-weight: 800; line-height: 1; }
.kpi-label { font-size: 0.8rem; color: #64748b; margin-top: 0.25rem; }

.chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
  gap: 1rem; margin-bottom: 1.5rem; }
.chart-card { background: #fff; border-radius: 0.75rem; padding: 1rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.chart-full { grid-column: 1 / -1; }

.table-wrap { overflow-x: auto; border-radius: 0.75rem; border: 1px solid #e2e8f0; margin-bottom: 1.5rem; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; background: #fff; }
.data-table th { background: #f1f5f9; padding: 0.625rem 0.875rem; text-align: left;
  font-weight: 600; color: #475569; font-size: 0.8rem; white-space: nowrap;
  border-bottom: 1px solid #e2e8f0; }
.data-table td { padding: 0.5rem 0.875rem; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: #f8fafc; }
.data-table.compact td { padding: 0.35rem 0.75rem; }
.num { text-align: right; font-variant-numeric: tabular-nums; }

.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 9999px;
  font-size: 0.75rem; font-weight: 600; white-space: nowrap; }
.badge-critical  { background: #fee2e2; color: #991b1b; }
.badge-high      { background: #ffedd5; color: #9a3412; }
.badge-medium    { background: #fef9c3; color: #854d0e; }
.badge-low       { background: #dcfce7; color: #166534; }
.badge-positive  { background: #f0fdf4; color: #166534; }
.badge-info      { background: #eff6ff; color: #1d4ed8; }
.badge-error     { background: #fef2f2; color: #dc2626; border: 1px solid #fca5a5; }
.badge-contrast  { background: #fff7ed; color: #ea580c; border: 1px solid #fdba74; }
.badge-alert     { background: #fefce8; color: #ca8a04; border: 1px solid #fde047; }
.badge-feature   { background: #f0fdf4; color: #16a34a; border: 1px solid #86efac; }
.badge-structure { background: #eff6ff; color: #2563eb; border: 1px solid #93c5fd; }
.badge-aria      { background: #faf5ff; color: #7c3aed; border: 1px solid #c4b5fd; }

.page-cards { display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem; }
.page-card { background: #fff; border-radius: 0.75rem; padding: 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #e2e8f0; }
.page-card-header { display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 0.75rem; }
.page-card h4 { font-size: 1.05rem; font-weight: 700; text-transform: capitalize; }
.aim-badge { display: flex; flex-direction: column; align-items: center;
  padding: 0.5rem 0.875rem; border-radius: 0.5rem; min-width: 80px; text-align: center; }
.sr-summary-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
.sr-chip { padding: 0.25rem 0.625rem; border-radius: 0.375rem; font-size: 0.8rem; font-weight: 600; }
.sr-critical { background: #fee2e2; color: #991b1b; }
.sr-high     { background: #ffedd5; color: #9a3412; }
.sr-medium   { background: #fef9c3; color: #854d0e; }
.sr-low      { background: #dcfce7; color: #166534; }
.muted { color: #94a3b8; }

@media (max-width: 640px) {
  .chart-grid { grid-template-columns: 1fr; }
  .main { padding: 1rem; }
  .kpi-grid { grid-template-columns: 1fr 1fr; }
}
"""

NAV_JS = """
function showSection(id, btn) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
  window.scrollTo(0, 0);
}
"""


def build_html(flows: list[dict]) -> str:
    summary_df = build_summary_df(flows)
    issues_df  = build_issues_df(flows)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total_pages    = len(summary_df)
    total_errors   = int(summary_df[["errors","contrast_errors","alerts"]].sum().sum())
    total_critical = int(summary_df["sr_critical"].sum())
    avg_aim        = round(summary_df["aim_score"].mean(), 1)

    kpis = [
        ("🗂️", str(len(flows)),       "Fluxos analisados",                "#3b82f6"),
        ("📄", str(total_pages),      "Páginas analisadas",               "#8b5cf6"),
        ("⚠️", str(total_errors),     "Total de problemas",               "#f97316"),
        ("🔴", str(total_critical),   "Problemas críticos (leitor de tela)", "#ef4444"),
        ("📊", f"{avg_aim}/10",        "Pontuação AIM média",              "#22c55e"),
    ]
    kpi_html = "".join(f"""
    <div class="kpi-card" style="border-left:4px solid {c}">
      <div class="kpi-icon">{icon}</div>
      <div class="kpi-value" style="color:{c}">{val}</div>
      <div class="kpi-label">{label}</div>
    </div>""" for icon, val, label, c in kpis)

    # ── Overview charts ───────────────────────────────────────────────────────
    aim_chart   = chart_aim_all(summary_df)
    issues_chart_all = chart_issues_stacked(summary_df, "Problemas por tipo — todas as páginas")
    sr_chart_all     = chart_sr(summary_df, "Impacto no leitor de tela — todas as páginas")
    pour_chart_all   = chart_pour(summary_df, "Dimensões POUR — todas as páginas")

    # ── Per-flow sections ─────────────────────────────────────────────────────
    flow_sections_html = ""
    nav_flow_btns = ""

    for i, flow in enumerate(flows):
        fid    = f"flow{i}"
        label  = flow_label(flow["name"])
        fdf    = summary_df[summary_df["flow"] == flow["name"]].copy()
        fidf   = issues_df[issues_df["flow"] == flow["name"]].copy()

        nav_flow_btns += f'<button class="nav-btn" onclick="showSection(\'{fid}\', this)">{label}</button>\n'

        flow_sections_html += f"""
<div id="{fid}" class="section">
  <h2>{label}</h2>

  <h3>Resumo por página</h3>
  <div class="table-wrap">{summary_table(fdf)}</div>

  <div class="chart-grid">
    <div class="chart-card">{chart_issues_stacked(fdf, "Problemas")}</div>
    <div class="chart-card">{chart_positive_stacked(fdf, "Boas práticas")}</div>
    <div class="chart-card">{chart_pour(fdf, "Dimensões POUR")}</div>
    <div class="chart-card">{chart_sr(fdf, "Impacto no leitor de tela")}</div>
    <div class="chart-card chart-full">{chart_top_issues(fidf, "Principais problemas neste fluxo", n=12)}</div>
  </div>

  <h3>Perspectiva do leitor de tela — página a página</h3>
  <p style="color:#64748b;font-size:0.875rem;margin-bottom:1rem">
    Problemas com impacto crítico ou alto para usuários de leitores de tela.
  </p>
  <div class="page-cards">{sr_page_cards(flow)}</div>
</div>"""

    # ── Top issues section ────────────────────────────────────────────────────
    top_chart = chart_top_issues(issues_df, "Top 15 problemas por ocorrências — todos os fluxos", n=15)
    top_table = top_issues_table(issues_df, n=20)

    # ── Plotly JS (CDN) ───────────────────────────────────────────────────────
    plotly_js = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>'

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Relatório de Acessibilidade WAVE</title>
  {plotly_js}
  <style>{CSS}</style>
</head>
<body>

<header class="app-header">
  <h1>Relatório de Acessibilidade WAVE</h1>
  <p>Análise de acessibilidade web — perspectiva de usuários de leitores de tela</p>
</header>

<nav class="nav-bar">
  <button class="nav-btn active" onclick="showSection('overview', this)">Visão geral</button>
  <div class="nav-divider"></div>
  {nav_flow_btns}
  <div class="nav-divider"></div>
  <button class="nav-btn" onclick="showSection('issues', this)">Principais problemas</button>
</nav>

<main class="main">

  <div id="overview" class="section active">
    <h2>Visão geral</h2>
    <div class="kpi-grid">{kpi_html}</div>
    <div class="chart-grid">
      <div class="chart-card chart-full">{aim_chart}</div>
      <div class="chart-card">{issues_chart_all}</div>
      <div class="chart-card">{sr_chart_all}</div>
      <div class="chart-card chart-full">{pour_chart_all}</div>
    </div>
  </div>

  {flow_sections_html}

  <div id="issues" class="section">
    <h2>Principais problemas de acessibilidade</h2>
    <p style="color:#64748b;font-size:0.875rem;margin-bottom:1.5rem">
      Os problemas mais frequentes somando todas as páginas e fluxos analisados.
    </p>
    <div class="chart-card chart-full" style="margin-bottom:1.5rem">{top_chart}</div>
    <div class="table-wrap">{top_table}</div>
  </div>

</main>

<script>{NAV_JS}</script>
</body>
</html>"""


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    flows = load_flows()
    if not flows:
        print(f"Nenhum wave-report.json encontrado em {OUTPUT_DIR}")
        raise SystemExit(1)

    print(f"Carregando {len(flows)} fluxo(s)...")
    for f in flows:
        print(f"  • {f['name']}: {len(f['pages'])} página(s)")

    html = build_html(flows)
    REPORT_PATH.write_text(html, encoding="utf-8")
    print(f"\nRelatório gerado em: {REPORT_PATH}")
