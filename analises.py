from __future__ import annotations

import math

import numpy as np
import pandas as pd

import referencias as ref
from valorant_data import resumo_jogadores

MIN_N = 10        # menor amostra para uma métrica aparecer no diagnóstico
ECO_FORCE = ["Eco", "Semi-eco", "Semi-compra"]
ECO_BAIXA = ["Eco", "Semi-eco"]


def fmt_pct(x, casas=0):
    return "–" if x is None or pd.isna(x) else f"{100 * x:.{casas}f}%"


#Tabelas-base

def tabela_time_round(rounds: pd.DataFrame) -> pd.DataFrame:
    """1 linha por (round, time): cada round aparece duas vezes, uma para cada lado."""
    cols = ["match_id", "mapa", "round", "pistol", "vencedor", "plantou", "site",
            "tempo_plant_s", "time_primeiro_abate"]
    partes = []
    for lado, eu, ele in (("Ataque", "ataque", "defesa"), ("Defesa", "defesa", "ataque")):
        x = rounds[cols].copy()
        x["lado"] = lado
        x["time"] = rounds[f"time_{eu}"].values
        x["adversario"] = rounds[f"time_{ele}"].values
        x["compra"] = rounds[f"compra_{eu}"].values
        x["compra_adv"] = rounds[f"compra_{ele}"].values
        x["valor"] = rounds[f"valor_{eu}"].values
        partes.append(x)
    tr = pd.concat(partes, ignore_index=True)
    tr["venceu"] = tr["time"] == tr["vencedor"]
    tr["fez_fk"] = tr["time_primeiro_abate"] == tr["time"]
    tr["sofreu_fk"] = tr["time_primeiro_abate"] == tr["adversario"]
    tr["force"] = tr["compra"] != "Eco"

    # resultado do pistol anterior (para os rounds 2 e 14)
    pist = tr.loc[tr["pistol"], ["match_id", "time", "round", "venceu"]].copy()
    pist["round"] += 1
    tr = tr.merge(pist.rename(columns={"venceu": "venceu_pistol_ant"}),
                  on=["match_id", "time", "round"], how="left")
    return tr.drop(columns="vencedor")


def tabela_mortes(kills: pd.DataFrame) -> pd.DataFrame:
    """Mortes causadas por inimigos (sem fogo amigo, spike ou queda sem autor)."""
    m = kills[~kills["fogo_amigo"] & kills["killer_time"].notna() & kills["vitima_time"].notna()
              & (kills["tipo_dano"] != "Bomb")].copy()
    m["time"] = m["vitima_time"]
    m["com_aliado"] = m["aliados_vivos"] > 0
    m["isolada"] = m["dist_aliado_m"] > ref.LIMIAR_ISOLADO_M
    return m


#Métricas de time

