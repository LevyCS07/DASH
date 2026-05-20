import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime, time

st.set_page_config(
    page_title="Monitor de Rotas",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Estilo ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] { font-family: 'Sora', sans-serif; }

    .main-header {
        font-size: 1.9rem; font-weight: 700; color: #0f172a;
        border-bottom: 3px solid #f59e0b; padding-bottom: 10px; margin-bottom: 20px;
        letter-spacing: -0.5px;
    }
    .section-title {
        font-size: 1rem; font-weight: 600; color: #475569;
        text-transform: uppercase; letter-spacing: 1px;
        margin: 20px 0 10px;
    }
    .badge-late {
        background: #fef2f2; border: 1px solid #fca5a5;
        color: #dc2626; border-radius: 6px; padding: 2px 10px;
        font-size: 0.78rem; font-weight: 600; font-family: 'JetBrains Mono', monospace;
    }
    .badge-ok {
        background: #f0fdf4; border: 1px solid #86efac;
        color: #16a34a; border-radius: 6px; padding: 2px 10px;
        font-size: 0.78rem; font-weight: 600; font-family: 'JetBrains Mono', monospace;
    }
    .kpi-box {
        background: #f8fafc; border-radius: 12px;
        border: 1px solid #e2e8f0; padding: 18px 22px;
        border-top: 4px solid #f59e0b;
    }
    .kpi-value { font-size: 2rem; font-weight: 700; color: #0f172a; }
    .kpi-label { font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.8px; }
    [data-testid="stSidebar"] { background: #0f172a; }
    [data-testid="stSidebar"] * { color: #cbd5e1 !important; }
    [data-testid="stSidebar"] h3 { color: #f59e0b !important; }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stMultiselect label { color: #94a3b8 !important; }
    div[data-testid="stTab"] button[aria-selected="true"] {
        color: #f59e0b !important;
        border-bottom-color: #f59e0b !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def detect_column_types(df):
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    date_cols    = df.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
    cat_cols     = df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()
    return numeric_cols, date_cols, cat_cols


def try_parse_dates(df):
    for col in df.select_dtypes(include="object").columns:
        try:
            parsed = pd.to_datetime(df[col], infer_datetime_format=True, errors="coerce")
            if parsed.notna().mean() > 0.7:
                df[col] = parsed
        except Exception:
            pass
    return df


def parse_time_col(series):
    """Tenta converter coluna para datetime, aceitando vários formatos."""
    result = pd.to_datetime(series, errors="coerce", infer_datetime_format=True)
    if result.isna().all():
        result = pd.to_datetime(series, format="%H:%M", errors="coerce")
    return result


def safe_fig(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=40, b=20),
        font=dict(family="Sora, sans-serif"),
    )
    return fig


def minutos_atraso(real, limite):
    """Calcula minutos de atraso entre dois datetime/time. Retorna float (negativo = adiantado)."""
    try:
        delta = real - limite
        return delta.total_seconds() / 60
    except Exception:
        return None


# ── Upload ────────────────────────────────────────────────────────────────────
st.markdown('<div class="main-header">🚌 Monitor de Rotas</div>', unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Faça upload do arquivo Excel (.xlsx / .xls)",
    type=["xlsx", "xls"],
    help="Colunas esperadas: ID da Viagem, Rota, Direção, Turno, Chegada, Motorista, Data…",
)

if not uploaded:
    st.info("⬆️ Envie o arquivo Excel de viagens para começar.")
    st.stop()

# ── Leitura ───────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Lendo arquivo…")
def load_data(file_bytes, sheet_name):
    df = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name)
    df = try_parse_dates(df)
    return df

file_bytes  = uploaded.read()
xls         = pd.ExcelFile(BytesIO(file_bytes))
sheet_names = xls.sheet_names

with st.sidebar:
    st.markdown("### ⚙️ Configurações")
    sheet = st.selectbox("Planilha", sheet_names)

df_raw = load_data(file_bytes, sheet)
numeric_cols, date_cols, cat_cols = detect_column_types(df_raw)

# ── Sidebar – Filtros Gerais ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🔍 Filtros")

    df_filtered = df_raw.copy()

    for col in cat_cols[:4]:
        unique_vals = sorted(df_raw[col].dropna().unique().tolist())
        if 1 < len(unique_vals) <= 60:
            sel = st.multiselect(col, unique_vals, default=unique_vals)
            df_filtered = df_filtered[df_filtered[col].isin(sel)]

    for col in numeric_cols[:2]:
        col_min = float(df_raw[col].min())
        col_max = float(df_raw[col].max())
        if col_min < col_max:
            rng = st.slider(col, col_min, col_max, (col_min, col_max))
            df_filtered = df_filtered[df_filtered[col].between(*rng)]

    for col in date_cols[:1]:
        d_min = df_raw[col].min().date()
        d_max = df_raw[col].max().date()
        d_range = st.date_input(f"Período — {col}", value=(d_min, d_max))
        if len(d_range) == 2:
            df_filtered = df_filtered[
                df_filtered[col].dt.date.between(d_range[0], d_range[1])
            ]

    st.markdown("---")
    st.caption(f"**{len(df_filtered):,}** de **{len(df_raw):,}** linhas")

# ── Tabs principais ───────────────────────────────────────────────────────────
tab_entradas, tab_overview, tab_charts, tab_time, tab_data = st.tabs([
    "🚦 Verificar Entradas",
    "🗂️ Visão Geral",
    "📈 Gráficos",
    "📅 Séries Temporais",
    "📋 Dados",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB: VERIFICAR ENTRADAS  (rotas com Direção == "Ida")
# ══════════════════════════════════════════════════════════════════════════════
with tab_entradas:

    st.markdown("### 🚦 Monitoramento de Entradas — Rotas com Direção **Ida**")

    # Validações de colunas
    col_dir    = "Direção"
    col_rota   = "Rota"
    col_cheg   = "Chegada"
    col_data   = "Data"

    missing_cols = [c for c in [col_dir, col_rota, col_cheg] if c not in df_raw.columns]
    if missing_cols:
        st.error(f"Colunas não encontradas no arquivo: **{', '.join(missing_cols)}**. "
                 f"Verifique os nomes das colunas.")
        st.stop()

    # ── Filtrar apenas Ida ────────────────────────────────────────────────────
    df_ida = df_filtered[
        df_filtered[col_dir].astype(str).str.strip().str.lower() == "ida"
    ].copy()

    if df_ida.empty:
        st.warning("Nenhuma viagem com Direção = 'Ida' encontrada após os filtros aplicados.")
        st.stop()

    # ── Pesquisa de Rota ──────────────────────────────────────────────────────
    rotas_disp = sorted(df_ida[col_rota].dropna().unique().tolist())

    col_search, col_mode = st.columns([3, 1])
    with col_search:
        rota_sel = st.selectbox(
            "🔎 Pesquisar Rota",
            options=["Todas as rotas"] + rotas_disp,
            help="Selecione uma rota específica ou deixe 'Todas as rotas' para ver o resumo geral.",
        )
    with col_mode:
        horario_ref = st.time_input(
            "⏰ Horário-limite de chegada",
            value=time(8, 0),
            help="Viagens com chegada após este horário serão consideradas atrasadas.",
        )

    if rota_sel != "Todas as rotas":
        df_ida = df_ida[df_ida[col_rota] == rota_sel]

    # ── Processar coluna Chegada ──────────────────────────────────────────────
    df_ida = df_ida.copy()
    df_ida["_chegada_dt"] = parse_time_col(df_ida[col_cheg])

    # Referência datetime: usa a data da linha se disponível
    if col_data in df_ida.columns:
        df_ida["_data_dt"] = pd.to_datetime(df_ida[col_data], errors="coerce")
        df_ida["_limite_dt"] = df_ida["_data_dt"].apply(
            lambda d: datetime.combine(d.date(), horario_ref) if pd.notna(d) else pd.NaT
        )
        df_ida["_chegada_full"] = df_ida.apply(
            lambda r: datetime.combine(r["_data_dt"].date(), r["_chegada_dt"].time())
            if pd.notna(r["_chegada_dt"]) and pd.notna(r["_data_dt"]) else pd.NaT,
            axis=1,
        )
    else:
        hoje = datetime.today().date()
        df_ida["_limite_dt"]   = datetime.combine(hoje, horario_ref)
        df_ida["_chegada_full"] = df_ida["_chegada_dt"]

    df_ida["_minutos_atraso"] = (
        df_ida["_chegada_full"] - df_ida["_limite_dt"]
    ).dt.total_seconds() / 60

    df_ida["_status"] = df_ida["_minutos_atraso"].apply(
        lambda m: "Atrasado" if pd.notna(m) and m > 0 else (
            "No prazo" if pd.notna(m) else "Sem dado"
        )
    )

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total     = len(df_ida)
    atrasados = (df_ida["_status"] == "Atrasado").sum()
    no_prazo  = (df_ida["_status"] == "No prazo").sum()
    sem_dado  = (df_ida["_status"] == "Sem dado").sum()
    pct_atraso = (atrasados / total * 100) if total else 0
    media_min  = df_ida.loc[df_ida["_minutos_atraso"] > 0, "_minutos_atraso"].mean()

    k1, k2, k3, k4, k5 = st.columns(5)
    kpis = [
        (k1, str(total),            "Total de Entradas",        "#3b82f6"),
        (k2, str(atrasados),        "Atrasadas 🔴",             "#ef4444"),
        (k3, str(no_prazo),         "No Prazo 🟢",              "#22c55e"),
        (k4, f"{pct_atraso:.1f}%",  "% Atraso",                 "#f59e0b"),
        (k5, f"{media_min:.0f} min" if pd.notna(media_min) else "—",
             "Atraso Médio",         "#8b5cf6"),
    ]
    for col, val, label, cor in kpis:
        with col:
            st.markdown(
                f'<div class="kpi-box" style="border-top-color:{cor}">'
                f'<div class="kpi-value" style="color:{cor}">{val}</div>'
                f'<div class="kpi-label">{label}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Gráfico principal ─────────────────────────────────────────────────────
    df_plot = df_ida[df_ida["_minutos_atraso"].notna()].copy()

    if df_plot.empty:
        st.info("Sem dados suficientes para gerar o gráfico (coluna Chegada não reconhecida).")
    else:
        g1, g2 = st.columns([2, 1])

        with g1:
            label_x = col_rota if rota_sel == "Todas as rotas" else (
                "Data" if col_data in df_plot.columns else "ID da Viagem"
            )
            x_axis = col_rota if rota_sel == "Todas as rotas" else (
                col_data if col_data in df_plot.columns else "ID da Viagem"
            )

            # Agrega por rota se "Todas"
            if rota_sel == "Todas as rotas":
                agg = (
                    df_plot.groupby(col_rota)
                    .agg(
                        total=(col_rota, "count"),
                        atrasados=("_status", lambda s: (s == "Atrasado").sum()),
                        atraso_medio=("_minutos_atraso", lambda m: m[m > 0].mean()),
                    )
                    .reset_index()
                )
                agg["pct"] = (agg["atrasados"] / agg["total"] * 100).round(1)
                fig_bar = px.bar(
                    agg.sort_values("atrasados", ascending=False),
                    x=col_rota, y="atrasados",
                    color="pct",
                    color_continuous_scale=["#bbf7d0", "#fef08a", "#fca5a5", "#dc2626"],
                    labels={"atrasados": "Viagens Atrasadas", "pct": "% Atraso"},
                    title="Viagens Atrasadas por Rota",
                    text="atrasados",
                )
                fig_bar.update_traces(textposition="outside")
            else:
                # Gráfico de timeline por viagem
                df_plot_s = df_plot.sort_values("_chegada_full")
                fig_bar = px.bar(
                    df_plot_s,
                    x=x_axis,
                    y="_minutos_atraso",
                    color="_status",
                    color_discrete_map={"Atrasado": "#ef4444", "No prazo": "#22c55e"},
                    labels={"_minutos_atraso": "Minutos em relação ao limite", x_axis: label_x},
                    title=f"Minutos em relação ao horário-limite — Rota {rota_sel}",
                    hover_data={col_cheg: True, "_status": True, "_minutos_atraso": ":.1f"},
                )
                fig_bar.add_hline(y=0, line_dash="dash", line_color="#f59e0b",
                                  annotation_text="Limite", annotation_position="top right")

            st.plotly_chart(safe_fig(fig_bar), use_container_width=True)

        with g2:
            pizza_data = df_ida["_status"].value_counts().reset_index()
            pizza_data.columns = ["Status", "Qtd"]
            fig_pie = px.pie(
                pizza_data, names="Status", values="Qtd",
                color="Status",
                color_discrete_map={
                    "Atrasado": "#ef4444",
                    "No prazo": "#22c55e",
                    "Sem dado": "#94a3b8",
                },
                title="Distribuição de Status",
                hole=0.45,
            )
            fig_pie.update_traces(textinfo="percent+label")
            st.plotly_chart(safe_fig(fig_pie), use_container_width=True)

        # ── Scatter: chegada real vs. limite ──────────────────────────────────
        if rota_sel != "Todas as rotas" and col_data in df_plot.columns:
            fig_sc = px.scatter(
                df_plot,
                x="_chegada_full",
                y="_minutos_atraso",
                color="_status",
                color_discrete_map={"Atrasado": "#ef4444", "No prazo": "#22c55e"},
                size=df_plot["_minutos_atraso"].abs().clip(1),
                labels={"_chegada_full": "Chegada Real", "_minutos_atraso": "Minutos de Atraso"},
                title="Dispersão: Chegada Real vs. Atraso",
                hover_data=["Motorista"] if "Motorista" in df_plot.columns else None,
            )
            fig_sc.add_hline(y=0, line_dash="dot", line_color="#f59e0b")
            st.plotly_chart(safe_fig(fig_sc), use_container_width=True)

    # ── Tabela detalhada ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📋 Detalhamento das Viagens</div>',
                unsafe_allow_html=True)

    cols_show = [c for c in [
        "ID da Viagem", col_rota, "Turno", "Motorista",
        col_data, col_cheg, "_minutos_atraso", "_status"
    ] if c in df_ida.columns]

    df_table = df_ida[cols_show].copy()
    df_table = df_table.rename(columns={
        "_minutos_atraso": "Δ min (atraso)",
        "_status": "Status",
    })
    df_table["Δ min (atraso)"] = df_table["Δ min (atraso)"].round(1)

    # Ordenar: atrasados primeiro
    df_table = df_table.sort_values("Δ min (atraso)", ascending=False)

    def color_status(val):
        if val == "Atrasado":
            return "background-color:#fef2f2; color:#dc2626; font-weight:600"
        elif val == "No prazo":
            return "background-color:#f0fdf4; color:#16a34a; font-weight:600"
        return ""

    st.dataframe(
        df_table.style.applymap(color_status, subset=["Status"]),
        use_container_width=True,
        height=380,
    )

    # Download
    out = BytesIO()
    df_table.to_excel(out, index=False)
    st.download_button(
        "⬇️ Exportar tabela de entradas (.xlsx)",
        data=out.getvalue(),
        file_name="entradas_verificadas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ══════════════════════════════════════════════════════════════════════════════
# TAB: VISÃO GERAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_overview:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="section-title">Tipos de Colunas</div>', unsafe_allow_html=True)
        type_df = pd.DataFrame({
            "Tipo": ["Numéricas", "Categóricas", "Datas"],
            "Qtd":  [len(numeric_cols), len(cat_cols), len(date_cols)],
        })
        fig = px.bar(type_df, x="Tipo", y="Qtd", color="Tipo",
                     color_discrete_sequence=["#3b82f6", "#22c55e", "#f59e0b"])
        st.plotly_chart(safe_fig(fig), use_container_width=True)

    with col2:
        st.markdown('<div class="section-title">Dados Ausentes (%)</div>', unsafe_allow_html=True)
        missing = (df_filtered.isnull().mean() * 100).reset_index()
        missing.columns = ["Coluna", "% Nulos"]
        missing = missing[missing["% Nulos"] > 0].sort_values("% Nulos", ascending=False).head(15)
        if missing.empty:
            st.success("✅ Nenhum valor ausente!")
        else:
            fig2 = px.bar(missing, x="% Nulos", y="Coluna", orientation="h",
                          color="% Nulos", color_continuous_scale="Reds")
            st.plotly_chart(safe_fig(fig2), use_container_width=True)

    st.markdown('<div class="section-title">Estatísticas Descritivas</div>', unsafe_allow_html=True)
    if numeric_cols:
        st.dataframe(df_filtered[numeric_cols].describe().T.style.format("{:.2f}"),
                     use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB: GRÁFICOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_charts:
    if not numeric_cols:
        st.warning("Nenhuma coluna numérica encontrada.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            y_col = st.selectbox("Eixo Y (métrica)", numeric_cols, key="y_col")
        with c2:
            x_col = st.selectbox("Eixo X / Agrupamento",
                                 cat_cols + numeric_cols + date_cols, key="x_col")

        chart_type = st.radio(
            "Tipo de gráfico",
            ["Barras", "Linha", "Dispersão", "Pizza", "Histograma", "Box"],
            horizontal=True,
        )
        color_col = st.selectbox("Cor (opcional)", ["— nenhuma —"] + cat_cols, key="color_col")
        color_arg = None if color_col == "— nenhuma —" else color_col
        palette   = px.colors.qualitative.Set2

        if chart_type == "Barras":
            fig = px.bar(df_filtered, x=x_col, y=y_col, color=color_arg,
                         color_discrete_sequence=palette, barmode="group")
        elif chart_type == "Linha":
            fig = px.line(df_filtered.sort_values(x_col), x=x_col, y=y_col,
                          color=color_arg, color_discrete_sequence=palette)
        elif chart_type == "Dispersão":
            fig = px.scatter(df_filtered, x=x_col, y=y_col, color=color_arg,
                             color_discrete_sequence=palette, opacity=0.7)
        elif chart_type == "Pizza":
            fig = px.pie(df_filtered, names=x_col, values=y_col,
                         color_discrete_sequence=palette)
        elif chart_type == "Histograma":
            fig = px.histogram(df_filtered, x=y_col, color=color_arg,
                               color_discrete_sequence=palette, nbins=30)
        else:
            fig = px.box(df_filtered, x=x_col if x_col in cat_cols else None,
                         y=y_col, color=color_arg, color_discrete_sequence=palette)

        st.plotly_chart(safe_fig(fig), use_container_width=True)

        if len(numeric_cols) >= 2:
            st.markdown('<div class="section-title">Mapa de Correlação</div>', unsafe_allow_html=True)
            corr = df_filtered[numeric_cols].corr()
            fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r",
                                 zmin=-1, zmax=1)
            st.plotly_chart(safe_fig(fig_corr), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB: SÉRIES TEMPORAIS
# ══════════════════════════════════════════════════════════════════════════════
with tab_time:
    if not date_cols:
        st.info("Nenhuma coluna de data detectada no arquivo.")
    else:
        dt_col  = st.selectbox("Coluna de data", date_cols, key="dt_col")
        val_col = st.selectbox("Valor", numeric_cols, key="val_col_ts")
        grp_col = st.selectbox("Agrupar por (opcional)", ["— nenhuma —"] + cat_cols, key="grp_ts")
        freq    = st.radio("Granularidade", ["Dia", "Semana", "Mês", "Trimestre", "Ano"],
                           horizontal=True)

        freq_map = {"Dia": "D", "Semana": "W", "Mês": "ME", "Trimestre": "QE", "Ano": "YE"}
        rule = freq_map[freq]

        agg_df = df_filtered.dropna(subset=[dt_col, val_col]).copy()
        agg_df[dt_col] = pd.to_datetime(agg_df[dt_col])

        if grp_col != "— nenhuma —":
            agg_df = (
                agg_df.groupby([pd.Grouper(key=dt_col, freq=rule), grp_col])[val_col]
                .sum().reset_index()
            )
            fig_ts = px.line(agg_df, x=dt_col, y=val_col, color=grp_col,
                             color_discrete_sequence=px.colors.qualitative.Set2)
        else:
            agg_df = agg_df.resample(rule, on=dt_col)[val_col].sum().reset_index()
            fig_ts = px.area(agg_df, x=dt_col, y=val_col,
                             color_discrete_sequence=["#3b82f6"])

        fig_ts.update_xaxes(rangeslider_visible=True)
        st.plotly_chart(safe_fig(fig_ts), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB: DADOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_data:
    st.markdown('<div class="section-title">Tabela de Dados Filtrados</div>', unsafe_allow_html=True)

    search = st.text_input("🔎 Busca rápida (qualquer coluna de texto)")
    display_df = df_filtered.copy()

    if search:
        mask = display_df.apply(
            lambda col: col.astype(str).str.contains(search, case=False, na=False)
        ).any(axis=1)
        display_df = display_df[mask]

    st.dataframe(display_df, use_container_width=True, height=400)

    output = BytesIO()
    display_df.to_excel(output, index=False)
    st.download_button(
        "⬇️ Baixar dados filtrados (.xlsx)",
        data=output.getvalue(),
        file_name="dados_filtrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
