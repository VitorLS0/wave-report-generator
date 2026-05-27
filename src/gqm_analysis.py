#!/usr/bin/env python3
"""GQM — Objetivo (i): caracterização automática WAVE x ASES.

Para cada página avaliada por ambas as ferramentas, responde:
  Q1 — Em que medida WAVE e ASES concordam sobre a acessibilidade das páginas?
  Q2 — Quais são os principais tipos de problemas encontrados?
  Q3 — Qual é o ranking de acessibilidade das páginas na teoria?
  Q4 — Em quais princípios WCAG (POUR) os problemas se concentram?

Saídas:
  output/gqm-analysis.html   — relatório interativo (Plotly)
  output/gqm/*.png           — figuras estáticas para artigo/LaTeX
  output/gqm/*.csv           — tabelas brutas (pareamento, top-N, seções)
"""

import json
import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats

ROOT        = Path(__file__).resolve().parent.parent
OUTPUT_DIR  = ROOT / "output"
INPUT_DIR   = ROOT / "input"
ASES_PATH   = INPUT_DIR / "ases-data.json"
PERF_PATH   = INPUT_DIR / "user-performance.json"   # stub para item 7
REPORT_HTML = OUTPUT_DIR / "gqm-analysis.html"
FIG_DIR     = OUTPUT_DIR / "gqm"


# ─── Nomes legíveis ──────────────────────────────────────────────────────────
# Mantidos como dicionário explícito para evitar derivação frágil do filename.

FLOW_NAMES = {
    "ConsultarCPF":                  "Consultar CPF",
    "ConsultaMonitoramentoServicos": "Monitoramento Serviços",
    "BuscaUnidadesAtendimento":      "Unidades RF",
    "ConsultaCenso":                 "Censo 2022",
    "ConsultaMapaDeEMpresas":        "Mapa de Empresas",
}
PAGE_NAMES = {
    "1-InicioConsultarCadastroCPF.html":   "Início CPF",
    "2-FormularioConsultaCPF.html":        "Formulário CPF",
    "3-comprovanteSituacaoCPF.html":       "Comprovante CPF",
    "1-GovernoDigital.html":               "Home Gov Digital",
    "2-EstrategiasEGovernanca.html":       "Estratégias Gov.",
    "3-TransformacaoDigital.html":         "Transformação Digital",
    "4-CentralDeQualidade.html":           "Central de Qualidade",
    "5-PainelDeMonitoramento.html":        "Painel Monitoramento",
    "1-ReceitaFederal.html":               "Home Receita",
    "2-AtendimentoPresencial.html":        "Atendimento Presencial",
    "3-UnidadesMinasGerais.html":          "Unidades MG",
    "4-UnidadesBeloHorizonte.html":        "Unidades BH",
    "5-UnidadesDeAtendimento.html":        "Buscador de Unidades",
    "1-Ibge.html":                         "Portal IBGE",
    "2-Censo2022.html":                    "Censo 2022",
    "3-ResultadosCenso2022.html":          "Panorama Censo 2022",
    "1-MapaDeEmpresas.html":               "Mapa de Empresas",
}

HIGHLIGHT_PAGE = "Comprovante CPF"   # maior descompasso WAVE×ASES com travamento de usuário


# ─── Cores ────────────────────────────────────────────────────────────────────

CAT_COLORS = {
    "error":    "#ef4444",
    "contrast": "#f97316",
    "alert":    "#eab308",
}
POUR_COLORS = {
    "perceivable":    "#3b82f6",
    "operable":       "#8b5cf6",
    "understandable": "#ec4899",
    "robust":         "#14b8a6",
}
POUR_PT = {
    "perceivable":    "Perceptível",
    "operable":       "Operável",
    "understandable": "Compreensível",
    "robust":         "Robusto",
}
SECTION_PT = {
    "marcacao":      "Marcação",
    "comportamento": "Comportamento",
    "conteudo":      "Conteúdo/Informação",
    "apresentacao":  "Apresentação / Design",
    "multimidia":    "Multimídia",
    "formularios":   "Formulários",
}
SECTION_COLORS = {
    "marcacao":      "#3b82f6",
    "comportamento": "#8b5cf6",
    "conteudo":      "#ec4899",
    "apresentacao":  "#f59e0b",
    "multimidia":    "#14b8a6",
    "formularios":   "#ef4444",
}

FLOW_COLORS = {
    "Consultar CPF":           "#60a5fa",
    "Monitoramento Serviços":  "#7c3aed",
    "Unidades RF":             "#db2777",
    "Censo 2022":              "#ea580c",
    "Mapa de Empresas":        "#16a34a",
}

# Layout base: legenda sempre embaixo (fora do título), margens generosas.
LAYOUT_BASE = dict(
    paper_bgcolor="white",
    plot_bgcolor="#f8fafc",
    font=dict(family="system-ui, sans-serif", size=12, color="#1e293b"),
    margin=dict(l=20, r=20, t=80, b=110),
    legend=dict(orientation="h", yanchor="top", y=-0.22,
                xanchor="center", x=0.5,
                bgcolor="rgba(255,255,255,0.85)"),
)
CHART_CONFIG = {"displaylogo": False, "responsive": True}


def title_dict(text: str) -> dict:
    return dict(text=text, x=0.02, xanchor="left", y=0.96, yanchor="top",
                font=dict(size=15, color="#0f172a"))