# Cada métrica: de qual tabela vem, quais linhas entram (filtro), o que é sucesso,
# se valor alto é bom, a frase (sujeito + verbo) e a dica quando é ponto fraco.
METRICAS = [
    dict(chave="ataque", nome="Rounds de ataque", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: d["lado"] == "Ataque",
         frase="vencem {v} dos rounds de ataque",
         dica="Revisem as execuções: quem abre espaço, em que ordem o utilitário entra e se o "
              "time chega junto no site. Comparem rounds de ataque vencidos e perdidos na aba Partida."),
    dict(chave="defesa", nome="Rounds de defesa", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: d["lado"] == "Defesa",
         frase="vencem {v} dos rounds de defesa",
         dica="Revisem o setup (posições iniciais) e o tempo das rotações. O mapa de abates mostra "
              "onde vocês mais morrem defendendo."),
    dict(chave="pistol", nome="Pistols", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: d["pistol"],
         frase="vencem {v} dos pistols",
         dica="Tenham 1 ou 2 estratégias fixas de pistol por lado. O pistol decide a economia dos "
              "3 rounds seguintes."),
    dict(chave="pos_pistol", nome="Round após pistol vencido", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: d["venceu_pistol_ant"] == True,  # noqa: E712
         frase="vencem {v} dos rounds seguintes a um pistol vencido",
         dica="No round bônus o adversário está sem dinheiro: joguem em distância e juntos, sem "
              "dar duelos de perto para pistolas e shotguns."),
    dict(chave="abre_round", nome="Fazer o 1º abate", fonte="tr", sucesso="fez_fk", alto_bom=True,
         filtro=lambda d: d["time_primeiro_abate"].notna(),
         frase="fazem o 1º abate em {v} dos rounds",
         dica="O time sai atrás com frequência. Revisem quem toma o duelo de abertura e se ele "
              "recebe utilitário (flash, info) antes do peek."),
    dict(chave="converte_fk", nome="Converter o 1º abate", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: d["fez_fk"],
         frase="vencem {v} dos rounds em que fazem o 1º abate",
         dica="Vocês desperdiçam a vantagem numérica. Com 5 contra 4, joguem pelo número: "
              "andem juntos, troquem mortes e não forcem duelos isolados."),
    dict(chave="recupera_fk", nome="Recuperar após sofrer o 1º abate", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: d["sofreu_fk"],
         frase="vencem {v} dos rounds em que sofrem o 1º abate",
         dica="Depois de sair atrás, evitem reagir um por vez. Reagrupem e joguem o round com 4, "
              "usando o utilitário que sobrou."),
    dict(chave="pos_plant", nome="Pós-plant (ataque)", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: (d["lado"] == "Ataque") & d["plantou"],
         frase="vencem {v} dos rounds de ataque em que plantam a spike",
         dica="Treinem posições de pós-plant com cruzadas e guardem utilitário para impedir o defuse."),
    dict(chave="retake", nome="Retake (defesa)", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: (d["lado"] == "Defesa") & d["plantou"],
         frase="vencem {v} dos rounds de defesa em que o adversário planta",
         dica="Treinem retakes: esperem os aliados e o utilitário e entrem juntos, não um por vez."),
    dict(chave="anti_eco", nome="Anti-eco", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: (d["compra"] == "Compra completa") & d["compra_adv"].isin(ECO_BAIXA),
         frase="vencem {v} dos rounds com compra completa contra eco/semi-eco",
         dica="Perder anti-eco custa caro. Joguem em distância e em grupo; nada de peek individual "
              "em ângulo fechado contra shotgun."),
    dict(chave="eco_force", nome="Eco/force contra compra completa", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: ~d["pistol"] & d["compra"].isin(ECO_FORCE) & (d["compra_adv"] == "Compra completa"),
         frase="vencem {v} dos rounds de eco/force contra compra completa",
         dica="Round econômico precisa de plano: stack em um site, jogo de perto e foco em pegar "
              "armas para o round seguinte."),
    dict(chave="full_vs_full", nome="Compra completa contra compra completa", fonte="tr", sucesso="venceu", alto_bom=True,
         filtro=lambda d: (d["compra"] == "Compra completa") & (d["compra_adv"] == "Compra completa"),
         frase="vencem {v} dos rounds em que os dois times estão com compra completa",
         dica="Com economia igual, decide a execução coletiva. É o melhor termômetro do nível do time; "
              "revisem esses rounds em VOD primeiro."),
    dict(chave="trade", nome="Mortes trocadas", fonte="mortes", sucesso="vitima_trocada", alto_bom=True,
         filtro=lambda d: d["com_aliado"],
         frase="trocam {v} das mortes (um aliado mata o assassino em até 5 s)",
         dica="Joguem mais perto uns dos outros. Morte sem troca dá vantagem numérica de graça "
              "(veja a aba Coesão)."),
    dict(chave="isolado", nome="Mortes isoladas", fonte="mortes", sucesso="isolada", alto_bom=False,
         filtro=lambda d: d["com_aliado"] & d["dist_aliado_m"].notna(),
         frase=f"morrem com o aliado mais próximo a mais de {ref.LIMIAR_ISOLADO_M} m em {{v}} das mortes",
         dica="Reduzam lurks e rotações solo sem informação. Quem morre longe do time quase nunca "
              "é trocado."),
]
METRICA = {m["chave"]: m for m in METRICAS}


