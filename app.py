import hashlib
import json
import re
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analises as A
import referencias as ref
from valorant_data import carregar_base, resumo_jogadores, resumo_times

st.set_page_config(page_title="VALORANT • Coach pós-partida", layout="wide")

# paleta (azul, laranja, verde-água) + rampa sequencial azul
AZUL, LARANJA, AQUA, CINZA = "#2a78d6", "#eb6834", "#1baf7a", "#8c8b86"
LADO_CORES = {"Ataque": LARANJA, "Defesa": AZUL}
SINAL_CORES = {"Acima da base": AZUL, "Abaixo da base": LARANJA}
SEQ_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
ORDEM_COMPRA = ["Pistol", "Eco", "Semi-eco", "Semi-compra", "Compra completa"]
PASTA_MINIMAPAS = Path(__file__).resolve().parent / "minimapas"


def grafico(fig, altura=380):
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=70, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, title=None))
    st.plotly_chart(fig, width="stretch")


def pct(x):
    return "–" if pd.isna(x) else f"{x:.1f}%"


def slug(t):
    return re.sub(r"[^a-z0-9]+", "_", str(t).lower()).strip("_")


def barras_percentil(df, rotulo, titulo, hover=None, altura=None):
    """Barras horizontais de percentil (0–100), azul acima da mediana, laranja abaixo."""
    d = df.copy()
    d["posição"] = d["percentil"].map(lambda p: "Acima da base" if p >= 50 else "Abaixo da base")
    d = d.sort_values("percentil")
    fig = px.bar(d, x="percentil", y=rotulo, orientation="h", color="posição", color_discrete_map=SINAL_CORES,
                 hover_data=hover, title=titulo, labels={"percentil": "percentil (0 = pior, 100 = melhor)", rotulo: ""})
    fig.add_vline(x=50, line_dash="dot", line_color=CINZA)
    fig.update_xaxes(range=[0, 100])
    fig.update_traces(marker_line_width=0)
    grafico(fig, altura or 60 + 34 * len(d))


def figura_posicoes(pontos, cx, cy, cor=None, cores=None, fundo=None, modo="Pontos", hover=None, altura=620):
    """Desenha posições no minimapa (0–1). `fundo` = todos os abates do mapa em cinza,
    só para dar a silhueta do mapa quando não há imagem."""
    if modo == "Calor":
        fig = px.density_heatmap(pontos, x=cx, y=cy, nbinsx=40, nbinsy=40, color_continuous_scale=SEQ_AZUL,
                                 range_x=[0, 1], range_y=[0, 1])
    else:
        fig = px.scatter(pontos, x=cx, y=cy, color=cor, color_discrete_map=cores, hover_data=hover)
        fig.update_traces(marker=dict(size=8, opacity=0.8, line=dict(width=1, color="white")))
    if fundo is not None and len(fundo):
        fig.add_trace(go.Scattergl(x=fundo[cx], y=fundo[cy], mode="markers", hoverinfo="skip", showlegend=False,
                                   marker=dict(size=3, color=CINZA, opacity=0.12)))
        fig.data = (fig.data[-1],) + fig.data[:-1]  # fundo atrás
    mapa = pontos["mapa"].iloc[0] if "mapa" in pontos and len(pontos) else None
    img = next((p for p in PASTA_MINIMAPAS.glob(f"{mapa}.*") if p.suffix.lower() in (".png", ".jpg", ".webp")), None) if mapa else None
    if img:
        from PIL import Image
        fig.add_layout_image(dict(source=Image.open(img), xref="x", yref="y", x=0, y=0, sizex=1, sizey=1,
                                  sizing="stretch", layer="below", opacity=0.9))
    fig.update_xaxes(range=[0, 1], showgrid=False, visible=False, constrain="domain")
    fig.update_yaxes(range=[1, 0], showgrid=False, visible=False, scaleanchor="x")
    fig.update_layout(height=altura, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=1.04, title=None))
    return fig


# Carregamento

@st.cache_resource(show_spinner="Lendo e tratando os JSONs...")
def base_da_pasta(pasta: str):
    return carregar_base(pasta)


@st.cache_resource(show_spinner="Lendo e tratando os JSONs enviados...")
def base_dos_uploads(chave: str, arquivos: tuple):
    pasta = Path(tempfile.gettempdir()) / f"valorant_upload_{chave}"
    pasta.mkdir(exist_ok=True)
    for nome, conteudo in arquivos:
        (pasta / Path(nome).name).write_bytes(conteudo)
    return carregar_base(pasta, usar_cache=False)


@st.cache_data(show_spinner="Calculando análises...")
def analisar(_base, chave):
    ids = set(chave[1])
    R = _base.rounds[_base.rounds["match_id"].isin(ids)]
    K = _base.kills[_base.kills["match_id"].isin(ids)]
    J = _base.jogadores[_base.jogadores["match_id"].isin(ids)]
    tr = A.tabela_time_round(R)
    mortes = A.tabela_mortes(K)
    met = A.metricas_por_time(tr, mortes)
    coes = A.coesao_times(mortes)
    perfil = A.perfil_jogadores(J, mortes)
    return tr, mortes, met, coes, perfil


st.sidebar.title("Dados")
fonte = st.sidebar.radio("Origem", ["Pasta local", "Enviar arquivos .json"], label_visibility="collapsed")
try:
    if fonte == "Pasta local":
        pasta = st.sidebar.text_input("Pasta com os JSONs (busca em subpastas)", "dados")
        base = base_da_pasta(pasta)
        id_base = "pasta:" + pasta
    else:
        ups = st.sidebar.file_uploader("Arquivos de partida", type="json", accept_multiple_files=True)
        if not ups:
            st.info("Envie um ou mais arquivos .json de partida na barra lateral.")
            st.stop()
        arquivos = tuple(sorted((u.name, u.getvalue()) for u in ups))
        chave_up = hashlib.sha1(b"".join(n.encode() + c for n, c in arquivos)).hexdigest()[:12]
        base = base_dos_uploads(chave_up, arquivos)
        id_base = "upload:" + chave_up
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

