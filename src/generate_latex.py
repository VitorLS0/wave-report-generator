#!/usr/bin/env python3
"""Generate LaTeX tables and figures from WAVE JSON output."""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker

OUTPUT_DIR  = Path("./output")
LATEX_DIR   = OUTPUT_DIR / "latex"
FIGURES_DIR = LATEX_DIR / "figures"
TABLES_DIR  = LATEX_DIR / "tables"

# ─── Colours ──────────────────────────────────────────────────────────────────

CAT_COLORS = {
    "errors":           "#ef4444",
    "contrast_errors":  "#f97316",
    "alerts":           "#eab308",
    "features":         "#22c55e",
    "structure":        "#3b82f6",
    "aria":             "#8b5cf6",
}
SR_COLORS = {
    "sr_critical": "#c0392b",  # vermelho forte
    "sr_high":     "#e67e22",  # laranja
    "sr_medium":   "#f1c40f",  # amarelo
    "sr_low":      "#27ae60",  # verde
}
POUR_COLORS = {
    "pour_perceivable":    "#3b82f6",
    "pour_operable":       "#8b5cf6",
    "pour_understandable": "#ec4899",
    "pour_robust":         "#14b8a6",
}
POUR_PT = {
    "pour_perceivable":    "Perceptível",
    "pour_operable":       "Operável",
    "pour_understandable": "Compreensível",
    "pour_robust":         "Robusto",
}
SR_PT = {
    "sr_critical": "Crítico",
    "sr_high":     "Alto",
    "sr_medium":   "Médio",
    "sr_low":      "Baixo",
}
CAT_NEG_PT = {
    "errors":          "Erros",
    "contrast_errors": "Contraste",
    "alerts":          "Alertas",
}
CAT_POS_PT = {
    "features":  "Funcionalidades",
    "structure": "Estrutura",
    "aria":      "ARIA",
}

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "axes.grid.axis":    "x",
    "grid.color":        "#e2e8f0",
    "grid.linewidth":    0.6,
})

DPI = 150


def aim_color(score):
    if score is None: return "#94a3b8"
    if score < 5:     return "#ef4444"
    if score < 7:     return "#f97316"
    if score < 8.5:   return "#eab308"
    return "#22c55e"


def flow_label(name: str) -> str:
    """Split CamelCase but keep consecutive uppercase (acronyms) together."""
    # Insert space between lowercase→uppercase transitions only
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", name).strip()


def page_name(filename: str) -> str:
    """Strip numeric prefix and split camelCase into readable words."""
    name = re.sub(r"\.html?$", "", filename, flags=re.IGNORECASE)
    # Remove leading digit-dash prefix (e.g. "1-")
    name = re.sub(r"^\d+-", "", name)
    # Split camelCase
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return name.strip()