def metricas_por_time(tr: pd.DataFrame, mortes: pd.DataFrame) -> pd.DataFrame:
    """Tabela longa: 1 linha por (time, métrica) com sucessos, n, taxa, taxa da base,
    z-score e percentil entre os times."""
    partes = []
    for m in METRICAS:
        df = tr if m["fonte"] == "tr" else mortes
        sel = df[m["filtro"](df).fillna(False).astype(bool)]
        g = sel.groupby("time")[m["sucesso"]].agg(sucessos="sum", n="count").reset_index()
        g["chave"] = m["chave"]
        partes.append(g)
    res = pd.concat(partes, ignore_index=True)
    res["sucessos"] = res["sucessos"].astype(float)
    res["taxa"] = res["sucessos"] / res["n"]

    tot = res.groupby("chave")[["sucessos", "n"]].sum()
    res["taxa_base"] = res["chave"].map(tot["sucessos"] / tot["n"])
    p0 = res["taxa_base"].clip(0.001, 0.999)
    res["z"] = (res["taxa"] - p0) / np.sqrt(p0 * (1 - p0) / res["n"])
    sinal = res["chave"].map({m["chave"]: 1 if m["alto_bom"] else -1 for m in METRICAS})
    res["z_bom"] = res["z"] * sinal  # positivo = melhor que a base

    ok = res["n"] >= MIN_N
    res["percentil"] = np.nan
    res.loc[ok, "percentil"] = (res[ok].assign(v=res["taxa"] * sinal)
                                .groupby("chave")["v"].rank(pct=True) * 100).round(0)
    res["nome"] = res["chave"].map({m["chave"]: m["nome"] for m in METRICAS})
    res["alto_bom"] = res["chave"].map({m["chave"]: m["alto_bom"] for m in METRICAS})
    return res


def _nivel(z):
    a = abs(z)
    if a >= 2:
        return "diferença forte"
    if a >= 1:
        return "diferença moderada"
    return "diferença leve (pode ser acaso)"


def diagnostico(met: pd.DataFrame, time: str, sujeito="Vocês", qtd=3):
    """Retorna (fortes, oportunidades, tabela_completa) para um time."""
    d = met[(met["time"] == time) & (met["n"] >= MIN_N)].copy()
    if d.empty:
        return d, d, d
    d["texto"] = d.apply(lambda r: (
        f'{sujeito} {METRICA[r["chave"]]["frase"].format(v=fmt_pct(r["taxa"]))} '
        f'(média da base: {fmt_pct(r["taxa_base"])}, n = {int(r["n"])})'), axis=1)
    d["nivel"] = d["z"].map(_nivel)
    d["dica"] = d["chave"].map(lambda c: METRICA[c]["dica"])
    # só entra como ponto forte/fraco se estiver do mesmo lado da base E da mediana dos times
    fortes = d[(d["z_bom"] > 0) & (d["percentil"] > 50)].nlargest(qtd, "z_bom")
    fracos = d[(d["z_bom"] < 0) & (d["percentil"] < 50)].nsmallest(qtd, "z_bom")
    return fortes, fracos, d.sort_values("z_bom", ascending=False)


#Coesão

def coesao_times(mortes: pd.DataFrame, min_mortes=40) -> pd.DataFrame:
    m = mortes[mortes["com_aliado"]]
    g = m.groupby("time").agg(
        mortes=("vitima_trocada", "size"), trocadas=("vitima_trocada", "sum"),
        isoladas=("isolada", "sum"), dist_mediana_m=("dist_aliado_m", "median"))
    g["trade_pct"] = 100 * g["trocadas"] / g["mortes"]
    g["isolado_pct"] = 100 * g["isoladas"] / g["mortes"]
    ok = g["mortes"] >= min_mortes
    nota = (g.loc[ok, "trade_pct"].rank(pct=True) + (-g.loc[ok, "isolado_pct"]).rank(pct=True)) / 2 * 100
    g["nota_coesao"] = nota.round(0)
    return g.round(1).reset_index().sort_values("nota_coesao", ascending=False)


def coesao_jogadores(mortes: pd.DataFrame, time=None) -> pd.DataFrame:
    m = mortes[mortes["com_aliado"]]
    if time is not None:
        m = m[m["time"] == time]
    g = m.groupby(["vitima", "vitima_nome"]).agg(
        mortes=("vitima_trocada", "size"), trocadas=("vitima_trocada", "sum"),
        isoladas=("isolada", "sum"), dist_mediana_m=("dist_aliado_m", "median"),
        agente=("vitima_agente", lambda s: s.value_counts().index[0]))
    g["trade_pct"] = 100 * g["trocadas"] / g["mortes"]
    g["isolado_pct"] = 100 * g["isoladas"] / g["mortes"]
    return g.round(1).reset_index().rename(columns={"vitima": "puuid", "vitima_nome": "nome"}) \
        .sort_values("isolado_pct", ascending=False)


FAIXAS_DIST = [0, 5, 10, 15, 20, 30, 50, ref.DIST_MAX_VALIDA_M]