P = base.partidas

# Filtros (escopo da análise)

st.sidebar.title("Escopo da análise")
st.sidebar.caption("Tudo (inclusive a média da base usada nas comparações) é calculado só com as partidas abaixo.")
eventos = st.sidebar.multiselect("Evento", sorted(P["evento"].unique()))
p_f = P[P["evento"].isin(eventos)] if eventos else P
fases = st.sidebar.multiselect("Fase", sorted(f for f in p_f["fase"].unique() if f))
if fases:
    p_f = p_f[p_f["fase"].isin(fases)]
mapas = st.sidebar.multiselect("Mapa", sorted(p_f["mapa"].unique()))
if mapas:
    p_f = p_f[p_f["mapa"].isin(mapas)]

ids = set(p_f["match_id"])
if not ids:
    st.warning("Nenhuma partida com esses filtros.")
    st.stop()

R = base.rounds[base.rounds["match_id"].isin(ids)]
J = base.jogadores[base.jogadores["match_id"].isin(ids)]
JR = base.jogador_round[base.jogador_round["match_id"].isin(ids)]
K = base.kills[base.kills["match_id"].isin(ids)]
T = base.times[base.times["match_id"].isin(ids)]
TR, MORTES, MET, COES, PERFIL = analisar(base, (id_base, tuple(sorted(ids))))

escopo = (f"{len(ids)} partidas · evento: {', '.join(eventos) or 'todos'} · fase: {', '.join(fases) or 'todas'}"
          f" · mapa: {', '.join(mapas) or 'todos'}")
st.sidebar.caption(f"{len(ids)} de {len(P)} partidas no escopo")
if base.avisos:
    with st.sidebar.expander(f"{len(base.avisos)} aviso(s) na leitura"):
        for a in base.avisos:
            st.write("•", a)

# Cabeçalho guiado

st.title("Coach pós-partida — VALORANT")
st.markdown("**1.** Escolha seu time e veja o diagnóstico em **Meu time** · "
            "**2.** Escolha o próximo adversário e veja o **Dossiê** · "
            "**3.** Baixe o relatório no fim da aba Meu time")
times_escopo = sorted(T["time"].unique())
c1, c2 = st.columns(2)
meu = c1.selectbox("Seu time", times_escopo, index=None, placeholder="Escolha seu time", key="meu_time")
adv = c2.selectbox("Próximo adversário (opcional)", times_escopo, index=None,
                   placeholder="Escolha o adversário", key="adversario")
if meu and adv and meu == adv:
    c2.warning("Escolha um adversário diferente do seu time.")
    adv = None

abas = st.tabs(["Meu time", "Adversário", "Coesão", "Jogador", "Explorar a base"])

# MEU TIME
with abas[0]:
    if not meu:
        st.info("Escolha seu time no topo da página para ver o diagnóstico.")
    else:
        tm = T[T["time"] == meu]
        coes_meu = COES.set_index("time").loc[meu] if meu in set(COES["time"]) else None
        c = st.columns(4)
        c[0].metric("Partidas", len(tm))
        c[1].metric("Vitórias", f'{int(tm["venceu"].sum())} ({pct(100 * tm["venceu"].mean())})')
        c[2].metric("Rounds vencidos", pct(100 * tm["rounds_ganhos"].sum() / tm["rounds_jogados"].sum()))
        c[3].metric("Nota de coesão", "–" if coes_meu is None or pd.isna(coes_meu["nota_coesao"])
                    else f'{coes_meu["nota_coesao"]:.0f}/100')

        fortes, fracos, todas = A.diagnostico(MET, meu)
        e, d = st.columns(2)
        with e:
            st.subheader("Pontos fortes")
            if fortes.empty:
                st.write("Nenhum destaque com amostra suficiente.")
            for _, r in fortes.iterrows():
                st.success(f'**{r["nome"]}** — {r["texto"]}  \n'
                           f'_{r["nivel"]} · melhor que {r["percentil"]:.0f}% dos times_')
        with d:
            st.subheader("Oportunidades de melhoria")
            if fracos.empty:
                st.write("Nenhuma métrica abaixo da base com amostra suficiente.")
            for _, r in fracos.iterrows():
                st.warning(f'**{r["nome"]}** — {r["texto"]}  \n'
                           f'_{r["nivel"]} · melhor que {r["percentil"]:.0f}% dos times_  \n'
                           f'**Sugestão:** {r["dica"]}')
        st.caption("Cada taxa é comparada com a taxa de todos os times no escopo. 'n' é o número de rounds "
                   "(ou mortes) usados. Diferença forte/moderada = z-score binomial ≥ 2 / ≥ 1.")

        if not todas.empty:
            barras_percentil(todas.assign(valor=todas["taxa"].map(A.fmt_pct), base=todas["taxa_base"].map(A.fmt_pct)),
                             "nome", "Todas as métricas: percentil entre os times",
                             hover={"valor": True, "base": True, "n": True, "posição": False})

        e, d = st.columns(2)
        with e:
            pm_ = tm.groupby("mapa").agg(partidas=("match_id", "count"), vitorias=("venceu", "sum")).reset_index()
            pm_["win_pct"] = 100 * pm_["vitorias"] / pm_["partidas"]
            fig = px.bar(pm_.sort_values("win_pct"), x="win_pct", y="mapa", orientation="h", text="partidas",
                         title="% de vitórias por mapa (número = partidas)", color_discrete_sequence=[AZUL],
                         labels={"win_pct": "% vitórias", "mapa": ""})
            fig.update_xaxes(range=[0, 100])
            grafico(fig, 320)
        with d:
            lado_m = (TR[TR["time"] == meu].groupby(["mapa", "lado"])["venceu"].mean() * 100).reset_index()
            fig = px.bar(lado_m, x="mapa", y="venceu", color="lado", barmode="group", color_discrete_map=LADO_CORES,
                         title="% de rounds vencidos por mapa e lado", labels={"venceu": "% rounds", "mapa": ""})
            fig.add_hline(y=50, line_dash="dot", line_color=CINZA)
            fig.update_yaxes(range=[0, 100])
            grafico(fig, 320)

        st.subheader("Jogadores do time")
        pj = PERFIL[PERFIL["time"] == meu].sort_values("rounds", ascending=False)
        st.dataframe(pj[["nome", "funcao", "agente_principal", "partidas", "rounds", "acs", "kd", "adr", "kast_pct",
                         "fk_menos_fd", "trade_pct", "isolado_pct", "acs_cv"]],
                     hide_index=True, width="stretch", column_config={
                         "funcao": "Função", "agente_principal": "Agente", "acs": "ACS", "kd": "K/D", "adr": "ADR",
                         "kast_pct": "KAST %", "fk_menos_fd": "FK − FD", "trade_pct": "Mortes trocadas %",
                         "isolado_pct": "Mortes isoladas %", "acs_cv": "Variação do ACS"})

        with st.expander("Tabela completa do diagnóstico"):
            st.dataframe(todas[["nome", "taxa", "taxa_base", "n", "z", "percentil", "nivel"]]
                         .assign(taxa=lambda x: (100 * x["taxa"]).round(1), taxa_base=lambda x: (100 * x["taxa_base"]).round(1),
                                 z=lambda x: x["z"].round(2)),
                         hide_index=True, width="stretch",
                         column_config={"taxa": "Time %", "taxa_base": "Base %", "nivel": "Confiança"})

        plano = A.plano_de_jogo(TR, MET, J, K, adv) if adv else None
        md = A.relatorio_markdown(meu, fortes, fracos, coes_meu, pj.head(7), adv, plano, escopo)
        st.download_button("Baixar relatório (.md)", md.encode("utf-8"), file_name=f"relatorio_{slug(meu)}.md",
                           mime="text/markdown", type="primary")
        st.caption("O relatório inclui o plano de jogo se um adversário estiver escolhido.")