def _fallback_name(filename: str) -> str:
    name = filename.replace(".html", "").replace(".htm", "")
    parts = name.split("-", 1)
    return parts[1] if len(parts) > 1 else name


def page_name(filename: str) -> str:
    return PAGE_NAMES.get(filename, _fallback_name(filename))


def flow_label(flow_key: str) -> str:
    return FLOW_NAMES.get(flow_key, re.sub(r"([A-Z])", r" \1", flow_key).strip())


# ─── Carregar WAVE + ASES e parear por (flow, source_file) ────────────────────

def load_paired() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    ases = json.loads(ASES_PATH.read_text(encoding="utf-8"))
    ases_flows = ases["flows"]
    meta = ases.get("_meta", {})

    paired_rows, issue_rows, section_rows = [], [], []

    for flow_dir in sorted(OUTPUT_DIR.iterdir()):
        if not flow_dir.is_dir():
            continue
        report_path = flow_dir / "wave-report.json"
        if not report_path.exists():
            continue

        flow = flow_dir.name
        ases_pages = {p["source_file"]: p for p in ases_flows.get(flow, [])}
        wave_pages = json.loads(report_path.read_text(encoding="utf-8"))

        for page in wave_pages:
            sf = page["source_file"]
            s = page["summary"]
            pb = s.get("pour_breakdown") or {}

            ap = ases_pages.get(sf)
            if not ap:
                print(f"  [aviso] sem ASES para {flow}/{sf} — pulado")
                continue

            sec = ap["sections"]
            ases_err = sum(v["errors"]   for v in sec.values())
            ases_wrn = sum(v["warnings"] for v in sec.values())

            paired_rows.append({
                "flow":             flow,
                "flow_label":       flow_label(flow),
                "source_file":      sf,
                "page":             page_name(sf),
                "ases_title":       ap.get("title", ""),
                "aim_score":        s.get("aim_score"),
                "ases_score":       ap["score"],
                "wave_errors":          s.get("errors", 0),
                "wave_contrast_errors": s.get("contrast_errors", 0),
                "wave_alerts":          s.get("alerts", 0),
                "wave_total_negatives": (s.get("errors", 0) + s.get("contrast_errors", 0)
                                         + s.get("alerts", 0)),
                "ases_errors":          ases_err,
                "ases_warnings":        ases_wrn,
                "ases_total_negatives": ases_err + ases_wrn,
                "pour_perceivable":    pb.get("perceivable", 0),
                "pour_operable":       pb.get("operable", 0),
                "pour_understandable": pb.get("understandable", 0),
                "pour_robust":         pb.get("robust", 0),
            })

            for cat in page.get("categories", []):
                if cat["category"] not in ("error", "contrast", "alert"):
                    continue
                for t in cat.get("types", []):
                    issue_rows.append({
                        "flow":       flow,
                        "flow_label": flow_label(flow),
                        "page":       page_name(sf),
                        "category":   cat["category"],
                        "type_id":    t["type_id"],
                        "type_label": t["type_label"],
                        "count":      t.get("count", 0),
                        "wcag_criteria":   ";".join(t["wcag_criteria"]) if t.get("wcag_criteria") else "",
                        "wcag_level":      t.get("wcag_level") or "",
                        "pour_dimensions": ";".join(t["pour_dimensions"]) if t.get("pour_dimensions") else "",
                        "sr_relevance":    t.get("sr_relevance") or "",
                    })

            for sec_key, vals in sec.items():
                section_rows.append({
                    "flow":          flow,
                    "flow_label":    flow_label(flow),
                    "page":          page_name(sf),
                    "section":       sec_key,
                    "section_label": SECTION_PT[sec_key],
                    "errors":        vals["errors"],
                    "warnings":      vals["warnings"],
                })

    return (pd.DataFrame(paired_rows),
            pd.DataFrame(issue_rows),
            pd.DataFrame(section_rows),
            meta)


def load_user_performance() -> pd.DataFrame | None:
    """Item 7 (stub): carrega dados de desempenho dos usuários se existirem.

    Formato esperado em input/user-performance.json:
      {"tasks": [{"flow": "ConsultarCPF", "page": "Comprovante CPF",
                  "completion_rate": 0.6, "nasa_tlx_mean": 72.5, "n": 5}, ...]}
    """
    if not PERF_PATH.exists():
        return None
    try:
        data = json.loads(PERF_PATH.read_text(encoding="utf-8"))
        rows = data.get("tasks", [])
        if not rows:
            return None
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"  [aviso] não consegui ler {PERF_PATH.name}: {e}")
        return None


# ─── Métricas ────────────────────────────────────────────────────────────────

def spearman(x, y):
    if len(x) < 3:
        return float("nan"), float("nan")
    rho, p = stats.spearmanr(x, y)
    return float(rho), float(p)


def pearson(x, y):
    if len(x) < 3:
        return float("nan"), float("nan")
    r, p = stats.pearsonr(x, y)
    return float(r), float(p)


# ─── Gráficos ─────────────────────────────────────────────────────────────────

def fig_to_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, config=CHART_CONFIG, include_plotlyjs=False)


def save_png(fig: go.Figure, name: str, width: int = 1000, height: int = 640):
    try:
        fig.write_image(str(FIG_DIR / f"{name}.png"), width=width, height=height, scale=2)
    except Exception as e:
        print(f"  [aviso] PNG '{name}' não gerado: {e}")