def trade_por_distancia(mortes: pd.DataFrame) -> pd.DataFrame:
    m = mortes[mortes["com_aliado"] & mortes["dist_aliado_m"].notna()].copy()
    m["faixa"] = pd.cut(m["dist_aliado_m"], FAIXAS_DIST)
    g = m.groupby("faixa", observed=True)["vitima_trocada"].agg(mortes="size", trade_pct="mean").reset_index()
    g["trade_pct"] = (100 * g["trade_pct"]).round(1)
    g["faixa"] = g["faixa"].map(lambda i: f"{int(i.left)}–{int(i.right)} m" if i.right < ref.DIST_MAX_VALIDA_M
                                else f"+{int(i.left)} m")
    return g


#Perfil por função

METRICAS_JOGADOR = [
    # coluna, nome, alto_bom, formato
    ("acs", "ACS", True, "{:.0f}"),
    ("kast_pct", "KAST %", True, "{:.0f}%"),
    ("adr", "ADR", True, "{:.0f}"),
    ("kd", "K/D", True, "{:.2f}"),
    ("hs_pct", "HS %", True, "{:.0f}%"),
    ("fk_por_round", "1º abates por round", True, "{:.2f}"),
    ("fd_por_round", "1ª mortes por round", False, "{:.2f}"),
    ("trade_pct", "Mortes trocadas %", True, "{:.0f}%"),
    ("isolado_pct", "Mortes isoladas %", False, "{:.0f}%"),
    ("acs_cv", "Variação do ACS entre partidas", False, "{:.2f}"),
]


def perfil_jogadores(jogadores: pd.DataFrame, mortes: pd.DataFrame) -> pd.DataFrame:
    """resumo_jogadores + função principal, consistência e coesão individual."""
    rj = resumo_jogadores(jogadores)
    g = jogadores.groupby("puuid")
    rj["funcao"] = rj["puuid"].map(g["funcao"].agg(lambda s: s.value_counts().index[0]))
    acs_partidas = g["acs"]
    cv = acs_partidas.std() / acs_partidas.mean()
    cv[g["match_id"].nunique() < 3] = np.nan  # consistência só com 3+ partidas
    rj["acs_cv"] = rj["puuid"].map(cv).round(2)
    rj["fk_por_round"] = (rj["primeiros_abates"] / rj["rounds"]).round(3)
    rj["fd_por_round"] = (rj["primeiras_mortes"] / rj["rounds"]).round(3)
    co = coesao_jogadores(mortes).set_index("puuid")
    rj["trade_pct"] = rj["puuid"].map(co["trade_pct"])
    rj["isolado_pct"] = rj["puuid"].map(co["isolado_pct"])
    return rj


def percentis_jogador(perfil: pd.DataFrame, puuid: str, min_rounds=100) -> pd.DataFrame:
    eu = perfil.set_index("puuid").loc[puuid]
    pool = perfil[(perfil["funcao"] == eu["funcao"]) & (perfil["rounds"] >= min_rounds)]
    linhas = []
    for col, nome, alto_bom, fmt in METRICAS_JOGADOR:
        v = eu[col]
        vals = pool[col].dropna()
        if pd.isna(v) or len(vals) < 5:
            continue
        menor = (vals < v).mean() + 0.5 * (vals == v).mean()
        p = 100 * (menor if alto_bom else 1 - menor)
        linhas.append({"metrica": nome, "valor": fmt.format(v), "mediana_funcao": fmt.format(vals.median()),
                       "percentil": round(p), "alto_bom": alto_bom, "n_comparados": len(vals)})
    return pd.DataFrame(linhas)


def frases_jogador(pct: pd.DataFrame, funcao: str, qtd=2):
    if pct.empty:
        return [], []
    plural = {"Duelista": "duelistas", "Iniciador": "iniciadores", "Controlador": "controladores",
              "Sentinela": "sentinelas"}.get(funcao, "jogadores da mesma função")
    def frase(r):
        return f'{r["metrica"]}: {r["valor"]} (mediana dos {plural}: {r["mediana_funcao"]}), percentil {r["percentil"]}'
    fortes = [frase(r) for _, r in pct.nlargest(qtd, "percentil").iterrows() if r["percentil"] >= 60]
    fracos = [frase(r) for _, r in pct.nsmallest(qtd, "percentil").iterrows() if r["percentil"] <= 40]
    return fortes, fracos


#Dossiê do adversário