# ADVERSÁRIO
with abas[1]:
    if not adv:
        st.info("Escolha o próximo adversário no topo da página para ver o dossiê.")
    else:
        mapas_adv = T[T["time"] == adv]["mapa"].value_counts()
        mapa_d = st.selectbox("Mapa", ["Todos"] + list(mapas_adv.index), key="mapa_dossie",
                              help="Mapas em ordem de partidas jogadas pelo adversário")
        mapa_q = None if mapa_d == "Todos" else mapa_d
        ta = T[(T["time"] == adv) & ((T["mapa"] == mapa_q) if mapa_q else True)]
        c = st.columns(4)
        c[0].metric("Partidas", len(ta))
        c[1].metric("Vitórias", f'{int(ta["venceu"].sum())} ({pct(100 * ta["venceu"].mean()) if len(ta) else "–"})')
        t_eu, t_base, n_pl = A.tempo_de_plant(TR, adv, mapa_q)
        c[2].metric("Tempo até o plant (mediana)", "–" if pd.isna(t_eu) else f"{t_eu:.0f} s",
                    None if pd.isna(t_eu) or pd.isna(t_base) else f"{t_eu - t_base:+.0f} s vs base",
                    delta_color="off")
        f_eu, f_base, n_f, w_force, w_save = A.compra_pos_pistol_perdido(TR, adv)
        c[3].metric("Force após perder o pistol", "–" if pd.isna(f_eu) else A.fmt_pct(f_eu),
                    None if pd.isna(f_eu) else f"base {A.fmt_pct(f_base)} · n = {n_f}", delta_color="off")

        st.subheader(f"Plano de jogo contra {adv}")
        plano = A.plano_de_jogo(TR, MET, J, K, adv, mapa_q)
        if plano:
            st.markdown("\n".join(f"- {p}" for p in plano))
        else:
            st.write("Amostra insuficiente para recomendações automáticas.")

        e, d = st.columns(2)
        f_adv, o_adv, _ = A.diagnostico(MET, adv, sujeito="Eles", qtd=3)
        with e:
            st.markdown("**Pontos fortes deles (respeitar)**")
            for _, r in f_adv.iterrows():
                st.write(f'• {r["texto"]} — _{r["nivel"]}_')
        with d:
            st.markdown("**Pontos fracos deles (explorar)**")
            for _, r in o_adv.iterrows():
                st.write(f'• {r["texto"]} — _{r["nivel"]}_')

        e, d = st.columns(2)
        with e:
            s = A.sites_de_plant(TR, adv, mapa_q)
            if len(s):
                s = s[s["mapa"].isin(s.groupby("mapa")["plants"].sum().nlargest(4).index)]
                fig = px.bar(s, x="site", y="pct_dos_plants", facet_col="mapa", text="plants",
                             hover_data={"vitoria_pct": ":.0f", "tempo_medio_s": ":.0f"}, color_discrete_sequence=[LARANJA],
                             title="Onde plantam (% dos plants no mapa; número = plants)",
                             labels={"pct_dos_plants": "% dos plants", "site": ""})
                fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                fig.update_yaxes(range=[0, 100])
                fig.update_xaxes(matches=None, categoryorder="category ascending")
                grafico(fig, 340)
        with d:
            comp = A.composicoes(J, adv, mapa_q)
            st.markdown("**Composições mais usadas**")
            st.dataframe(comp.head(8), hide_index=True, width="stretch")

        jc = A.jogadores_chave(J, K, adv)
        st.markdown("**Jogadores**")
        if len(jc["tabela"]):
            st.dataframe(jc["tabela"][["nome", "agente_principal", "partidas", "acs", "kd", "kast_pct", "primeiros_abates",
                                       "primeiras_mortes", "hs_pct"]],
                         hide_index=True, width="stretch",
                         column_config={"agente_principal": "Agente", "acs": "ACS", "kd": "K/D", "kast_pct": "KAST %",
                                        "primeiros_abates": "1º abates", "primeiras_mortes": "1ª mortes", "hs_pct": "HS %"})

        mapa_h = mapa_q or (mapas_adv.index[0] if len(mapas_adv) else None)
        if mapa_h:
            st.subheader(f"Onde {adv} mata — {mapa_h}")
            modo_h = st.radio("Estilo", ["Pontos", "Calor"], horizontal=True, key="modo_dossie")
            fundo = K[(K["mapa"] == mapa_h)].dropna(subset=["killer_mx"])
            ka = K[(K["mapa"] == mapa_h) & (K["killer_time"] == adv) & ~K["fogo_amigo"]].dropna(subset=["killer_mx"])
            e, d = st.columns(2)
            for col, lado_ in ((e, "Ataque"), (d, "Defesa")):
                with col:
                    pts = ka[ka["killer_lado"] == lado_]
                    st.markdown(f"**{lado_}** · {len(pts)} abates")
                    if len(pts):
                        st.plotly_chart(figura_posicoes(pts, "killer_mx", "killer_my", cores=LADO_CORES, cor="killer_lado",
                                                        fundo=fundo, modo=modo_h, altura=480,
                                                        hover=["killer_nome", "vitima_nome", "arma", "round"]),
                                        width="stretch", key=f"dossie_{lado_}")
            st.caption("Pontos cinza = todos os abates da base neste mapa (silhueta do mapa).")

        if meu:
            h2h = P[P["match_id"].isin(ids) & (((P["time_red"] == meu) & (P["time_blue"] == adv)) |
                                                ((P["time_red"] == adv) & (P["time_blue"] == meu)))]
            if len(h2h):
                st.markdown(f"**Confrontos diretos: {meu} × {adv}**")
                st.dataframe(h2h[["data", "evento", "fase", "mapa", "time_red", "rounds_red", "rounds_blue", "time_blue"]],
                             hide_index=True, width="stretch")