def chart_scatter_wave_ases(df: pd.DataFrame) -> go.Figure:
    """Item 6 + 8: scatter dedicado mostrando que WAVE×ASES quase não concordam,
    com a página 'Comprovante CPF' destacada (item 8)."""
    rho, p_rho = spearman(df["aim_score"], df["ases_score"])
    r,   _     = pearson (df["aim_score"], df["ases_score"])

    fig = go.Figure()
    for flow_lbl, sub in df.groupby("flow_label"):
        fig.add_trace(go.Scatter(
            x=sub["aim_score"], y=sub["ases_score"],
            mode="markers", name=flow_lbl,
            marker=dict(size=14, line=dict(width=1.5, color="#1e293b"),
                        color=FLOW_COLORS.get(flow_lbl, "#64748b")),
            text=sub["page"],
            hovertemplate="<b>%{text}</b><br>AIM: %{x:.2f}<br>ASES: %{y:.2f}%<extra></extra>",
        ))

    # ajuste linear como referência visual
    if len(df) >= 2:
        x = df["aim_score"].to_numpy()
        y = df["ases_score"].to_numpy()
        slope, intercept = stats.linregress(x, y)[:2]
        xs = [0, 10]
        ys = [slope * v + intercept for v in xs]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="Ajuste linear",
                                 line=dict(color="#94a3b8", dash="dash"), showlegend=False,
                                 hoverinfo="skip"))

    # destaque da página com maior descompasso (item 8)
    h = df[df["page"] == HIGHLIGHT_PAGE]
    if not h.empty:
        hx = float(h["aim_score"].iloc[0])
        hy = float(h["ases_score"].iloc[0])
        fig.add_trace(go.Scatter(
            x=[hx], y=[hy], mode="markers",
            name="Maior divergência",
            marker=dict(size=22, color="rgba(0,0,0,0)",
                        line=dict(width=3, color="#dc2626")),
            hoverinfo="skip",
        ))
        fig.add_annotation(
            x=hx, y=hy,
            text=("<b>Comprovante CPF</b><br>AIM 10/10 (perfeito) × ASES 89,5%<br>"
                  "Onde um usuário travou na sessão real."),
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2, arrowcolor="#dc2626",
            ax=-220, ay=120,
            bgcolor="#fee2e2", bordercolor="#dc2626", borderwidth=1.5,
            borderpad=8, font=dict(color="#7f1d1d", size=11),
            align="left",
        )

    # rótulo do ρ no canto inferior direito (área vazia do gráfico)
    fig.add_annotation(
        xref="paper", yref="paper", x=0.99, y=0.02, xanchor="right", yanchor="bottom",
        text=(f"<b>ρ Spearman = {rho:.2f}</b><br>"
              f"<span style='font-size:11px'>p = {p_rho:.3f} • Pearson r = {r:.2f}</span><br>"
              "<span style='font-size:11px'>→ rankings das duas ferramentas<br>"
              "praticamente não se correlacionam</span>"),
        showarrow=False, align="right",
        bgcolor="rgba(254, 243, 199, 0.95)",
        bordercolor="#d97706", borderwidth=1.5, borderpad=10,
        font=dict(size=15, color="#78350f"),
    )

    fig.update_layout(
        **LAYOUT_BASE,
        title=title_dict("Concordância WAVE × ASES — escalas originais"),
        height=620,
        xaxis=dict(range=[0, 10.5], title="AIM (WAVE) — 0 a 10",
                   gridcolor="#e2e8f0", zeroline=False),
        yaxis=dict(range=[0, 100], title="Nota ASES — 0 a 100 (%)",
                   gridcolor="#e2e8f0", zeroline=False),
    )
    return fig