def tex_escape(s: str) -> str:
    for char, escaped in [
        ("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
        ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
        ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
    ]:
        s = s.replace(char, escaped)
    return s


# ─── Data loading ─────────────────────────────────────────────────────────────

def load_flows() -> list[dict]:
    flows = []
    for d in sorted(OUTPUT_DIR.iterdir()):
        if not d.is_dir(): continue
        rp = d / "wave-report.json"
        if not rp.exists(): continue
        flows.append({"name": d.name, "pages": json.loads(rp.read_text())})
    return flows


def build_summary_df(flows: list[dict]) -> pd.DataFrame:
    rows = []
    for flow in flows:
        for page in flow["pages"]:
            s  = page["summary"]
            pb = s.get("pour_breakdown") or {}
            sr = s.get("sr_relevance_breakdown") or {}
            errors   = s.get("errors", 0)
            contrast = s.get("contrast_errors", 0)
            alerts   = s.get("alerts", 0)
            features = s.get("features", 0)
            structure= s.get("structure", 0)
            aria     = s.get("aria", 0)
            total_neg = errors + contrast + alerts
            total_pos = features + structure + aria
            total_all = total_neg + total_pos
            rows.append({
                "flow":       flow["name"],
                "flow_label": flow_label(flow["name"]),
                "source_file":page["source_file"],
                "page":       page_name(page["source_file"]),
                "aim_score":  s.get("aim_score"),
                "errors":     errors,
                "contrast_errors": contrast,
                "alerts":     alerts,
                "features":   features,
                "structure":  structure,
                "aria":       aria,
                "total_neg":  total_neg,
                "total_pos":  total_pos,
                "total_elements": total_all,
                # issues per 100 total elements (normalised rate)
                "issue_rate": round(total_neg / total_all * 100, 1) if total_all else 0,
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
                        "flow":          flow["name"],
                        "flow_label":    flow_label(flow["name"]),
                        "page":          page_name(page["source_file"]),
                        "category":      cat["category"],
                        "type_id":       t["type_id"],
                        "type_label":    t["type_label"],
                        "count":         t.get("count", 0),
                        "wcag_criteria": ", ".join(t["wcag_criteria"]) if t.get("wcag_criteria") else "",
                        "wcag_level":    t.get("wcag_level") or "",
                        "pour_dimensions": ", ".join(t["pour_dimensions"]) if t.get("pour_dimensions") else "",
                        "sr_relevance":  t.get("sr_relevance") or "",
                    })
    return pd.DataFrame(rows)


# ─── Figure helpers ───────────────────────────────────────────────────────────

def save_fig(fig, name: str) -> str:
    path = FIGURES_DIR / f"{name}.pdf"
    fig.savefig(path, bbox_inches="tight", dpi=DPI)
    plt.close(fig)
    print(f"  Figure: {path.name}")
    return path.name


def _hbar_stacked(ax, pages, data_dict, title, xlabel="Ocorrências"):
    """Horizontal stacked bar. data_dict = {col: (label, color, values)}"""
    y   = np.arange(len(pages))
    left= np.zeros(len(pages))
    patches = []
    for label, color, vals in data_dict:
        vals = np.array(vals, dtype=float)
        ax.barh(y, vals, left=left, color=color, height=0.55, label=label)
        patches.append(mpatches.Patch(color=color, label=label))
        left += vals
    ax.set_yticks(y)
    ax.set_yticklabels(pages, fontsize=8.5)
    ax.set_xlabel(xlabel, fontsize=8)
    ax.set_title(title, fontsize=10, fontweight="bold", pad=6)
    ax.invert_yaxis()
    ax.legend(handles=patches, fontsize=7.5, loc="lower right", framealpha=0.8)
    ax.grid(True, axis="x", color="#e2e8f0", linewidth=0.6)
    ax.set_axisbelow(True)


def _vbar_stacked(ax, pages, data_dict, title, ylabel=""):
    """Vertical stacked bar. data_dict = [(label, color, values)]"""
    x      = np.arange(len(pages))
    bottom = np.zeros(len(pages))
    patches = []
    for label, color, vals in data_dict:
        vals = np.array(vals, dtype=float)
        ax.bar(x, vals, bottom=bottom, color=color, width=0.55, label=label)
        patches.append(mpatches.Patch(color=color, label=label))
        bottom += vals
    ax.set_xticks(x)
    ax.set_xticklabels(pages, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
    ax.legend(handles=patches, fontsize=7.5, framealpha=0.8)
    ax.grid(True, axis="y", color="#e2e8f0", linewidth=0.6)
    ax.set_axisbelow(True)


# ─── Overview figures ─────────────────────────────────────────────────────────

def fig_aim_all(df: pd.DataFrame) -> str:
    """AIM scores for all pages, annotated with total element count."""
    labels = (df["flow_label"] + "\n" + df["page"]).tolist()
    scores = df["aim_score"].tolist()
    totals = df["total_elements"].tolist()
    colors = [aim_color(s) for s in scores]

    fig, ax = plt.subplots(figsize=(11, max(4.5, len(df) * 0.5)))
    y    = np.arange(len(labels))
    bars = ax.barh(y, scores, color=colors, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlim(0, 12.5)
    ax.set_xlabel("AIM Score (0–10)", fontsize=9)
    ax.set_title("Pontuação AIM por Página", fontsize=13, fontweight="bold", pad=10)
    ax.invert_yaxis()

    # Threshold lines
    for xv, col in [(5, "#ef4444"), (7, "#f97316"), (8.5, "#eab308")]:
        ax.axvline(x=xv, color=col, linestyle="--", linewidth=0.9, alpha=0.45)

    # Annotate score + element count
    for bar, score, n in zip(bars, scores, totals):
        if score is not None:
            ax.text(score + 0.15, bar.get_y() + bar.get_height() / 2,
                    f"{score}  (n={n})",
                    va="center", fontsize=7.5, color="#1e293b")

    # Separator lines between flows
    prev_flow = None
    for i, row in enumerate(df.itertuples()):
        if prev_flow and row.flow != prev_flow:
            ax.axhline(y=i - 0.5, color="#cbd5e1", linewidth=1.2, linestyle="-")
        prev_flow = row.flow

    legend_patches = [
        mpatches.Patch(color="#ef4444", label="< 5"),
        mpatches.Patch(color="#f97316", label="5–7"),
        mpatches.Patch(color="#eab308", label="7–8.5"),
        mpatches.Patch(color="#22c55e", label="≥ 8.5"),
    ]
    ax.legend(handles=legend_patches, title="AIM", fontsize=8, loc="lower right")
    ax.grid(True, axis="x", color="#e2e8f0", linewidth=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    return save_fig(fig, "aim_all_pages")


def fig_issues_overview(df: pd.DataFrame) -> str:
    """Side-by-side: negative issues | SR impact — all pages."""
    pages  = df["page"].tolist()
    n_pages = len(pages)
    height  = max(5, n_pages * 0.48)

    fig, axes = plt.subplots(1, 2, figsize=(15, height))
    fig.suptitle("Visão Geral dos Problemas — Todas as Páginas",
                 fontsize=12, fontweight="bold", y=1.01)

    _hbar_stacked(axes[0], pages, [
        ("Erros",     CAT_COLORS["errors"],          df["errors"]),
        ("Contraste", CAT_COLORS["contrast_errors"],  df["contrast_errors"]),
        ("Alertas",   CAT_COLORS["alerts"],           df["alerts"]),
    ], "Problemas por Tipo")

    _hbar_stacked(axes[1], pages, [
        ("Crítico", SR_COLORS["sr_critical"], df["sr_critical"]),
        ("Alto",    SR_COLORS["sr_high"],     df["sr_high"]),
        ("Médio",   SR_COLORS["sr_medium"],   df["sr_medium"]),
        ("Baixo",   SR_COLORS["sr_low"],      df["sr_low"]),
    ], "Impacto no Leitor de Tela")

    # Flow separators on both axes
    prev_flow = None
    for i, row in enumerate(df.itertuples()):
        if prev_flow and row.flow != prev_flow:
            for ax in axes:
                ax.axhline(y=i - 0.5, color="#cbd5e1", linewidth=1.1)
        prev_flow = row.flow

    fig.tight_layout()
    return save_fig(fig, "issues_overview")


def fig_pour_all(df: pd.DataFrame) -> str:
    pages   = df["page"].tolist()
    height  = max(4.5, len(pages) * 0.48)
    fig, ax = plt.subplots(figsize=(11, height))
    _hbar_stacked(ax, pages, [
        (v, POUR_COLORS[k], df[k]) for k, v in POUR_PT.items()
    ], "Distribuição POUR — Todas as Páginas")

    prev_flow = None
    for i, row in enumerate(df.itertuples()):
        if prev_flow and row.flow != prev_flow:
            ax.axhline(y=i - 0.5, color="#cbd5e1", linewidth=1.1)
        prev_flow = row.flow

    fig.tight_layout()
    return save_fig(fig, "pour_all_pages")


def fig_elements_all(df: pd.DataFrame) -> str:
    """Total element composition per page (shows relative page size)."""
    pages  = df["page"].tolist()
    height = max(4.5, len(pages) * 0.48)
    fig, ax = plt.subplots(figsize=(11, height))
    _hbar_stacked(ax, pages, [
        ("Erros",            CAT_COLORS["errors"],          df["errors"]),
        ("Contraste",        CAT_COLORS["contrast_errors"],  df["contrast_errors"]),
        ("Alertas",          CAT_COLORS["alerts"],           df["alerts"]),
        ("Funcionalidades",  CAT_COLORS["features"],         df["features"]),
        ("Estrutura",        CAT_COLORS["structure"],        df["structure"]),
        ("ARIA",             CAT_COLORS["aria"],             df["aria"]),
    ], "Composição de Elementos por Página  (tamanho = total de componentes detectados)")

    # Annotate total count and issue rate
    for i, row in enumerate(df.itertuples()):
        ax.text(row.total_elements + 2, i,
                f"n={row.total_elements}  ({row.issue_rate}% problemas)",
                va="center", fontsize=7.5, color="#475569")

    prev_flow = None
    for i, row in enumerate(df.itertuples()):
        if prev_flow and row.flow != prev_flow:
            ax.axhline(y=i - 0.5, color="#cbd5e1", linewidth=1.1)
        prev_flow = row.flow

    ax.set_xlim(right=df["total_elements"].max() * 1.25)
    fig.tight_layout()
    return save_fig(fig, "elements_all_pages")


def fig_top_issues(issues_df: pd.DataFrame, n: int = 15) -> str:
    neg = issues_df[issues_df["category"].isin(["error", "contrast", "alert"])]
    top = (
        neg.groupby(["type_id", "type_label", "category"])["count"]
        .sum().reset_index()
        .sort_values("count", ascending=False)
        .head(n)
    )
    color_map = {"error": CAT_COLORS["errors"], "contrast": CAT_COLORS["contrast_errors"],
                 "alert": CAT_COLORS["alerts"]}
    colors = top["category"].map(color_map).tolist()

    fig, ax = plt.subplots(figsize=(10, max(4.5, n * 0.42)))
    y    = np.arange(len(top))
    bars = ax.barh(y, top["count"], color=colors, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(top["type_label"], fontsize=9)
    ax.set_xlabel("Total de ocorrências", fontsize=9)
    ax.set_title(f"Principais {n} Problemas de Acessibilidade", fontsize=12, fontweight="bold", pad=10)
    ax.invert_yaxis()

    for bar, val in zip(bars, top["count"]):
        ax.text(bar.get_width() + 0.4, bar.get_y() + bar.get_height() / 2,
                str(int(val)), va="center", fontsize=8.5, fontweight="bold")

    patches = [
        mpatches.Patch(color=CAT_COLORS["errors"],          label="Erro"),
        mpatches.Patch(color=CAT_COLORS["contrast_errors"], label="Contraste"),
        mpatches.Patch(color=CAT_COLORS["alerts"],          label="Alerta"),
    ]
    ax.legend(handles=patches, fontsize=8, loc="lower right")
    ax.set_xlim(right=top["count"].max() * 1.2)
    ax.grid(True, axis="x", color="#e2e8f0", linewidth=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    return save_fig(fig, "top_issues")


# ─── Per-flow figures ─────────────────────────────────────────────────────────

def fig_flow_summary(df: pd.DataFrame, flow_name: str) -> str:
    slug   = re.sub(r"\s+", "_", flow_name).lower()
    pages  = df["page"].tolist()
    n      = len(pages)
    x      = np.arange(n)
    w      = 0.55

    fig, axes = plt.subplots(3, 2, figsize=(13, 13))
    fig.suptitle(f"Fluxo: {flow_name}", fontsize=13, fontweight="bold")

    # ── AIM Score ─────────────────────────────────────────────────────────────
    ax = axes[0, 0]
    colors = [aim_color(s) for s in df["aim_score"]]
    bars   = ax.bar(x, df["aim_score"], color=colors, width=w)
    ax.set_xticks(x); ax.set_xticklabels(pages, rotation=45, ha="right", fontsize=8)
    ax.set_ylim(0, 11); ax.set_ylabel("AIM Score"); ax.set_title("Pontuação AIM", fontweight="bold")
    ax.axhline(8.5, color="#eab308", linestyle="--", linewidth=0.8, alpha=0.6)
    for bar, score in zip(bars, df["aim_score"]):
        if score is not None:
            ax.text(bar.get_x() + bar.get_width() / 2, score + 0.15,
                    str(score), ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax.grid(True, axis="y", color="#e2e8f0", linewidth=0.6); ax.set_axisbelow(True)

    # ── Negative issues stacked ───────────────────────────────────────────────
    _vbar_stacked(axes[0, 1], pages, [
        ("Erros",     CAT_COLORS["errors"],          df["errors"]),
        ("Contraste", CAT_COLORS["contrast_errors"],  df["contrast_errors"]),
        ("Alertas",   CAT_COLORS["alerts"],           df["alerts"]),
    ], "Erros e Alertas")

    # ── Positive elements stacked ─────────────────────────────────────────────
    ax = axes[1, 0]
    _vbar_stacked(ax, pages, [
        ("Funcionalidades", CAT_COLORS["features"],  df["features"]),
        ("Estrutura",       CAT_COLORS["structure"],  df["structure"]),
        ("ARIA",            CAT_COLORS["aria"],       df["aria"]),
    ], "Boas Práticas (indicadores de riqueza da página)")
    # Annotate total positive — inside top of bar to avoid overflow
    bottom_pos = df["features"].values + df["structure"].values + df["aria"].values
    for i, tot in enumerate(bottom_pos):
        y_text = tot * 0.97 if tot > 15 else tot + 1
        color_text = "white" if tot > 15 else "#475569"
        axes[1, 0].text(i, y_text, f"n={int(tot)}", ha="center", va="top",
                        fontsize=7.5, color=color_text, fontweight="bold")

    # ── POUR breakdown ────────────────────────────────────────────────────────
    _vbar_stacked(axes[1, 1], pages, [
        (v, POUR_COLORS[k], df[k]) for k, v in POUR_PT.items()
    ], "Dimensões POUR")

    # ── SR relevance ──────────────────────────────────────────────────────────
    _vbar_stacked(axes[2, 0], pages, [
        (v, SR_COLORS[k], df[k]) for k, v in SR_PT.items()
    ], "Impacto no Leitor de Tela")

    # ── Issue rate (normalised) ───────────────────────────────────────────────
    ax = axes[2, 1]
    bar_colors = [aim_color(s) for s in df["aim_score"]]
    bars = ax.bar(x, df["issue_rate"], color=bar_colors, width=w, alpha=0.85)
    ax.set_xticks(x); ax.set_xticklabels(pages, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("% de elementos")
    ax.set_title("Taxa de Problemas (% sobre total de elementos)", fontweight="bold", fontsize=9, pad=8)
    max_rate = df["issue_rate"].max()
    ax.set_ylim(0, max_rate * 1.35)  # headroom so annotations don't clip into title
    for bar, val, tot in zip(bars, df["issue_rate"], df["total_elements"]):
        cx = bar.get_x() + bar.get_width() / 2
        h  = bar.get_height()
        # put label inside if bar is tall enough, outside if short
        if h > max_rate * 0.25:
            ax.text(cx, h * 0.5, f"{val}%\nn={int(tot)}", ha="center", va="center",
                    fontsize=7.5, color="white", fontweight="bold")
        else:
            ax.text(cx, h + max_rate * 0.02, f"{val}%  n={int(tot)}", ha="center", va="bottom", fontsize=7.5)
    ax.grid(True, axis="y", color="#e2e8f0", linewidth=0.6); ax.set_axisbelow(True)

    fig.tight_layout(pad=2.0)
    return save_fig(fig, f"flow_{slug}")


# ─── Table builders ───────────────────────────────────────────────────────────

def df_to_latex(df: pd.DataFrame, label: str, caption: str,
                col_format: str = None, index: bool = False) -> str:
    n_cols = len(df.columns) + (1 if index else 0)
    fmt = col_format or ("l" + "r" * (n_cols - 1))

    escaped = df.copy()
    for col in escaped.select_dtypes(include="str").columns:
        escaped[col] = escaped[col].apply(
            lambda x: tex_escape(str(x)) if pd.notna(x) else "---"
        )

    body = escaped.to_latex(index=index, escape=False, column_format=fmt, na_rep="---")
    # Replace default \toprule etc with booktabs-style (already there via pandas)
    return (
        "\\begin{table}[htbp]\n"
        "  \\centering\n"
        f"  \\caption{{{tex_escape(caption)}}}\n"
        f"  \\label{{{label}}}\n"
        "  \\small\n"
        f"  {body.strip()}\n"
        "\\end{table}\n"
    )


def table_summary_all(df: pd.DataFrame) -> str:
    display = df[["flow_label", "page", "aim_score", "total_elements",
                  "errors", "contrast_errors", "alerts", "issue_rate",
                  "sr_critical", "sr_high"]].copy()
    display.columns = ["Fluxo", "Página", "AIM", "Elem.", "Erros",
                       "Contraste", "Alertas", "\\% prob.", "LS Crít.", "LS Alto"]
    return df_to_latex(display, "tab:summary_all",
                       "Resumo de acessibilidade — todas as páginas",
                       col_format="llcrrrrrr r")


def table_flow_summary(df: pd.DataFrame, fname: str) -> str:
    slug = re.sub(r"\s+", "_", fname).lower()
    display = df[["page", "aim_score", "total_elements", "issue_rate",
                  "errors", "contrast_errors", "alerts",
                  "features", "structure", "aria",
                  "sr_critical", "sr_medium"]].copy()
    display.columns = ["Página", "AIM", "Elem.", "\\% prob.", "Erros",
                       "Contraste", "Alertas", "Func.", "Estrutura",
                       "ARIA", "LS Crít.", "LS Méd."]
    return df_to_latex(display, f"tab:flow_{slug}",
                       f"Métricas por página — {fname}",
                       col_format="lcrrrrrrrrrr")


def table_top_issues(issues_df: pd.DataFrame, n: int = 15) -> str:
    neg = issues_df[issues_df["category"].isin(["error", "contrast", "alert"])]
    agg = (
        neg.groupby(["type_label", "category", "wcag_criteria",
                     "wcag_level", "pour_dimensions", "sr_relevance"])
        .agg(total=("count", "sum"), pages=("page", "nunique"))
        .reset_index()
        .sort_values("total", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
    agg.index += 1

    cat_map = {"error": "Erro", "contrast": "Contraste", "alert": "Alerta"}
    sr_map  = {"critical": "Crítico", "high": "Alto", "medium": "Médio",
               "low": "Baixo", "": "---"}

    display = agg[["type_label", "category", "total", "pages",
                   "wcag_criteria", "wcag_level", "pour_dimensions", "sr_relevance"]].copy()
    display["category"]      = display["category"].map(cat_map)
    display["sr_relevance"]  = display["sr_relevance"].map(lambda x: sr_map.get(x, x))
    display["wcag_criteria"] = display["wcag_criteria"].replace("", "---")
    display["pour_dimensions"] = display["pour_dimensions"].replace("", "---")
    display.columns = ["Problema", "Tipo", "Total", "Pág.", "WCAG", "Nível", "POUR", "Imp. LS"]
    return df_to_latex(display, "tab:top_issues",
                       f"Principais {n} problemas de acessibilidade — todos os fluxos",
                       col_format="lcrrcclc", index=True)


# ─── Main .tex ────────────────────────────────────────────────────────────────

def build_main_tex(flows: list[dict]) -> str:
    flow_sections = ""
    for flow in flows:
        name  = flow["name"]
        label = flow_label(name)
        slug  = re.sub(r"\s+", "_", label).lower()
        flow_sections += f"""
\\subsection{{{tex_escape(label)}}}

\\input{{tables/table_flow_{slug}}}

\\begin{{figure}}[htbp]
  \\centering
  \\includegraphics[width=\\linewidth]{{figures/flow_{slug}}}
  \\caption{{Métricas de acessibilidade — {tex_escape(label)}}}
  \\label{{fig:flow_{slug}}}
\\end{{figure}}

"""

    return r"""\documentclass[12pt,a4paper]{article}

\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[portuguese]{babel}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{array}
\usepackage{float}
\usepackage{hyperref}
\usepackage{geometry}
\geometry{margin=2.5cm}

\graphicspath{{figures/}}

\title{Relatório de Acessibilidade Web\\
       \large Análise WAVE --- Perspectiva do Leitor de Tela}
\author{}
\date{\today}

\begin{document}

\maketitle
\tableofcontents
\newpage

%% ─────────────────────────────────────────────────────────────
\section{Visão Geral}

\input{tables/table_summary_all}

\begin{figure}[htbp]
  \centering
  \includegraphics[width=\linewidth]{figures/aim_all_pages}
  \caption{Pontuação AIM por página (escala 0--10, maior é melhor).
           O valor \textbf{n} indica o total de componentes detectados pelo WAVE,
           usado como proxy do tamanho da página.
           Linhas tracejadas delimitam as faixas de qualidade em 5, 7 e 8{,}5.}
  \label{fig:aim_all}
\end{figure}

\begin{figure}[htbp]
  \centering
  \includegraphics[width=\linewidth]{figures/elements_all_pages}
  \caption{Composição de todos os elementos detectados por página.
           A proporção de elementos negativos (erros, contraste, alertas)
           sobre o total é indicada como \emph{\% prob.} e permite comparar
           páginas de tamanhos diferentes.}
  \label{fig:elements_all}
\end{figure}

\begin{figure}[htbp]
  \centering
  \includegraphics[width=\linewidth]{figures/issues_overview}
  \caption{Visão geral dos problemas: tipos de erro (esquerda) e
           impacto para usuários de leitores de tela (direita).}
  \label{fig:issues_overview}
\end{figure}

\begin{figure}[htbp]
  \centering
  \includegraphics[width=\linewidth]{figures/pour_all_pages}
  \caption{Distribuição dos problemas pelas quatro dimensões WCAG (POUR).}
  \label{fig:pour_all}
\end{figure}

%% ─────────────────────────────────────────────────────────────
\section{Análise por Fluxo}

""" + flow_sections + r"""
%% ─────────────────────────────────────────────────────────────
\section{Principais Problemas de Acessibilidade}

\input{tables/table_top_issues}

\begin{figure}[htbp]
  \centering
  \includegraphics[width=\linewidth]{figures/top_issues}
  \caption{Principais 15 problemas de acessibilidade por número total de
           ocorrências em todos os fluxos.}
  \label{fig:top_issues}
\end{figure}

\end{document}
"""


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    flows = load_flows()
    if not flows:
        print(f"Nenhum wave-report.json encontrado em {OUTPUT_DIR}")
        raise SystemExit(1)

    print(f"Carregando {len(flows)} fluxo(s)...")
    for f in flows:
        print(f"  • {f['name']}: {len(f['pages'])} página(s)")

    summary_df = build_summary_df(flows)
    issues_df  = build_issues_df(flows)

    print("\nGerando figuras...")
    fig_aim_all(summary_df)
    fig_issues_overview(summary_df)
    fig_pour_all(summary_df)
    fig_elements_all(summary_df)
    fig_top_issues(issues_df)

    for flow in flows:
        fdf   = summary_df[summary_df["flow"] == flow["name"]].copy()
        label = flow_label(flow["name"])
        fig_flow_summary(fdf, label)

    print("\nGerando tabelas...")
    (TABLES_DIR / "table_summary_all.tex").write_text(table_summary_all(summary_df), encoding="utf-8")
    print("  Table: table_summary_all.tex")

    (TABLES_DIR / "table_top_issues.tex").write_text(table_top_issues(issues_df), encoding="utf-8")
    print("  Table: table_top_issues.tex")

    for flow in flows:
        fdf   = summary_df[summary_df["flow"] == flow["name"]].copy()
        label = flow_label(flow["name"])
        slug  = re.sub(r"\s+", "_", label).lower()
        fname = TABLES_DIR / f"table_flow_{slug}.tex"
        fname.write_text(table_flow_summary(fdf, label), encoding="utf-8")
        print(f"  Table: {fname.name}")

    print("\nGerando main.tex...")
    (LATEX_DIR / "main.tex").write_text(build_main_tex(flows), encoding="utf-8")
    print(f"  output/latex/main.tex")

    print(f"""
Concluído. Para compilar:
  cd output/latex
  pdflatex main.tex && pdflatex main.tex
""")