# COESÃO
with abas[2]:
    st.markdown(f"No momento de cada morte o JSON traz a posição de todos os jogadores vivos. Daí sai a distância até "
                f"o aliado mais próximo. A morte é **isolada** quando esse aliado está a mais de "
                f"{ref.LIMIAR_ISOLADO_M} m, e é **trocada** quando um aliado mata o assassino em até 5 s.")
    tpd = A.trade_por_distancia(MORTES).assign(serie="Base")
    if meu:
        tpd = pd.concat([tpd, A.trade_por_distancia(MORTES[MORTES["time"] == meu]).assign(serie=meu)])
    fig = px.bar(tpd, x="faixa", y="trade_pct", color="serie", barmode="group", hover_data=["mortes"],
                 color_discrete_sequence=[CINZA, AZUL],
                 title="Quanto mais longe o aliado, menos a morte é trocada",
                 labels={"faixa": "Distância até o aliado vivo mais próximo", "trade_pct": "% das mortes trocadas"})
    grafico(fig, 360)

    e, d = st.columns([3, 2])
    with e:
        st.markdown("**Ranking de coesão dos times**")
        st.dataframe(COES[["time", "nota_coesao", "trade_pct", "isolado_pct", "dist_mediana_m", "mortes"]],
                     hide_index=True, width="stretch", height=360,
                     column_config={"nota_coesao": "Nota (0–100)", "trade_pct": "Trocadas %",
                                    "isolado_pct": "Isoladas %", "dist_mediana_m": "Dist. mediana (m)"})
        st.caption("Nota = média dos percentis do time em mortes trocadas (mais é melhor) e mortes isoladas "
                   "(menos é melhor). Só times com 40+ mortes.")
    with d:
        if meu:
            cj = A.coesao_jogadores(MORTES, meu)
            cj = cj[cj["mortes"] >= 15]
            fig = px.bar(cj.sort_values("isolado_pct"), x="isolado_pct", y="nome", orientation="h",
                         hover_data=["agente", "mortes", "trade_pct", "dist_mediana_m"], color_discrete_sequence=[LARANJA],
                         title=f"Quem morre isolado em {meu}", labels={"isolado_pct": "% das mortes isoladas", "nome": ""})
            media = 100 * MORTES.loc[MORTES["com_aliado"] & MORTES["dist_aliado_m"].notna(), "isolada"].mean()
            fig.add_vline(x=media, line_dash="dot", line_color=CINZA, annotation_text="base", annotation_position="top")
            grafico(fig, 360)
        else:
            st.info("Escolha seu time no topo para ver quem morre isolado.")

    if meu:
        mm = MORTES[(MORTES["time"] == meu) & MORTES["com_aliado"]].dropna(subset=["vitima_mx"])
        mapas_m = mm["mapa"].value_counts()
        if len(mapas_m):
            c = st.columns(3)
            mapa_c = c[0].selectbox("Mapa", list(mapas_m.index), key="mapa_coesao",
                                    help="Mapas em ordem de número de mortes do time")
            so_iso = c[1].checkbox("Só mortes isoladas", value=True)
            jog_c = c[2].multiselect("Jogador", sorted(mm["vitima_nome"].dropna().unique()), key="jog_coesao")
            pts = mm[mm["mapa"] == mapa_c]
            if so_iso:
                pts = pts[pts["isolada"]]
            if jog_c:
                pts = pts[pts["vitima_nome"].isin(jog_c)]
            pts = pts.assign(situacao=pts["vitima_trocada"].map({True: "Trocada", False: "Não trocada"}))
            st.markdown(f"**Onde {meu} morre {'isolado' if so_iso else ''} — {mapa_c}** · {len(pts)} mortes")
            fundo = K[K["mapa"] == mapa_c].dropna(subset=["vitima_mx"])
            if len(pts):
                st.plotly_chart(figura_posicoes(pts, "vitima_mx", "vitima_my", cor="situacao",
                                                cores={"Trocada": AZUL, "Não trocada": LARANJA}, fundo=fundo,
                                                hover=["vitima_nome", "vitima_agente", "dist_aliado_m", "round", "killer_nome"]),
                                width="stretch", key="mapa_coesao_fig")
            st.caption("Use no VOD review: filtre o jogador e veja em que regiões ele costuma ficar sozinho.")