def chart_rankings_side_by_side(df: pd.DataFrame) -> go.Figure:
    """Cada lado mostra seu próprio ranking (melhor no topo).
    Cor por fluxo evidencia onde as ordens divergem — uma página pode estar
    no topo de um lado e no rodapé do outro."""
    aim_sorted  = df.sort_values("aim_score",  ascending=True).copy()   # menor embaixo, maior topo
    ases_sorted = df.sort_values("ases_score", ascending=True).copy()

    aim_labels  = (aim_sorted ["flow_label"] + " — " + aim_sorted ["page"]).tolist()
    ases_labels = (ases_sorted["flow_label"] + " — " + ases_sorted["page"]).tolist()

    fig = make_subplots(rows=1, cols=2, shared_yaxes=False,
                        horizontal_spacing=0.04,
                        subplot_titles=("AIM (WAVE) — 0–10  •  ranking próprio",
                                        "ASES — 0–100 (%)  •  ranking próprio"))

    # Uma trace por fluxo em cada subplot. Legenda só na coluna esquerda.
    for flow_lbl in df["flow_label"].unique():
        color = FLOW_COLORS.get(flow_lbl, "#64748b")

        sa = aim_sorted[aim_sorted["flow_label"] == flow_lbl]
        sb = ases_sorted[ases_sorted["flow_label"] == flow_lbl]

        fig.add_trace(go.Bar(
            x=sa["aim_score"],
            y=(sa["flow_label"] + " — " + sa["page"]).tolist(),
            orientation="h",
            marker_color=color,
            text=sa["aim_score"].round(2), textposition="outside",
            textfont=dict(size=15, color="#0f172a", family="system-ui, sans-serif"),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>AIM: %{x:.2f}<extra></extra>",
            name=flow_lbl, legendgroup=flow_lbl, showlegend=True,
        ), row=1, col=1)

        fig.add_trace(go.Bar(
            x=sb["ases_score"],
            y=(sb["flow_label"] + " — " + sb["page"]).tolist(),
            orientation="h",
            marker_color=color,
            text=sb["ases_score"].round(2).astype(str) + "%", textposition="outside",
            textfont=dict(size=15, color="#0f172a", family="system-ui, sans-serif"),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>ASES: %{x:.2f}%<extra></extra>",
            name=flow_lbl, legendgroup=flow_lbl, showlegend=False,
        ), row=1, col=2)

    # Cada lado tem sua ordem (ascendente → melhor fica no topo).
    # Labels do AIM ficam à esquerda; labels do ASES vão à direita para não
    # colidirem com as barras do AIM.
    tick_font = dict(size=14, color="#1e293b", family="system-ui, sans-serif")
    axis_tick_font = dict(size=13, color="#475569", family="system-ui, sans-serif")
    fig.update_yaxes(categoryorder="array", categoryarray=aim_labels,
                     tickfont=tick_font, row=1, col=1)
    fig.update_yaxes(categoryorder="array", categoryarray=ases_labels,
                     side="right", tickfont=tick_font, row=1, col=2)
    fig.update_xaxes(range=[0, 10.6], tickfont=axis_tick_font, row=1, col=1)
    fig.update_xaxes(range=[60, 105], tickfont=axis_tick_font, row=1, col=2)

    # Subtítulos dos subplots (anotações criadas por make_subplots) também maiores.
    for ann in fig["layout"]["annotations"]:
        ann["font"] = dict(size=15, color="#0f172a", family="system-ui, sans-serif")

    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="#f8fafc",
        font=dict(family="system-ui, sans-serif", size=14, color="#1e293b"),
        title=dict(text="Ranking teórico — cada ferramenta ordenada pelo seu próprio ranking (melhor no topo)",
                   x=0.02, xanchor="left", y=0.97,
                   font=dict(size=18, color="#0f172a")),
        margin=dict(l=260, r=260, t=96, b=100),
        legend=dict(orientation="h", yanchor="top", y=-0.05,
                    xanchor="center", x=0.5,
                    bgcolor="rgba(255,255,255,0.85)",
                    font=dict(size=13, color="#1e293b")),
        height=max(520, 46 * len(df)),
        uniformtext=dict(minsize=13, mode="show"),
    )
    return fig


def chart_top_wave_types(issues: pd.DataFrame, n: int = 15) -> go.Figure:
    agg = (issues.groupby(["type_id", "type_label", "category"], as_index=False)["count"]
           .sum()
           .sort_values("count", ascending=False)
           .head(n))
    colors = agg["category"].map(CAT_COLORS).fillna("#94a3b8")
    fig = go.Figure(go.Bar(
        x=agg["count"], y=agg["type_label"], orientation="h",
        marker_color=colors,
        text=agg["count"], textposition="outside",
        hovertemplate="%{y}<br>%{x} ocorrências<extra></extra>",
        showlegend=False,
    ))
    layout = {**LAYOUT_BASE,
              "margin": dict(l=20, r=20, t=80, b=40),
              "legend": dict(visible=False)}
    fig.update_layout(
        **layout,
        title=title_dict(f"Top-{n} tipos de problema reportados pelo WAVE"),
        height=max(380, 34 * len(agg)),
        xaxis_title="Ocorrências",
        yaxis=dict(autorange="reversed"),
    )
    return fig


def chart_top_wave_categories(issues: pd.DataFrame) -> go.Figure:
    agg = (issues.groupby("category", as_index=False)["count"].sum()
           .sort_values("count", ascending=False))
    label_map = {"error": "Erros", "contrast": "Erros de Contraste", "alert": "Alertas"}
    agg["label"] = agg["category"].map(label_map)
    fig = go.Figure(go.Bar(
        x=agg["label"], y=agg["count"],
        marker_color=[CAT_COLORS.get(c, "#94a3b8") for c in agg["category"]],
        text=agg["count"], textposition="outside",
        showlegend=False,
    ))
    layout = {**LAYOUT_BASE,
              "margin": dict(l=20, r=20, t=80, b=60),
              "legend": dict(visible=False)}
    fig.update_layout(**layout,
                      title=title_dict("Categorias WAVE — total agregado"),
                      height=400, yaxis_title="Ocorrências")
    return fig


def chart_top_ases_sections(sections: pd.DataFrame) -> go.Figure:
    agg = (sections.groupby(["section", "section_label"], as_index=False)
           .agg(errors=("errors", "sum"), warnings=("warnings", "sum")))
    agg["total"] = agg["errors"] + agg["warnings"]
    agg = agg.sort_values("total", ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Erros", x=agg["section_label"], y=agg["errors"],
                         marker_color="#ef4444"))
    fig.add_trace(go.Bar(name="Alertas", x=agg["section_label"], y=agg["warnings"],
                         marker_color="#eab308"))
    fig.update_layout(**LAYOUT_BASE, barmode="stack",
                      title=title_dict("ASES — erros e alertas por seção (agregado)"),
                      height=440, yaxis_title="Ocorrências",
                      xaxis=dict(tickangle=-15))
    return fig