def sites_de_plant(tr: pd.DataFrame, time: str, mapa=None) -> pd.DataFrame:
    a = tr[(tr["time"] == time) & (tr["lado"] == "Ataque")]
    if mapa:
        a = a[a["mapa"] == mapa]
    p = a[a["plantou"] & a["site"].notna()]
    if p.empty:
        return pd.DataFrame(columns=["mapa", "site", "plants", "pct_dos_plants", "vitoria_pct", "tempo_medio_s"])
    s = p.groupby(["mapa", "site"]).agg(plants=("round", "size"), vitoria_pct=("venceu", "mean"),
                                        tempo_medio_s=("tempo_plant_s", "mean")).reset_index()
    s["pct_dos_plants"] = 100 * s["plants"] / s.groupby("mapa")["plants"].transform("sum")
    s["vitoria_pct"] *= 100
    rounds_atk = a.groupby("mapa").size()
    s["rounds_ataque"] = s["mapa"].map(rounds_atk)
    return s.round(1).sort_values(["mapa", "plants"], ascending=[True, False])


def tempo_de_plant(tr: pd.DataFrame, time: str, mapa=None):
    """(mediana do time, mediana da base nos mesmos mapas, n)."""
    p = tr[(tr["lado"] == "Ataque") & tr["plantou"] & tr["tempo_plant_s"].notna()]
    eu = p[p["time"] == time]
    mapas = [mapa] if mapa else eu["mapa"].unique()
    if mapa:
        eu = eu[eu["mapa"] == mapa]
    base = p[p["mapa"].isin(mapas)]
    return eu["tempo_plant_s"].median(), base["tempo_plant_s"].median(), len(eu)


def compra_pos_pistol_perdido(tr: pd.DataFrame, time: str):
    """(% de force do time, % de force da base, n, % de vitória da base com force, sem force)."""
    x = tr[tr["venceu_pistol_ant"] == False]  # noqa: E712
    eu = x[x["time"] == time]
    return (eu["force"].mean(), x["force"].mean(), len(eu),
            x.loc[x["force"], "venceu"].mean(), x.loc[~x["force"], "venceu"].mean())


def composicoes(jogadores: pd.DataFrame, time: str, mapa=None) -> pd.DataFrame:
    j = jogadores[jogadores["time"] == time]
    if mapa:
        j = j[j["mapa"] == mapa]
    c = j.groupby(["match_id", "mapa"])["agente"].apply(lambda s: ", ".join(sorted(s))).reset_index()
    return (c.groupby(["mapa", "agente"]).size().reset_index(name="partidas")
            .rename(columns={"agente": "composição"}).sort_values("partidas", ascending=False))


def jogadores_chave(jogadores: pd.DataFrame, kills: pd.DataFrame, time: str) -> dict:
    rj = resumo_jogadores(jogadores[jogadores["time"] == time])
    rj = rj[rj["rounds"] >= max(20, rj["rounds"].max() * 0.3)]  # ignora reservas que jogaram pouco
    out = {"tabela": rj}
    if rj.empty:
        return out
    out["estrela"] = rj.nlargest(1, "acs").iloc[0]
    tot_fk = rj["primeiros_abates"].sum()
    e = rj.nlargest(1, "primeiros_abates").iloc[0]
    out["entry"] = e
    out["entry_share"] = e["primeiros_abates"] / tot_fk if tot_fk else np.nan
    k = kills[(kills["killer_time"] == time) & ~kills["fogo_amigo"]]
    op = k[k["arma"] == "Operator"].groupby("killer_nome").size()
    if len(op):
        nome = op.idxmax()
        total_jog = (k["killer_nome"] == nome).sum()
        out["awper"] = (nome, int(op.max()), op.max() / total_jog if total_jog else 0)
    return out