# JOGADOR
with abas[3]:
    c = st.columns([2, 1])
    perf = PERFIL.copy()
    ordem = pd.concat([perf[perf["time"] == meu], perf[perf["time"] != meu]]) if meu else perf
    ordem = ordem[ordem["rounds"] > 0]
    rotulos = {}
    for _, r in ordem.iterrows():
        rot_j = f'{r["nome"]} ({r["time"]} · {r["funcao"]})'
        rotulos[rot_j if rot_j not in rotulos else f'{rot_j} [{r["puuid"][:6]}]'] = r["puuid"]
    jog = rotulos[c[0].selectbox("Jogador", list(rotulos))]
    min_r = c[1].slider("Comparar com jogadores com pelo menos N rounds", 20, 300, 100, 20)
    eu = perf.set_index("puuid").loc[jog]
    c = st.columns(5)
    c[0].metric("Função principal", eu["funcao"])
    c[1].metric("Partidas / rounds", f'{eu["partidas"]} / {eu["rounds"]}')
    c[2].metric("ACS", f'{eu["acs"]:.0f}')
    c[3].metric("K/D", f'{eu["kd"]:.2f}')
    c[4].metric("KAST", f'{eu["kast_pct"]:.0f}%')
    if eu["rounds"] < min_r:
        st.warning(f"Este jogador tem só {eu['rounds']} rounds no escopo: os percentis são indicativos.")

    pc = A.percentis_jogador(perf, jog, min_r)
    if pc.empty:
        st.info("Poucos jogadores da mesma função para comparar. Diminua o mínimo de rounds.")
    else:
        fortes_j, fracos_j = A.frases_jogador(pc, eu["funcao"])
        e, d = st.columns(2)
        with e:
            st.markdown("**Pontos fortes**")
            for f in fortes_j or ["Nenhuma métrica acima do percentil 60."]:
                st.write("•", f)
        with d:
            st.markdown("**A melhorar**")
            for f in fracos_j or ["Nenhuma métrica abaixo do percentil 40."]:
                st.write("•", f)
        barras_percentil(pc, "metrica", f'Percentil entre {pc["n_comparados"].iloc[0]} {eu["funcao"].lower()}s da base '
                                        f'(com {min_r}+ rounds)', hover={"valor": True, "mediana_funcao": True, "posição": False})
        st.caption("Variação do ACS = desvio padrão ÷ média do ACS entre partidas (menor = mais consistente; "
                   "precisa de 3+ partidas). Em métricas onde menos é melhor, o percentil já está invertido.")

    hist = J[J["puuid"] == jog].sort_values("data").reset_index(drop=True)
    hist["partida_n"] = hist.index + 1
    hist["dia"] = hist["data"].dt.strftime("%d/%m/%Y")
    e, d = st.columns(2)
    with e:
        fig = px.line(hist, x="partida_n", y="acs", markers=True, hover_data=["dia", "mapa", "agente", "kills", "deaths"],
                      title="ACS partida a partida (linha = média)", color_discrete_sequence=[AZUL],
                      labels={"partida_n": "partida (ordem cronológica)", "acs": "ACS"})
        fig.add_hline(y=hist["acs"].mean(), line_dash="dot", line_color=CINZA)
        grafico(fig, 320)
    with d:
        armas = K[(K["killer"] == jog) & ~K["fogo_amigo"]]["arma"].value_counts().head(10)
        fig = px.bar(armas.sort_values(), orientation="h", title="Abates por arma / habilidade",
                     color_discrete_sequence=[AZUL], labels={"value": "abates", "arma": ""})
        fig.update_layout(showlegend=False)
        grafico(fig, 320)
    ag = hist.groupby("agente").agg(partidas=("match_id", "count"), acs=("acs", "mean"),
                                    kd=("kd", "mean"), vitorias=("venceu", "mean")).round(2)
    ag["vitorias"] = (100 * ag["vitorias"]).round(1)
    st.markdown("**Por agente**")
    st.dataframe(ag.rename(columns={"vitorias": "vitórias %"}), width="stretch")