def chart_pour_aggregate(df: pd.DataFrame) -> go.Figure:
    totals = {dim: int(df[f"pour_{dim}"].sum()) for dim in POUR_PT}
    labels = [POUR_PT[k] for k in totals]
    values = [totals[k] for k in totals]
    colors = [POUR_COLORS[k] for k in totals]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors,
                           text=values, textposition="outside", showlegend=False))
    layout = {**LAYOUT_BASE,
              "margin": dict(l=20, r=20, t=80, b=60),
              "legend": dict(visible=False)}
    fig.update_layout(**layout,
                      title=title_dict("Concentração de problemas WAVE por princípio WCAG (POUR)"),
                      height=420, yaxis_title="Ocorrências de erros/alertas")
    return fig


def chart_pour_per_page(df: pd.DataFrame) -> go.Figure:
    d = df.copy()
    labels = d["flow_label"] + " — " + d["page"]
    fig = go.Figure()
    for dim, pt in POUR_PT.items():
        fig.add_trace(go.Bar(
            name=pt, y=labels, x=d[f"pour_{dim}"], orientation="h",
            marker_color=POUR_COLORS[dim],
            hovertemplate=f"{pt}: %{{x}}<extra></extra>",
        ))
    fig.update_layout(**LAYOUT_BASE, barmode="stack",
                      title=title_dict("POUR por página — distribuição empilhada"),
                      height=max(420, 32 * len(d)),
                      yaxis=dict(autorange="reversed"),
                      xaxis_title="Ocorrências de erros/alertas")
    return fig


def chart_ases_sections_per_page(sections: pd.DataFrame) -> go.Figure:
    d = sections.copy()
    d["page_full"] = d["flow_label"] + " — " + d["page"]
    d["total"] = d["errors"] + d["warnings"]
    pivot = d.pivot_table(index="page_full", columns="section_label",
                          values="total", aggfunc="sum", fill_value=0)
    order = pivot.sum(axis=0).sort_values(ascending=False).index.tolist()
    pivot = pivot[order]
    page_order = pivot.sum(axis=1).sort_values(ascending=True).index.tolist()
    pivot = pivot.loc[page_order]

    fig = go.Figure()
    for section_label in pivot.columns:
        key = next((k for k, v in SECTION_PT.items() if v == section_label), None)
        fig.add_trace(go.Bar(
            name=section_label, y=pivot.index, x=pivot[section_label],
            orientation="h",
            marker_color=SECTION_COLORS.get(key, "#94a3b8"),
            hovertemplate=f"{section_label}: %{{x}}<extra></extra>",
        ))
    fig.update_layout(**LAYOUT_BASE, barmode="stack",
                      title=title_dict("ASES — erros + alertas por seção e por página"),
                      height=max(420, 32 * len(pivot)),
                      xaxis_title="Ocorrências (erros + alertas)")
    return fig


def chart_tech_vs_user(paired: pd.DataFrame, perf: pd.DataFrame) -> go.Figure:
    """Item 7: nota técnica × desempenho real dos usuários.

    Espera colunas em `perf`: page (str), completion_rate (0-1), nasa_tlx_mean (0-100), n (int).
    Mescla com `paired` por nome de página e plota dois subplots: AIM×completion e ASES×TLX.
    """
    d = paired.merge(perf, on="page", how="inner")
    if d.empty:
        raise ValueError("merge vazio — confira nomes de páginas em user-performance.json")

    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.12,
                        subplot_titles=("AIM (WAVE) × taxa de conclusão",
                                        "ASES × NASA-TLX (maior = pior carga)"))

    fig.add_trace(go.Scatter(
        x=d["aim_score"], y=d["completion_rate"] * 100,
        mode="markers+text", text=d["page"], textposition="top center",
        marker=dict(size=14, color="#2563eb",
                    line=dict(width=1.5, color="#1e293b")),
        name="Páginas",
        hovertemplate="%{text}<br>AIM: %{x:.2f}<br>Conclusão: %{y:.0f}%<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=d["ases_score"], y=d["nasa_tlx_mean"],
        mode="markers+text", text=d["page"], textposition="top center",
        marker=dict(size=14, color="#dc2626",
                    line=dict(width=1.5, color="#1e293b")),
        name="Páginas",
        hovertemplate="%{text}<br>ASES: %{x:.2f}%<br>NASA-TLX: %{y:.1f}<extra></extra>",
        showlegend=False,
    ), row=1, col=2)

    rho1, _ = spearman(d["aim_score"], d["completion_rate"])
    rho2, _ = spearman(d["ases_score"], d["nasa_tlx_mean"])

    fig.update_xaxes(title_text="AIM (0–10)", row=1, col=1, range=[0, 10.5])
    fig.update_yaxes(title_text="Taxa de conclusão (%)", row=1, col=1, range=[0, 105])
    fig.update_xaxes(title_text="ASES (%)", row=1, col=2, range=[60, 102])
    fig.update_yaxes(title_text="NASA-TLX (média)", row=1, col=2, range=[0, 105])

    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="#f8fafc",
        font=dict(family="system-ui, sans-serif", size=12, color="#1e293b"),
        title=dict(text=(f"Técnico × vivido — ρ(AIM, conclusão) = {rho1:.2f} • "
                         f"ρ(ASES, TLX) = {rho2:.2f}"),
                   x=0.02, xanchor="left", y=0.97,
                   font=dict(size=15, color="#0f172a")),
        margin=dict(l=20, r=20, t=80, b=60),
        height=540, showlegend=False,
    )
    return fig


# ─── KPIs / tabelas ───────────────────────────────────────────────────────────