def plano_de_jogo(tr, met, jogadores, kills, time, mapa=None) -> list[str]:
    """Regras simples que viram recomendações contra o time `time`."""
    plano = []

    # 1. site preferido
    s = sites_de_plant(tr, time, mapa)
    if not s.empty:
        top = s.sort_values("plants", ascending=False).groupby("mapa").head(1)
        for _, r in top.iterrows():
            tot = s.loc[s["mapa"] == r["mapa"], "plants"].sum()
            if tot >= 6 and r["pct_dos_plants"] >= 45:
                plano.append(f'No {r["mapa"]}, {r["pct_dos_plants"]:.0f}% dos plants deles são no site '
                             f'{r["site"]} (n = {int(tot)}). Reforcem o {r["site"]} ou deixem o retake '
                             f'preparado ali.')
            if not mapa and len(plano) >= 2:
                break

    # 2. ritmo de execução
    eu, base, n = tempo_de_plant(tr, time, mapa)
    if n >= 8 and pd.notna(eu) and pd.notna(base):
        if eu <= base - 6:
            plano.append(f"Executam rápido: plantam aos {eu:.0f} s (mediana; base nos mesmos mapas: "
                         f"{base:.0f} s, n = {n}). Busquem informação cedo e não deixem um site com 1 jogador só.")
        elif eu >= base + 6:
            plano.append(f"Jogam devagar: plantam aos {eu:.0f} s (mediana; base: {base:.0f} s, n = {n}). "
                         "Não rotacionem cedo e cuidado com lurk no fim do round.")

    # 3. compra depois de perder o pistol
    f_eu, f_base, n, _, _ = compra_pos_pistol_perdido(tr, time)
    if n >= 4 and pd.notna(f_eu):
        if f_eu >= max(0.4, f_base + 0.2):
            plano.append(f"Depois de perder o pistol fazem force em {fmt_pct(f_eu)} das vezes (base: "
                         f"{fmt_pct(f_base)}, n = {n}). No round 2, joguem em distância e com escudo.")
        elif f_eu <= 0.1:
            plano.append(f"Depois de perder o pistol quase sempre salvam (force em {fmt_pct(f_eu)}, n = {n}). "
                         "No round 2, joguem o anti-eco com calma e em grupo.")

    # 4. jogadores-chave
    jc = jogadores_chave(jogadores, kills, time)
    if "entry" in jc and pd.notna(jc.get("entry_share")) and jc["entry_share"] >= 0.28:
        e = jc["entry"]
        plano.append(f'{e["nome"]} ({e["agente_principal"]}) faz {fmt_pct(jc["entry_share"])} dos 1º abates '
                     f'deles. Neguem o duelo de abertura dele (utilitário, posição recuada) e troquem rápido.')
    if "awper" in jc:
        nome, n_op, share = jc["awper"]
        if n_op >= 10 and share >= 0.2:
            plano.append(f"{nome} é o AWPer: {n_op} abates de Operator ({fmt_pct(share)} dos abates dele). "
                         "Usem smoke e flash nas linhas longas e evitem peek seco.")

    # 5. pontos fracos do diagnóstico deles
    _, fracos, _ = diagnostico(met, time, sujeito="Eles", qtd=2)
    for _, r in fracos.iterrows():
        if r["z_bom"] <= -1:
            plano.append(f'Ponto fraco para explorar: {r["texto"]}.')
    return plano


#Relatório

def relatorio_markdown(time, fortes, fracos, coesao=None, jogadores_time=None,
                       adversario=None, plano=None, escopo="") -> str:
    L = [f"# Relatório pós-partida — {time}", ""]
    if escopo:
        L += [f"_Base analisada: {escopo}_", ""]
    L += ["## Pontos fortes", ""]
    L += [f"- {r['texto']} — {r['nivel']}" for _, r in fortes.iterrows()] or ["- (nenhum destaque com amostra suficiente)"]
    L += ["", "## Oportunidades de melhoria", ""]
    for _, r in fracos.iterrows():
        L += [f"- {r['texto']} — {r['nivel']}", f"  - Sugestão: {r['dica']}"]
    if fracos.empty:
        L += ["- (nenhuma oportunidade com amostra suficiente)"]
    if coesao is not None:
        L += ["", "## Coesão", "",
              f"- Mortes trocadas: {coesao['trade_pct']:.0f}% · mortes isoladas (+{ref.LIMIAR_ISOLADO_M} m): "
              f"{coesao['isolado_pct']:.0f}% · nota de coesão: {coesao['nota_coesao']:.0f}/100"]
    if jogadores_time is not None and len(jogadores_time):
        L += ["", "## Jogadores", "", "| Jogador | Agente | ACS | K/D | KAST % | Mortes isoladas % |", "|---|---|---|---|---|---|"]
        for _, r in jogadores_time.iterrows():
            iso = "–" if pd.isna(r.get("isolado_pct")) else f"{r['isolado_pct']:.0f}"
            L += [f"| {r['nome']} | {r['agente_principal']} | {r['acs']:.0f} | {r['kd']:.2f} | {r['kast_pct']:.0f} | {iso} |"]
    if adversario and plano is not None:
        L += ["", f"## Plano de jogo contra {adversario}", ""]
        L += [f"- {p}" for p in plano] or ["- (amostra insuficiente para recomendações)"]
    L += ["", "---", "Metodologia: cada taxa é comparada com a taxa da base inteira; o z-score binomial "
          "indica o quanto a diferença é confiável (|z| ≥ 2 forte, ≥ 1 moderada)."]
    return "\n".join(L)