# EXPLORAR A BASE
with abas[4]:
    sub = st.tabs(["Visão geral", "Partida", "Times", "Jogadores", "Rounds e economia", "Mapa de abates", "Tabelas"])

    # 1. visão geral
    with sub[0]:
        c = st.columns(5)
        c[0].metric("Partidas", len(ids))
        c[1].metric("Rounds", f"{len(R):,}".replace(",", "."))
        c[2].metric("Abates", f"{len(K):,}".replace(",", "."))
        c[3].metric("Jogadores", J["puuid"].nunique())
        c[4].metric("Times", T["time"].nunique())

        e, d = st.columns(2)
        with e:
            m = p_f["mapa"].value_counts().rename_axis("mapa").reset_index(name="partidas")
            fig = px.bar(m, x="partidas", y="mapa", orientation="h", title="Partidas por mapa",
                         color_discrete_sequence=[AZUL])
            fig.update_yaxes(categoryorder="total ascending", title=None)
            grafico(fig)
        with d:
            ev = p_f.assign(fase=p_f["fase"].replace("", "—")).groupby(["evento", "fase"]).size().reset_index(name="partidas")
            ev["rotulo"] = ev["evento"] + " · " + ev["fase"]
            fig = px.bar(ev, x="partidas", y="rotulo", orientation="h", title="Partidas por evento e fase",
                         color_discrete_sequence=[AZUL])
            fig.update_yaxes(categoryorder="total ascending", title=None)
            grafico(fig)

        e, d = st.columns(2)
        with e:
            picks = (J.groupby(["agente", "funcao"])["match_id"].count().reset_index(name="escolhas")
                     .assign(pick_pct=lambda x: 100 * x["escolhas"] / (2 * len(ids))))
            fig = px.bar(picks.sort_values("pick_pct").tail(20), x="pick_pct", y="agente", orientation="h",
                         hover_data=["funcao", "escolhas"], title="Agentes: % das composições em que aparecem",
                         color_discrete_sequence=[AZUL], labels={"pick_pct": "% das composições", "agente": ""})
            grafico(fig, 520)
        with d:
            lado = (R.groupby("mapa")["lado_vencedor"].apply(lambda s: 100 * (s == "Ataque").mean())
                    .reset_index(name="ataque_pct").sort_values("ataque_pct"))
            lado["n_rounds"] = lado["mapa"].map(R["mapa"].value_counts())
            fig = px.bar(lado, x="ataque_pct", y="mapa", orientation="h", hover_data=["n_rounds"],
                         title="% de rounds vencidos pelo ataque, por mapa",
                         color_discrete_sequence=[LARANJA], labels={"ataque_pct": "% vitórias do ataque", "mapa": ""})
            fig.add_vline(x=50, line_dash="dot", line_color=CINZA)
            fig.update_xaxes(range=[0, 100])
            grafico(fig, 520)

    # 2. partida
    with sub[1]:
        p_part = p_f
        if meu and st.checkbox(f"Só partidas de {meu}", value=True):
            p_part = p_f[(p_f["time_red"] == meu) | (p_f["time_blue"] == meu)]
        rot = p_part.sort_values("data", ascending=False).apply(
            lambda r: f'{r["data"]:%d/%m} · {r["time_red"]} {r["rounds_red"]} x {r["rounds_blue"]} {r["time_blue"]} · {r["mapa"]} · {r["evento"]} {r["fase"]}'.strip(),
            axis=1)
        opcoes_p = {}
        for i, lbl in rot.items():
            opcoes_p[lbl if lbl not in opcoes_p else f"{lbl} [{i}]"] = i
        escolha = opcoes_p[st.selectbox("Partida", list(opcoes_p))]
        pm = p_part.loc[escolha]
        mid = pm["match_id"]
        st.subheader(f'{pm["time_red"]} {pm["rounds_red"]} x {pm["rounds_blue"]} {pm["time_blue"]} — {pm["mapa"]}')
        st.caption(f'{pm["evento"]} {pm["fase"]} · {pm["data"]:%d/%m/%Y %H:%M} · {pm["duracao_min"]} min · arquivo {pm["arquivo"]}')

        rr = base.rounds[base.rounds["match_id"] == mid].sort_values("round")
        fig = go.Figure()
        for col, nome, cor in (("placar_red", pm["time_red"], AZUL), ("placar_blue", pm["time_blue"], LARANJA)):
            fig.add_trace(go.Scatter(x=rr["round"], y=rr[col], name=nome, mode="lines+markers",
                                     line=dict(color=cor, width=2), marker=dict(size=8),
                                     line_shape="hv"))
        fig.update_layout(title="Placar round a round", xaxis_title="Round", yaxis_title="Rounds vencidos",
                          hovermode="x unified")
        grafico(fig, 320)

        st.markdown("**Placar dos jogadores**")
        sb = base.jogadores[base.jogadores["match_id"] == mid].sort_values(["time", "acs"], ascending=[True, False])
        st.dataframe(sb[["time", "nome", "agente", "acs", "kills", "deaths", "assists", "kd", "adr", "kast_pct",
                         "hs_pct", "primeiros_abates", "primeiras_mortes"]],
                     hide_index=True, width="stretch")

        st.markdown("**Rounds**")
        st.dataframe(rr[["round", "vencedor", "lado_vencedor", "resultado", "time_ataque", "compra_ataque",
                         "valor_ataque", "compra_defesa", "valor_defesa", "site", "time_primeiro_abate",
                         "n_abates", "cerimonia"]],
                     hide_index=True, width="stretch")

        with st.expander("Ver o JSON bruto desta partida"):
            if fonte == "Pasta local":
                caminho = next(Path(pasta).rglob(pm["arquivo"]), None)
                if caminho:
                    st.json(json.loads(caminho.read_text(encoding="utf-8")), expanded=1)
            else:
                st.write("Disponível só no modo pasta local.")

    # 3. times
    with sub[2]:
        rt = resumo_times(base, ids)
        st.dataframe(rt, hide_index=True, width="stretch", column_config={
            "win_pct": "Vitórias %", "rounds_pct": "Rounds %", "ataque_pct": "Ataque %",
            "defesa_pct": "Defesa %", "pistol_pct": "Pistol %", "fk_pct": "Primeiro abate %",
            "conversao_fk_pct": "Vence após 1º abate %"})
        st.caption("Primeiro abate % = em quantos rounds o time abriu o round matando. "
                   "Vence após 1º abate % = desses rounds, quantos o time venceu.")

        time = st.selectbox("Detalhar time", rt["time"])
        tm = T[T["time"] == time]
        ids_t = set(tm["match_id"])
        rt_ = R[R["match_id"].isin(ids_t)]
        c = st.columns(4)
        lin = rt[rt["time"] == time].iloc[0]
        c[0].metric("Partidas", int(lin["partidas"]))
        c[1].metric("Vitórias", f'{int(lin["vitorias"])} ({pct(lin["win_pct"])})')
        c[2].metric("Ataque", pct(lin["ataque_pct"]))
        c[3].metric("Defesa", pct(lin["defesa_pct"]))

        e, d = st.columns(2)
        with e:
            pm_ = tm.groupby("mapa").agg(partidas=("match_id", "count"), vitorias=("venceu", "sum")).reset_index()
            pm_["win_pct"] = 100 * pm_["vitorias"] / pm_["partidas"]
            fig = px.bar(pm_.sort_values("win_pct"), x="win_pct", y="mapa", orientation="h", text="partidas",
                         title="% de vitórias por mapa (número = partidas)", color_discrete_sequence=[AZUL],
                         labels={"win_pct": "% vitórias", "mapa": ""})
            fig.update_xaxes(range=[0, 100])
            grafico(fig)
        with d:
            lados = []
            for lado_, col_time in (("Ataque", "time_ataque"), ("Defesa", "time_defesa")):
                x = rt_[rt_[col_time] == time]
                g = x.groupby("compra_" + ("ataque" if lado_ == "Ataque" else "defesa"))["vencedor"].agg(
                    rounds="count", vitorias=lambda s: (s == time).sum()).reset_index()
                g.columns = ["compra", "rounds", "vitorias"]
                g["lado"] = lado_
                lados.append(g)
            g = pd.concat(lados)
            g["win_pct"] = 100 * g["vitorias"] / g["rounds"]
            fig = px.bar(g, x="compra", y="win_pct", color="lado", barmode="group", hover_data=["rounds"],
                         category_orders={"compra": ORDEM_COMPRA}, color_discrete_map=LADO_CORES,
                         title="% de rounds vencidos por tipo de compra do time",
                         labels={"win_pct": "% vitórias", "compra": ""})
            fig.update_yaxes(range=[0, 100])
            grafico(fig)

        comp = (J[J["time"] == time].groupby("match_id")["agente"].apply(lambda s: ", ".join(sorted(s)))
                .value_counts().rename_axis("composição").reset_index(name="partidas"))
        st.markdown("**Composições mais usadas**")
        st.dataframe(comp.head(10), hide_index=True, width="stretch")
        st.markdown("**Jogadores do time**")
        st.dataframe(resumo_jogadores(J[J["time"] == time]), hide_index=True, width="stretch")

    # 4. jogadores
    with sub[3]:
        min_r = st.slider("Mínimo de rounds jogados", 0, 300, 50, 10)
        rj = resumo_jogadores(J, min_rounds=min_r)
        st.dataframe(rj.drop(columns="puuid"), hide_index=True, width="stretch", column_config={
            "win_pct": "Vitórias %", "kd": "K/D", "acs": "ACS", "adr": "ADR", "kast_pct": "KAST %",
            "hs_pct": "HS %", "primeiros_abates": "1º abates", "primeiras_mortes": "1ª mortes",
            "fk_menos_fd": "FK − FD"})
        st.caption("ACS = score médio por round · ADR = dano médio em inimigos por round · "
                   "KAST = % de rounds com abate, assistência, sobrevivência ou morte trocada (5 s)")

        if len(rj):
            e, d = st.columns(2)
            with e:
                fig = px.scatter(rj, x="kast_pct", y="acs", hover_name="nome", hover_data=["time", "agente_principal", "rounds"],
                                 title="ACS × KAST (cada ponto é um jogador)", color_discrete_sequence=[AZUL],
                                 labels={"kast_pct": "KAST %", "acs": "ACS"})
                fig.update_traces(marker=dict(size=9, line=dict(width=1, color="white")))
                grafico(fig, 420)
            with d:
                fig = px.scatter(rj, x="primeiros_abates", y="primeiras_mortes", hover_name="nome",
                                 hover_data=["time", "agente_principal"], title="Agressividade: 1º abates × 1ª mortes",
                                 color_discrete_sequence=[LARANJA],
                                 labels={"primeiros_abates": "1º abates", "primeiras_mortes": "1ª mortes"})
                mx = max(rj["primeiros_abates"].max(), rj["primeiras_mortes"].max())
                fig.add_trace(go.Scatter(x=[0, mx], y=[0, mx], mode="lines", line=dict(dash="dot", color=CINZA),
                                         showlegend=False, hoverinfo="skip"))
                fig.update_traces(marker=dict(size=9, line=dict(width=1, color="white")), selector=dict(mode="markers"))
                grafico(fig, 420)

            opcoes_j = {f'{r["nome"]} ({r["time"]}) [{i}]': i for i, r in rj.iterrows()}
            jog = opcoes_j[st.selectbox("Detalhar jogador", list(opcoes_j))]
            pid = rj.loc[jog, "puuid"]
            hist = J[J["puuid"] == pid].sort_values("data")
            e, d = st.columns(2)
            with e:
                fig = px.line(hist, x="data", y="acs", markers=True, hover_data=["mapa", "agente", "kills", "deaths"],
                              title="ACS partida a partida", color_discrete_sequence=[AZUL], labels={"data": "", "acs": "ACS"})
                grafico(fig, 340)
            with d:
                armas = K[(K["killer"] == pid) & ~K["fogo_amigo"]]["arma"].value_counts().head(10)
                fig = px.bar(armas.sort_values(), orientation="h", title="Abates por arma / habilidade",
                             color_discrete_sequence=[AZUL], labels={"value": "abates", "arma": ""})
                fig.update_layout(showlegend=False)
                grafico(fig, 340)
            ag = hist.groupby("agente").agg(partidas=("match_id", "count"), acs=("acs", "mean"),
                                            kd=("kd", "mean"), vitorias=("venceu", "mean")).round(2)
            ag["vitorias"] = (100 * ag["vitorias"]).round(1)
            st.markdown("**Por agente**")
            st.dataframe(ag.rename(columns={"vitorias": "vitórias %"}), width="stretch")

    # 5. rounds e economia
    with sub[4]:
        e, d = st.columns(2)
        with e:
            g = (R.groupby("compra_ataque")["lado_vencedor"].apply(lambda s: 100 * (s == "Ataque").mean())
                 .reindex(ORDEM_COMPRA).reset_index(name="win_pct"))
            g["rounds"] = g["compra_ataque"].map(R["compra_ataque"].value_counts())
            fig = px.bar(g, x="compra_ataque", y="win_pct", hover_data=["rounds"], text="rounds",
                         title="Ataque: % de rounds vencidos por tipo de compra (número = rounds)",
                         color_discrete_sequence=[LARANJA], labels={"compra_ataque": "", "win_pct": "% vitórias"})
            fig.update_yaxes(range=[0, 100])
            grafico(fig)
        with d:
            x = R[~R["pistol"]]
            tab = pd.crosstab(x["compra_ataque"], x["compra_defesa"],
                              values=(x["lado_vencedor"] == "Ataque") * 100, aggfunc="mean").round(0)
            ordem = [o for o in ORDEM_COMPRA if o != "Pistol"]
            tab = tab.reindex(index=ordem, columns=ordem)
            fig = px.imshow(tab, text_auto=True, color_continuous_scale=SEQ_AZUL, zmin=0, zmax=100, aspect="auto",
                            title="% de vitória do ataque: compra do ataque × compra da defesa",
                            labels=dict(x="Compra da defesa", y="Compra do ataque", color="% ataque"))
            grafico(fig)

        e, d = st.columns(2)
        with e:
            fb = R.dropna(subset=["primeiro_abate_venceu"])
            conv = 100 * fb["primeiro_abate_venceu"].mean()
            st.metric("Time que faz o 1º abate vence o round", pct(conv))
            pos_pistol = []
            for mid_, grp in R.groupby("match_id"):
                grp = grp.set_index("round")
                for pr in (1, 13):
                    if pr in grp.index and pr + 1 in grp.index:
                        pos_pistol.append(grp.loc[pr, "vencedor"] == grp.loc[pr + 1, "vencedor"])
            st.metric("Quem vence o pistol também vence o round seguinte",
                      pct(100 * pd.Series(pos_pistol).mean() if pos_pistol else float("nan")))
            res = R["resultado"].replace({"Elimination": "Eliminação", "Detonate": "Spike explodiu",
                                          "Defuse": "Spike desarmada", "": "Tempo esgotado"})
            res = res.fillna("Tempo esgotado").value_counts().reset_index()
            res.columns = ["resultado", "rounds"]
            fig = px.bar(res, x="rounds", y="resultado", orientation="h", title="Como os rounds terminam",
                         color_discrete_sequence=[AZUL], labels={"resultado": ""})
            fig.update_yaxes(categoryorder="total ascending")
            grafico(fig, 300)
        with d:
            pl = R[R["plantou"]].groupby(["mapa", "site"]).agg(
                plants=("round", "count"), ataque_venceu=("lado_vencedor", lambda s: 100 * (s == "Ataque").mean())
            ).reset_index()
            fig = px.bar(pl, x="site", y="plants", facet_col="mapa", facet_col_wrap=4, hover_data=["ataque_venceu"],
                         title="Plants por site (hover: % de vitória do ataque após plantar)",
                         color_discrete_sequence=[LARANJA], labels={"site": "", "plants": "plants"})
            fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
            grafico(fig, 460)

        armas = (JR[~JR["arma"].isin(["Nenhuma"])].groupby("arma")
                 .agg(rounds=("round", "count"), win=("venceu_round", "mean")).reset_index())
        armas["win_pct"] = 100 * armas["win"]
        armas = armas[armas["rounds"] >= 30].sort_values("rounds", ascending=False)
        fig = px.bar(armas, x="arma", y="rounds", hover_data={"win_pct": ":.1f"},
                     title="Arma principal comprada (jogador × round) — hover mostra % de rounds vencidos",
                     color_discrete_sequence=[AZUL], labels={"arma": ""})
        grafico(fig, 340)

    # 6. mapa de abates
    with sub[5]:
        c = st.columns(4)
        mapa = c[0].selectbox("Mapa", K["mapa"].value_counts().index, key="mapa_explorar")
        o_que = c[1].radio("Mostrar posição", ["de quem morreu", "de quem matou"])
        lado_f = c[2].multiselect("Lado de quem matou", ["Ataque", "Defesa"], default=["Ataque", "Defesa"])
        modo = c[3].radio("Estilo", ["Pontos", "Calor"], key="modo_explorar")
        c2 = st.columns(3)
        km = K[(K["mapa"] == mapa) & ~K["fogo_amigo"] & K["killer_lado"].isin(lado_f)]
        times_m = sorted(km["killer_time"].dropna().unique())
        tsel = c2[0].multiselect("Time de quem matou", times_m)
        if tsel:
            km = km[km["killer_time"].isin(tsel)]
        jsel = c2[1].multiselect("Jogador que matou", sorted(km["killer_nome"].dropna().unique()))
        if jsel:
            km = km[km["killer_nome"].isin(jsel)]
        so_fk = c2[2].checkbox("Só primeiros abates do round")
        if so_fk:
            km = km[km["primeiro_abate"]]
        t_max = int(K["tempo_round_s"].max()) + 1
        faixa_t = st.slider("Segundos desde o início do round", 0, t_max, (0, t_max))
        km = km[km["tempo_round_s"].between(*faixa_t)]

        cx, cy = ("vitima_mx", "vitima_my") if o_que == "de quem morreu" else ("killer_mx", "killer_my")
        km = km.dropna(subset=[cx, cy])
        st.caption(f"{len(km)} abates")

        if modo == "Pontos":
            fig = px.scatter(km, x=cx, y=cy, color="killer_lado", color_discrete_map=LADO_CORES,
                             hover_data=["killer_nome", "vitima_nome", "arma", "round", "tempo_round_s"],
                             labels={"killer_lado": "Lado de quem matou"})
            fig.update_traces(marker=dict(size=8, opacity=0.75, line=dict(width=1, color="white")))
        else:
            fig = px.density_heatmap(km, x=cx, y=cy, nbinsx=40, nbinsy=40, color_continuous_scale=SEQ_AZUL,
                                     range_x=[0, 1], range_y=[0, 1])
        img = next((p for p in PASTA_MINIMAPAS.glob(f"{mapa}.*") if p.suffix.lower() in (".png", ".jpg", ".webp")), None)
        if img:
            from PIL import Image
            fig.add_layout_image(dict(source=Image.open(img), xref="x", yref="y", x=0, y=0, sizex=1, sizey=1,
                                      sizing="stretch", layer="below", opacity=0.9))
        fig.update_xaxes(range=[0, 1], showgrid=False, visible=False, constrain="domain")
        fig.update_yaxes(range=[1, 0], showgrid=False, visible=False, scaleanchor="x")  # y cresce para baixo
        fig.update_layout(height=720, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.02))
        st.plotly_chart(fig, width="stretch")
        if not img:
            st.caption(f"Sem imagem de fundo: coloque o minimapa em `minimapas/{mapa}.png` (quadrado) "
                       "e ele aparece atrás dos pontos.")

    # 7. tabelas
    with sub[6]:
        nome_tab = st.selectbox("Tabela", list(base.tabelas()))
        tab = base.tabelas()[nome_tab]
        tab = tab[tab["match_id"].isin(ids)]
        st.caption(f"{len(tab):,} linhas × {tab.shape[1]} colunas".replace(",", "."))
        st.dataframe(tab.head(5000), width="stretch", hide_index=True)
        st.download_button("Baixar CSV (com filtros)", tab.to_csv(index=False).encode("utf-8"),
                           file_name=f"{nome_tab}.csv", mime="text/csv")