def build_kpi_block(df: pd.DataFrame) -> str:
    rho_score, p_score = spearman(df["aim_score"], df["ases_score"])
    h = df[df["page"] == HIGHLIGHT_PAGE]
    highlight_html = ""
    if not h.empty:
        gap = h["ases_score"].iloc[0] - h["aim_score"].iloc[0] * 10
        highlight_html = (f"AIM {h['aim_score'].iloc[0]:.0f}/10 × ASES "
                          f"{h['ases_score'].iloc[0]:.2f}% (Δ {gap:+.1f} pp)")

    kpis = [
        ("📄", str(len(df)),                      "Páginas pareadas",                  "#3b82f6"),
        ("🎯", f"{df['aim_score'].mean():.2f}/10", "AIM médio (WAVE)",                  "#22c55e"),
        ("🎯", f"{df['ases_score'].mean():.2f}%",  "ASES médio",                        "#10b981"),
        ("🔗", f"ρ = {rho_score:.2f}",             f"Spearman WAVE×ASES (p={p_score:.3f})", "#8b5cf6"),
        ("⚠️", HIGHLIGHT_PAGE,                    highlight_html or "—",               "#dc2626"),
    ]
    return "".join(f"""
    <div class="kpi-card" style="border-left:4px solid {c}">
      <div class="kpi-icon">{icon}</div>
      <div class="kpi-value" style="color:{c}">{val}</div>
      <div class="kpi-label">{label}</div>
    </div>""" for icon, val, label, c in kpis)


def table_paired(df: pd.DataFrame) -> str:
    d = df[["flow_label", "page", "aim_score", "ases_score",
            "wave_total_negatives", "ases_total_negatives",
            "pour_perceivable", "pour_operable",
            "pour_understandable", "pour_robust"]].copy()
    d["rank_aim"]  = d["aim_score"].rank(ascending=False, method="min").astype(int)
    d["rank_ases"] = d["ases_score"].rank(ascending=False, method="min").astype(int)
    d["aim_score"]  = d["aim_score"].round(2)
    d["ases_score"] = d["ases_score"].round(2)
    d = d[["flow_label", "page", "aim_score", "rank_aim",
           "ases_score", "rank_ases",
           "wave_total_negatives", "ases_total_negatives",
           "pour_perceivable", "pour_operable",
           "pour_understandable", "pour_robust"]]
    d.columns = ["Fluxo", "Página", "AIM", "Rank AIM",
                 "ASES (%)", "Rank ASES",
                 "WAVE erros+alertas", "ASES erros+alertas",
                 "POUR P", "POUR O", "POUR U", "POUR R"]
    return d.to_html(index=False, escape=False, classes="data-table", border=0)


def table_top_wave(issues: pd.DataFrame, n: int = 15) -> str:
    agg = (issues.groupby(
        ["type_id", "type_label", "category", "wcag_criteria",
         "wcag_level", "pour_dimensions", "sr_relevance"], as_index=False)
        .agg(total=("count", "sum"), pages=("page", "nunique"))
        .sort_values("total", ascending=False)
        .head(n))
    agg = agg[["type_label", "type_id", "category", "total", "pages",
               "wcag_criteria", "wcag_level", "pour_dimensions", "sr_relevance"]]
    agg.columns = ["Problema", "type_id", "Categoria", "Ocorrências", "Páginas",
                   "WCAG", "Nível", "POUR", "Impacto LS"]
    return agg.to_html(index=False, escape=False, classes="data-table", border=0)


def table_top_ases(sections: pd.DataFrame) -> str:
    agg = (sections.groupby(["section", "section_label"], as_index=False)
           .agg(errors=("errors", "sum"), warnings=("warnings", "sum")))
    agg["total"] = agg["errors"] + agg["warnings"]
    agg = agg.sort_values("total", ascending=False)[
        ["section_label", "errors", "warnings", "total"]]
    agg.columns = ["Seção (ASES)", "Erros", "Alertas", "Total"]
    return agg.to_html(index=False, escape=False, classes="data-table", border=0)


# ─── HTML ─────────────────────────────────────────────────────────────────────

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: #f8fafc;
  color: #1e293b; line-height: 1.5; }
