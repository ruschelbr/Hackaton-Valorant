import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from valorant_data import carregar_base, resumo_jogadores, resumo_times

st.set_page_config(page_title="VALORANT • Explorador de partidas", layout="wide")

#paleta
AZUL, LARANJA, AQUA, CINZA = "#2a78d6", "#eb6834", "#1baf7a", "#8c8b86"
LADO_CORES = {"Ataque": LARANJA, "Defesa": AZUL}
SEQ_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
ORDEM_COMPRA = ["Pistol", "Eco", "Semi-eco", "Semi-compra", "Compra completa"]
PASTA_MINIMAPAS = Path(__file__).resolve().parent / "minimapas"


def grafico(fig, altura=380):
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=1.08, x=0, title=None))
    st.plotly_chart(fig, width="stretch")


def pct(x):
    return "–" if pd.isna(x) else f"{x:.1f}%"


#carregamento

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


st.sidebar.title("Dados")
fonte = st.sidebar.radio("Origem", ["Pasta local", "Enviar arquivos .json"], label_visibility="collapsed")
try:
    if fonte == "Pasta local":
        pasta = st.sidebar.text_input("Pasta com os JSONs (busca em subpastas)", "dados")
        base = base_da_pasta(pasta)
    else:
        ups = st.sidebar.file_uploader("Arquivos de partida", type="json", accept_multiple_files=True)
        if not ups:
            st.info("Envie um ou mais arquivos .json de partida na barra lateral.")
            st.stop()
        arquivos = tuple(sorted((u.name, u.getvalue()) for u in ups))
        chave = hashlib.sha1(b"".join(n.encode() + c for n, c in arquivos)).hexdigest()[:12]
        base = base_dos_uploads(chave, arquivos)
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

P = base.partidas

#filtros

st.sidebar.title("Filtros")
eventos = st.sidebar.multiselect("Evento", sorted(P["evento"].unique()))
p_f = P[P["evento"].isin(eventos)] if eventos else P
fases = st.sidebar.multiselect("Fase", sorted(f for f in p_f["fase"].unique() if f))
if fases:
    p_f = p_f[p_f["fase"].isin(fases)]
mapas = st.sidebar.multiselect("Mapa", sorted(p_f["mapa"].unique()))
if mapas:
    p_f = p_f[p_f["mapa"].isin(mapas)]
todos_times = sorted(set(p_f["time_red"]) | set(p_f["time_blue"]))
times_sel = st.sidebar.multiselect("Partidas dos times", todos_times)
if times_sel:
    p_f = p_f[p_f["time_red"].isin(times_sel) | p_f["time_blue"].isin(times_sel)]

ids = set(p_f["match_id"])
if not ids:
    st.warning("Nenhuma partida com esses filtros.")
    st.stop()

R = base.rounds[base.rounds["match_id"].isin(ids)]
J = base.jogadores[base.jogadores["match_id"].isin(ids)]
JR = base.jogador_round[base.jogador_round["match_id"].isin(ids)]
K = base.kills[base.kills["match_id"].isin(ids)]
T = base.times[base.times["match_id"].isin(ids)]

st.sidebar.caption(f"{len(ids)} de {len(P)} partidas selecionadas")
if base.avisos:
    with st.sidebar.expander(f"{len(base.avisos)} aviso(s) na leitura"):
        for a in base.avisos:
            st.write("•", a)

st.title("Explorador de partidas — VALORANT")

abas = st.tabs(["Visão geral", "Partida", "Times", "Jogadores", "Rounds e economia", "Mapa de abates", "Tabelas"])

#1. visão geral
with abas[0]:
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

#2. partida
with abas[1]:
    rot = p_f.sort_values("data", ascending=False).apply(
        lambda r: f'{r["data"]:%d/%m} · {r["time_red"]} {r["rounds_red"]} x {r["rounds_blue"]} {r["time_blue"]} · {r["mapa"]} · {r["evento"]} {r["fase"]}'.strip(),
        axis=1)
    escolha = st.selectbox("Partida", rot.index, format_func=lambda i: rot[i])
    pm = p_f.loc[escolha]
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

#3. times
with abas[2]:
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

#4. jogadores
with abas[3]:
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

        jog = st.selectbox("Detalhar jogador", rj.index, format_func=lambda i: f'{rj.loc[i, "nome"]} ({rj.loc[i, "time"]})')
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

#5. rounds e economia
with abas[4]:
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

#6. mapa de abates
with abas[5]:
    c = st.columns(4)
    mapa = c[0].selectbox("Mapa", K["mapa"].value_counts().index)
    o_que = c[1].radio("Mostrar posição", ["de quem morreu", "de quem matou"])
    lado_f = c[2].multiselect("Lado de quem matou", ["Ataque", "Defesa"], default=["Ataque", "Defesa"])
    modo = c[3].radio("Estilo", ["Pontos", "Calor"])
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

#7. tabelas
with abas[6]:
    nome_tab = st.selectbox("Tabela", list(base.tabelas()))
    tab = base.tabelas()[nome_tab]
    tab = tab[tab["match_id"].isin(ids)]
    st.caption(f"{len(tab):,} linhas × {tab.shape[1]} colunas".replace(",", "."))
    st.dataframe(tab.head(5000), width="stretch", hide_index=True)
    st.download_button("Baixar CSV (com filtros)", tab.to_csv(index=False).encode("utf-8"),
                       file_name=f"{nome_tab}.csv", mime="text/csv")