.app-header { background: #1e293b; color: #f8fafc; padding: 1.25rem 2rem; }
.app-header h1 { font-size: 1.5rem; font-weight: 700; }
.app-header p { color: #94a3b8; font-size: 0.875rem; margin-top: 0.25rem; }
.main { max-width: 1400px; margin: 0 auto; padding: 2rem; }
h2 { font-size: 1.35rem; font-weight: 700; margin: 2rem 0 0.75rem; color: #0f172a;
  border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }
h3 { font-size: 1.05rem; font-weight: 600; margin: 1.25rem 0 0.5rem; color: #1e293b; }
.lead { color: #475569; font-size: 0.95rem; margin-bottom: 1rem; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem; margin-bottom: 1.5rem; }
.kpi-card { background: #fff; border-radius: 0.75rem; padding: 1.1rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.kpi-icon { font-size: 1.4rem; margin-bottom: 0.4rem; }
.kpi-value { font-size: 1.5rem; font-weight: 800; line-height: 1.1; }
.kpi-label { font-size: 0.78rem; color: #64748b; margin-top: 0.35rem; }
.chart-card { background: #fff; border-radius: 0.75rem; padding: 1rem 0.5rem 0.5rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 1rem; }
.chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
  gap: 1rem; margin-bottom: 1rem; }
.chart-full { grid-column: 1 / -1; }
.table-wrap { overflow-x: auto; border-radius: 0.75rem; border: 1px solid #e2e8f0;
  margin-bottom: 1.5rem; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; background: #fff; }
.data-table th { background: #f1f5f9; padding: 0.55rem 0.8rem; text-align: left;
  font-weight: 600; color: #475569; font-size: 0.8rem; white-space: nowrap;
  border-bottom: 1px solid #e2e8f0; }
.data-table td { padding: 0.5rem 0.8rem; border-bottom: 1px solid #f1f5f9; }
.data-table tr:hover td { background: #f8fafc; }
.note { background: #fff7ed; border-left: 3px solid #f97316; padding: 0.75rem 1rem;
  border-radius: 0.375rem; color: #7c2d12; font-size: 0.875rem; margin: 1rem 0; }
.stub { background: #f1f5f9; border: 1px dashed #94a3b8; border-radius: 0.75rem;
  padding: 1.5rem; color: #475569; margin: 1rem 0; }
.stub strong { color: #1e293b; }
.stub code { background: #fff; padding: 0.15rem 0.45rem; border-radius: 0.25rem;
  font-size: 0.85rem; border: 1px solid #e2e8f0; }
.callout-cpf { background: #fef2f2; border-left: 4px solid #dc2626;
  padding: 1rem 1.25rem; border-radius: 0.5rem; margin: 1rem 0; color: #7f1d1d; }
.callout-cpf strong { color: #991b1b; }
"""


def build_html(paired: pd.DataFrame, issues: pd.DataFrame,
               sections: pd.DataFrame, meta: dict, figs: dict,
               perf_df: pd.DataFrame | None) -> str:
    plotly_js = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>'
    kpi_html = build_kpi_block(paired)

    h = paired[paired["page"] == HIGHLIGHT_PAGE]
    cpf_callout = ""
    if not h.empty:
        a = h.iloc[0]
        cpf_callout = f"""
  <div class="callout-cpf">
    <strong>Maior divergência entre as ferramentas — {HIGHLIGHT_PAGE}.</strong>
    WAVE atribuiu AIM <strong>{a['aim_score']:.0f}/10</strong> (sinaliza apenas {a['wave_total_negatives']}
    erros/alertas), enquanto ASES atribuiu <strong>{a['ases_score']:.2f}%</strong>
    com {a['ases_total_negatives']} ocorrências em suas seções. Nas sessões com usuários,
    foi exatamente nesta página que um participante travou — sugerindo que a métrica
    "perfeita" do WAVE deixou de capturar barreiras vividas na prática.
  </div>"""

    if perf_df is not None and "tech_vs_user" in figs:
        item7 = f'<div class="chart-card chart-full">{fig_to_html(figs["tech_vs_user"])}</div>'
    else:
        item7 = """
  <div class="stub">
    <strong>Aguardando dados de desempenho dos usuários.</strong>
    Para gerar o cruzamento técnico × vivido, crie
    <code>input/user-performance.json</code> com o seguinte formato:
    <pre style="background:#fff;padding:0.75rem;border-radius:0.5rem;margin-top:0.5rem;
      border:1px solid #e2e8f0;font-size:0.8rem;overflow-x:auto">
{
  "tasks": [
    {"page": "Comprovante CPF", "completion_rate": 0.6, "nasa_tlx_mean": 72.5, "n": 5},
    {"page": "Buscador de Unidades", "completion_rate": 0.8, "nasa_tlx_mean": 55.0, "n": 5}
  ]
}</pre>
    A chave <code>page</code> precisa bater com os nomes legíveis das páginas
    (veja a coluna "Página" na tabela do Q3 abaixo). Rode novamente
    <code>py -3 src/gqm_analysis.py</code> e o gráfico aparece automaticamente aqui.
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GQM — Objetivo (i): WAVE × ASES</title>
  {plotly_js}
  <style>{CSS}</style>
</head>
<body>
<header class="app-header">
  <h1>GQM — Objetivo (i): caracterização automática WAVE × ASES</h1>
  <p>Comparação das notas, rankings e tipos de problema reportados pelas duas ferramentas.</p>
</header>

<main class="main">

  <section>
    <div class="kpi-grid">{kpi_html}</div>
    <p class="lead">
      WAVE retorna a pontuação AIM (0–10) e categoriza problemas por tipo e princípio WCAG/POUR.
      ASES retorna nota percentual (0–100%) e agrupa por seção do eMAG.
      Esta análise pareia as duas ferramentas por página, calcula a correlação de Spearman
      e destaca onde os problemas se concentram — e onde elas <em>discordam</em>.
    </p>
  </section>

  <h2>Q1 — Em que medida WAVE e ASES concordam?</h2>
  <p class="lead">
    Resultado central: <strong>quase nada</strong>. ρ de Spearman = 0,12 indica que
    as duas ferramentas ordenam as páginas de formas praticamente independentes.
  </p>
  <div class="chart-card chart-full">{fig_to_html(figs['scatter'])}</div>
  {cpf_callout}

  <h2>Q2 — Principais tipos de problema</h2>
  <p class="lead">Top tipos reportados pelo WAVE e distribuição por seção do ASES.</p>
  <div class="chart-card">{fig_to_html(figs['top_wave'])}</div>
  <div class="chart-grid">
    <div class="chart-card">{fig_to_html(figs['top_wave_cats'])}</div>
    <div class="chart-card">{fig_to_html(figs['top_ases'])}</div>
  </div>

  <h3>Top tipos WAVE — tabela com metadados WCAG/POUR/LS</h3>
  <div class="table-wrap">{table_top_wave(issues, n=15)}</div>

  <h3>ASES — totais por seção (todas as páginas)</h3>
  <div class="table-wrap">{table_top_ases(sections)}</div>

  <h2>Q3 — Ranking teórico de acessibilidade</h2>
  <p class="lead">
    Páginas ordenadas pelo AIM (WAVE) crescente, com a nota ASES espelhada para
    comparação visual. As barras ASES "saltando" para cima e para baixo são a versão
    visual do ρ baixo: páginas vizinhas no eixo AIM não estão próximas no eixo ASES.
  </p>
  <div class="chart-card chart-full">{fig_to_html(figs['rankings'])}</div>
  <div class="table-wrap">{table_paired(paired)}</div>

  <h2>Q4 — Concentração por princípio WCAG (POUR)</h2>
  <p class="lead">
    Distribuição das ocorrências de erros e alertas do WAVE pelos quatro princípios
    do WCAG (Perceptível / Operável / Compreensível / Robusto). Um mesmo tipo pode
    contar em mais de uma dimensão.
  </p>
  <div class="chart-grid">
    <div class="chart-card">{fig_to_html(figs['pour_total'])}</div>
    <div class="chart-card">{fig_to_html(figs['pour_page'])}</div>
  </div>

  <h3>ASES — concentração por seção e por página</h3>
  <div class="chart-card chart-full">{fig_to_html(figs['ases_page'])}</div>

  <h2>Confronto técnico × vivido <small style="color:#94a3b8;font-weight:400">(objetivo (iii) do GQM)</small></h2>
  <p class="lead">
    Aqui a nota técnica de cada página (AIM e ASES) é confrontada com o desempenho real
    dos usuários (taxa de conclusão e NASA-TLX). É a evidência mais importante: se as
    ferramentas automáticas não predizem o que os usuários vivem, o uso isolado delas
    como métrica de acessibilidade fica fragilizado.
  </p>
  {item7}

  <div class="note">
    <strong>Como interpretar ρ de Spearman:</strong> varia de −1 a 1. Próximo de +1, as
    duas ferramentas concordam sobre quais páginas são mais acessíveis; próximo de 0,
    os rankings são essencialmente independentes; negativo, discordam sistematicamente.
    Com ρ = 0,12, escolher entre WAVE e ASES para classificar páginas é praticamente
    arbitrário — o que reforça a necessidade do confronto técnico × vivido acima.
  </div>

</main>
</body>
</html>"""


# ─── Entrypoint ──────────────────────────────────────────────────────────────

def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    print("Carregando WAVE + ASES…")
    paired, issues, sections, meta = load_paired()
    if paired.empty:
        print("Nenhuma página pareada. Verifique output/ e input/ases-data.json.")
        raise SystemExit(1)
    print(f"  {len(paired)} páginas pareadas em {paired['flow'].nunique()} fluxos.")

    perf = load_user_performance()
    if perf is None:
        print("  (item 7) sem input/user-performance.json — gráfico técnico×vivido será stub.")
    else:
        print(f"  (item 7) {len(perf)} entradas de desempenho carregadas.")

    # CSVs brutos
    paired.to_csv(FIG_DIR / "paired-wave-ases.csv", index=False, encoding="utf-8")
    issues.to_csv(FIG_DIR / "wave-issues-long.csv", index=False, encoding="utf-8")
    sections.to_csv(FIG_DIR / "ases-sections-long.csv", index=False, encoding="utf-8")

    figs = {
        "scatter":       chart_scatter_wave_ases(paired),
        "rankings":      chart_rankings_side_by_side(paired),
        "top_wave":      chart_top_wave_types(issues, n=15),
        "top_wave_cats": chart_top_wave_categories(issues),
        "top_ases":      chart_top_ases_sections(sections),
        "pour_total":    chart_pour_aggregate(paired),
        "pour_page":     chart_pour_per_page(paired),
        "ases_page":     chart_ases_sections_per_page(sections),
    }
    if perf is not None:
        try:
            figs["tech_vs_user"] = chart_tech_vs_user(paired, perf)
        except Exception as e:
            print(f"  [aviso] gráfico técnico×vivido falhou: {e}")

    print(f"Exportando PNGs para {FIG_DIR}/ …")
    save_png(figs["scatter"],       "01-scatter-wave-ases",       width=1100, height=680)
    save_png(figs["rankings"],      "03-rankings-side-by-side",   width=1600, height=860)
    save_png(figs["top_wave"],      "04-top-wave-types",          width=1100, height=620)
    save_png(figs["top_wave_cats"], "05-top-wave-categories",     width=900,  height=440)
    save_png(figs["top_ases"],      "06-top-ases-sections",       width=900,  height=460)
    save_png(figs["pour_total"],    "07-pour-aggregate",          width=900,  height=460)
    save_png(figs["pour_page"],     "08-pour-per-page",           width=1100, height=720)
    save_png(figs["ases_page"],     "09-ases-sections-per-page",  width=1100, height=720)
    if "tech_vs_user" in figs:
        save_png(figs["tech_vs_user"], "10-tech-vs-user", width=1200, height=560)

    html = build_html(paired, issues, sections, meta, figs, perf)
    REPORT_HTML.write_text(html, encoding="utf-8")
    print(f"Relatório HTML em: {REPORT_HTML}")
    print(f"PNGs/CSVs em: {FIG_DIR}/")


if __name__ == "__main__":
    main()
