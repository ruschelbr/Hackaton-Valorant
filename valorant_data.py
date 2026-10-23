from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import referencias as ref

VERSAO_CACHE = 5  # aumente quando mudar o formato das tabelas
PASTA_CACHE = Path(__file__).resolve().parent / ".cache"

# RUSH2_030a_21-06-26_azure_bears_golden_13_x_9_ufmt_turuna_fracture.json
PADRAO_ARQUIVO = re.compile(
    r"^(?P<codigo>.+?)_(?P<dia>\d{2})-(?P<mes>\d{2})-(?P<ano>\d{2})_"
    r"(?P<time_a>.+)_(?P<placar_a>\d+)_x_(?P<placar_b>\d+)_(?P<time_b>.+)_(?P<mapa>[a-z]+)$"
)


@dataclass
class Base:
    partidas: pd.DataFrame
    times: pd.DataFrame
    rounds: pd.DataFrame
    jogadores: pd.DataFrame
    jogador_round: pd.DataFrame
    kills: pd.DataFrame
    dano: pd.DataFrame
    avisos: list = field(default_factory=list)

    def tabelas(self):
        return {
            "partidas": self.partidas, "times": self.times, "rounds": self.rounds,
            "jogadores": self.jogadores, "jogador_round": self.jogador_round,
            "kills": self.kills, "dano": self.dano,
        }


#utilidades

def _decodificar(texto: str) -> str:
    """'Univav#U00e1' -> 'Univavá' (o zip guardou acentos assim)."""
    return re.sub(r"#U([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), texto)


def _nome_time(slug: str) -> str:
    return slug.replace("_", " ").title()


def _minimapa(mapa, x, y):
    """Coordenada do jogo -> posição no minimapa (0 a 1). None se não houver."""
    conv = ref.MINIMAPA.get(mapa)
    if conv is None or x is None or y is None:
        return None, None
    xm, ym, xa, ya = conv
    mx, my = y * xm + xa, x * ym + ya
    if not (-0.05 <= mx <= 1.05 and -0.05 <= my <= 1.05):  # posições inválidas no JSON
        return None, None
    return mx, my


def _listar_jsons(alvo: Path):
    if alvo.is_file():
        return [alvo]
    return sorted(alvo.rglob("*.json"))


#leitura de 1 partida

def _ler_partida(caminho: Path, raiz: Path, avisos: list):
    with open(caminho, encoding="utf-8") as f:
        d = json.load(f)

    info = d["matchInfo"]
    mid = info["matchId"]
    mapa = ref.nome_mapa(info["mapId"])

    # campeonato / fase vêm das pastas; times vêm do nome do arquivo
    partes = [_decodificar(p) for p in caminho.relative_to(raiz).parts[:-1]] if caminho != raiz else []
    evento = partes[0] if partes else ""
    fase = " / ".join(partes[1:])

    placar = {t["teamId"]: t["roundsWon"] for t in d["teams"]}
    nomes = {"Red": "Red", "Blue": "Blue"}
    meta = PADRAO_ARQUIVO.match(caminho.stem)
    data_jogo = pd.to_datetime(info["gameStartMillis"], unit="ms", utc=True).tz_convert("America/Sao_Paulo")
    codigo = caminho.stem
    if meta:
        codigo = meta["codigo"]
        pa, pb = int(meta["placar_a"]), int(meta["placar_b"])
        ta, tb = _nome_time(meta["time_a"]), _nome_time(meta["time_b"])
        if placar.get("Red") == pa and placar.get("Blue") == pb:
            nomes = {"Red": ta, "Blue": tb}
        elif placar.get("Blue") == pa and placar.get("Red") == pb:
            nomes = {"Blue": ta, "Red": tb}
        else:
            avisos.append(f"{caminho.name}: placar do arquivo ({pa}x{pb}) não bate com o JSON {placar}; times ficaram como Red/Blue")
    else:
        avisos.append(f"{caminho.name}: nome fora do padrão; times ficaram como Red/Blue")

    vencedor_id = next((t["teamId"] for t in d["teams"] if t.get("won")), None)
    partida = {
        "match_id": mid, "arquivo": caminho.name, "evento": evento, "fase": fase, "codigo": codigo,
        "data": data_jogo, "mapa": mapa,
        "time_red": nomes["Red"], "time_blue": nomes["Blue"],
        "rounds_red": placar.get("Red"), "rounds_blue": placar.get("Blue"),
        "vencedor": nomes.get(vencedor_id, vencedor_id),
        "placar": f"{max(placar.values())}x{min(placar.values())}",
        "n_rounds": len(d["roundResults"]),
        "duracao_min": round(info["gameLengthMillis"] / 60000, 1),
        "versao_jogo": info["gameVersion"],
    }
    times = [
        {"match_id": mid, "team_id": t["teamId"], "time": nomes.get(t["teamId"], t["teamId"]),
         "adversario": nomes["Blue" if t["teamId"] == "Red" else "Red"],
         "rounds_ganhos": t["roundsWon"], "rounds_jogados": t["roundsPlayed"], "venceu": t["won"]}
        for t in d["teams"]
    ]

    # jogadores (ignora observadores, que ficam no time "Neutral")
    jog = {}
    for p in d["players"]:
        if p.get("isObserver") or p["teamId"] not in ("Red", "Blue") or p.get("stats") is None:
            continue
        agente, funcao = ref.nome_agente(p["characterId"])
        jog[p["puuid"]] = {
            "team_id": p["teamId"], "time": nomes[p["teamId"]],
            "nome": f'{p["gameName"]}#{p["tagLine"]}', "agente": agente, "funcao": funcao,
            "stats": p["stats"],
        }

    rounds, jr_linhas, kills_linhas, dano_linhas = [], [], [], []
    placar_corrente = {"Red": 0, "Blue": 0}

    for r in d["roundResults"]:
        rn = r["roundNum"]
        venc = r["winningTeam"]
        perd = "Blue" if venc == "Red" else "Red"
        atk = venc if r["winningTeamRole"] == "Attacker" else perd
        dfn = perd if atk == venc else venc
        lado = {atk: "Ataque", dfn: "Defesa"}

        # abates do round, em ordem de tempo
        ks = []
        for ps in r["playerStats"]:
            for k in ps["kills"] or []:
                ks.append(k)
        ks.sort(key=lambda k: k["timeSinceRoundStartMillis"])

        # morte pela própria spike não conta como morte nas estatísticas oficiais
        morte_t = {k["victim"]: k["timeSinceRoundStartMillis"] for k in ks
                   if (k.get("finishingDamage") or {}).get("damageType") != "Bomb"}
        assist_set = {a for k in ks for a in (k.get("assistants") or [])}
        killers_set = {k["killer"] for k in ks}
        trocados = set()  # vítimas cuja morte foi "trocada" por um aliado
        kill_trade = []   # este abate foi uma troca?
        for k in ks:
            t, kil, vit = k["timeSinceRoundStartMillis"], k["killer"], k["victim"]
            # a vítima foi vingada se o assassino dela morreu até JANELA ms depois
            # pelas mãos de um aliado da vítima
            for k2 in ks:
                if (k2["victim"] == kil and 0 <= k2["timeSinceRoundStartMillis"] - t <= ref.JANELA_TRADE_MS
                        and jog.get(k2["killer"], {}).get("team_id") == jog.get(vit, {}).get("team_id")):
                    trocados.add(vit)
                    break
        for k in ks:
            t, kil, vit = k["timeSinceRoundStartMillis"], k["killer"], k["victim"]
            eh_trade = any(
                k0["victim"] != vit and k0["killer"] == vit
                and 0 <= t - k0["timeSinceRoundStartMillis"] <= ref.JANELA_TRADE_MS
                and jog.get(k0["victim"], {}).get("team_id") == jog.get(kil, {}).get("team_id")
                for k0 in ks
            )
            kill_trade.append(eh_trade)

        primeiro = next((k for k in ks if k["killer"] in jog and k["victim"] in jog
                         and jog[k["killer"]]["team_id"] != jog[k["victim"]]["team_id"]), None)

        for i, k in enumerate(ks):
            kil, vit = k["killer"], k["victim"]
            fd = k.get("finishingDamage") or {}
            tipo = fd.get("damageType", "")
            if tipo == "Weapon" or tipo == "Melee":
                arma, cat = ref.nome_arma(fd.get("damageItem"))
                if arma == "Nenhuma":
                    arma, cat = "Desconhecida", "Outro"
            elif tipo == "Ability":
                arma, cat = ref.HABILIDADES.get(fd.get("damageItem"), "Habilidade"), "Habilidade"
            else:
                arma, cat = {"Bomb": "Spike", "Fall": "Queda", "Crush": "Esmagamento"}.get(tipo, tipo), "Outro"
            loc_k = next((pl["location"] for pl in (k.get("playerLocations") or []) if pl["puuid"] == kil), None)
            vx, vy = k["victimLocation"]["x"], k["victimLocation"]["y"]
            kx, ky = (loc_k["x"], loc_k["y"]) if loc_k else (None, None)
            vmx, vmy = _minimapa(mapa, vx, vy)
            kmx, kmy = _minimapa(mapa, kx, ky)
            jk, jv = jog.get(kil, {}), jog.get(vit, {})
            # coesão: aliados da vítima vivos no momento e distância até o mais próximo
            # (playerLocations traz todos os vivos menos a vítima; unidades do jogo = cm)
            dists = [math.dist((vx, vy), (pl["location"]["x"], pl["location"]["y"])) / 100
                     for pl in (k.get("playerLocations") or [])
                     if pl["puuid"] != vit and jog.get(pl["puuid"], {}).get("team_id") == jv.get("team_id")]
            dist_aliado = min(dists) if dists else None
            if dist_aliado is not None and dist_aliado > ref.DIST_MAX_VALIDA_M:
                dist_aliado = None  # coordenada inválida no JSON
            kills_linhas.append({
                "match_id": mid, "mapa": mapa, "round": rn + 1,
                "tempo_round_s": k["timeSinceRoundStartMillis"] / 1000,
                "killer": kil, "killer_nome": jk.get("nome"), "killer_time": jk.get("time"),
                "killer_agente": jk.get("agente"), "killer_lado": lado.get(jk.get("team_id")),
                "vitima": vit, "vitima_nome": jv.get("nome"), "vitima_time": jv.get("time"),
                "vitima_agente": jv.get("agente"), "vitima_lado": lado.get(jv.get("team_id")),
                "arma": arma, "categoria_arma": cat, "tipo_dano": tipo,
                "tiro_secundario": fd.get("isSecondaryFireMode", False),
                "n_assistencias": len(k.get("assistants") or []),
                "primeiro_abate": k is primeiro,
                "trade": kill_trade[i],
                "fogo_amigo": bool(jk) and bool(jv) and jk["team_id"] == jv["team_id"],
                "vitima_trocada": vit in trocados,
                "aliados_vivos": len(dists),
                "dist_aliado_m": None if dist_aliado is None else round(dist_aliado, 1),
                "vitima_x": vx, "vitima_y": vy, "killer_x": kx, "killer_y": ky,
                "vitima_mx": vmx, "vitima_my": vmy, "killer_mx": kmx, "killer_my": kmy,
            })

        # jogador x round
        valor_time = {"Red": 0, "Blue": 0}
        for ps in r["playerStats"]:
            pid = ps["puuid"]
            if pid not in jog:
                continue
            j = jog[pid]
            eco = ps.get("economy") or {}
            dmg_inimigo = hs = bs = ls = 0
            for dm in ps.get("damage") or []:
                rec = dm["receiver"]
                aliado = jog.get(rec, {}).get("team_id") == j["team_id"]
                dano_linhas.append({
                    "match_id": mid, "round": rn + 1, "atacante": pid, "receptor": rec,
                    "dano": dm["damage"], "headshots": dm["headshots"],
                    "bodyshots": dm["bodyshots"], "legshots": dm["legshots"], "fogo_amigo": aliado,
                })
                if not aliado:
                    dmg_inimigo += dm["damage"]
                    hs += dm["headshots"]; bs += dm["bodyshots"]; ls += dm["legshots"]
            n_kills = sum(1 for k in ks if k["killer"] == pid and jog.get(k["victim"], {}).get("team_id") != j["team_id"])
            morreu = pid in morte_t
            kast = (pid in killers_set) or (pid in assist_set) or (not morreu) or (pid in trocados)
            valor_time[j["team_id"]] += eco.get("loadoutValue", 0)
            arma, cat_arma = ref.nome_arma(eco.get("weapon"))
            jr_linhas.append({
                "match_id": mid, "round": rn + 1, "puuid": pid, "nome": j["nome"],
                "time": j["time"], "team_id": j["team_id"], "agente": j["agente"],
                "lado": lado[j["team_id"]], "venceu_round": j["team_id"] == venc,
                "kills": n_kills, "morreu": morreu,
                "assistencia": sum(1 for k in ks if pid in (k.get("assistants") or [])),
                "dano": dmg_inimigo, "headshots": hs, "bodyshots": bs, "legshots": ls,
                "score": ps.get("score", 0), "kast": kast,
                "primeiro_abate": primeiro is not None and primeiro["killer"] == pid,
                "primeira_morte": primeiro is not None and primeiro["victim"] == pid,
                "valor_equip": eco.get("loadoutValue", 0), "gasto": eco.get("spent", 0),
                "sobra": eco.get("remaining", 0), "arma": arma, "categoria_arma": cat_arma,
                "escudo": ref.ESCUDOS.get((eco.get("armor") or "").upper(), "Outro"),
            })

        placar_corrente[venc] += 1
        fb_time = jog[primeiro["killer"]]["time"] if primeiro else None
        rounds.append({
            "match_id": mid, "mapa": mapa, "round": rn + 1,
            "pistol": rn in (0, 12), "overtime": rn >= 24,
            "vencedor": nomes[venc], "perdedor": nomes[perd],
            "time_ataque": nomes[atk], "time_defesa": nomes[dfn],
            "lado_vencedor": "Ataque" if venc == atk else "Defesa",
            "resultado": r.get("roundResultCode") or r.get("roundResult"),
            "cerimonia": (r.get("roundCeremony") or "").replace("Ceremony", ""),
            "plantou": bool(r.get("bombPlanter")), "site": r.get("plantSite") or None,
            "tempo_plant_s": (r.get("plantRoundTime") or 0) / 1000 or None,
            "defusou": bool(r.get("bombDefuser")),
            "valor_ataque": valor_time[atk], "valor_defesa": valor_time[dfn],
            "compra_ataque": "Pistol" if rn in (0, 12) else ref.faixa_compra(valor_time[atk]),
            "compra_defesa": "Pistol" if rn in (0, 12) else ref.faixa_compra(valor_time[dfn]),
            "time_primeiro_abate": fb_time,
            "primeiro_abate_venceu": fb_time == nomes[venc] if fb_time else None,
            "placar_red": placar_corrente["Red"], "placar_blue": placar_corrente["Blue"],
            "n_abates": len(ks),
        })

    #  jogador x partida (estatísticas oficiais + derivadas dos rounds)
    jog_linhas = []
    for pid, j in jog.items():
        s = j["stats"]
        jog_linhas.append({
            "match_id": mid, "puuid": pid, "nome": j["nome"], "time": j["time"], "team_id": j["team_id"],
            "agente": j["agente"], "funcao": j["funcao"],
            "kills": s["kills"], "deaths": s["deaths"], "assists": s["assists"],
            "score": s["score"], "rounds": s["roundsPlayed"],
            "casts_c": s["abilityCasts"]["grenadeCasts"], "casts_q": s["abilityCasts"]["ability1Casts"],
            "casts_e": s["abilityCasts"]["ability2Casts"], "casts_ult": s["abilityCasts"]["ultimateCasts"],
            "venceu": j["team_id"] == vencedor_id,
        })

    return partida, times, rounds, jog_linhas, jr_linhas, kills_linhas, dano_linhas


#base completa

def _assinatura(arquivos):
    h = hashlib.sha1(str(VERSAO_CACHE).encode())
    for a in arquivos:
        st = a.stat()
        h.update(f"{a.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode())
    return h.hexdigest()[:16]


def carregar_base(alvo, usar_cache=True, progresso=None) -> Base:
    alvo = Path(alvo)
    arquivos = _listar_jsons(alvo)
    if not arquivos:
        raise FileNotFoundError(f"Nenhum .json encontrado em {alvo}")

    cache = PASTA_CACHE / f"base_{_assinatura(arquivos)}.pkl"
    if usar_cache and cache.exists():
        with open(cache, "rb") as f:
            return pickle.load(f)

    raiz = alvo if alvo.is_dir() else alvo.parent
    avisos = []
    acum = [[] for _ in range(7)]
    vistos = set()
    for i, arq in enumerate(arquivos):
        try:
            res = _ler_partida(arq, raiz, avisos)
        except Exception as e: 
            avisos.append(f"{arq.name}: erro ao ler ({type(e).__name__}: {e})")
            continue
        if res[0]["match_id"] in vistos:
            avisos.append(f"{arq.name}: partida duplicada, ignorada")
            continue
        vistos.add(res[0]["match_id"])
        acum[0].append(res[0])
        for lista, novos in zip(acum[1:], res[1:]):
            lista.extend(novos)
        if progresso:
            progresso(i + 1, len(arquivos))

    partidas, times, rounds, jogadores, jr, kills, dano = (pd.DataFrame(x) for x in acum)

    nick = jogadores.groupby("puuid")["nome"].agg(lambda s: s.value_counts().index[0])
    for df in (jogadores, jr):
        df["nome"] = df["puuid"].map(nick)
    kills["killer_nome"] = kills["killer"].map(nick)
    kills["vitima_nome"] = kills["vitima"].map(nick)

    agg = jr.groupby(["match_id", "puuid"]).agg(
        dano=("dano", "sum"), headshots=("headshots", "sum"), bodyshots=("bodyshots", "sum"),
        legshots=("legshots", "sum"), kast_rounds=("kast", "sum"),
        primeiros_abates=("primeiro_abate", "sum"), primeiras_mortes=("primeira_morte", "sum"),
        valor_equip_medio=("valor_equip", "mean"),
    ).reset_index()
    jogadores = jogadores.merge(agg, on=["match_id", "puuid"], how="left")
    jogadores = _metricas(jogadores)
    jogadores = jogadores.merge(partidas[["match_id", "mapa", "evento", "fase", "data"]], on="match_id")

    for df in (times, rounds, kills, jr):
        for col in ("evento", "fase", "data"):
            if col not in df.columns:
                df[col] = df["match_id"].map(partidas.set_index("match_id")[col])
    times["mapa"] = times["match_id"].map(partidas.set_index("match_id")["mapa"])
    partidas = partidas.sort_values("data").reset_index(drop=True)

    base = Base(partidas, times, rounds, jogadores, jr, kills, dano, avisos)
    if usar_cache:
        PASTA_CACHE.mkdir(exist_ok=True)
        for velho in PASTA_CACHE.glob("base_*.pkl"):
            velho.unlink()
        with open(cache, "wb") as f:
            pickle.dump(base, f)
    return base


def _metricas(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula ACS, K/D, ADR, KAST%, HS% a partir de colunas somadas."""
    df = df.copy()
    r = df["rounds"].where(df["rounds"] > 0)
    tiros = df["headshots"] + df["bodyshots"] + df["legshots"]
    df["acs"] = (df["score"] / r).round(1)
    df["kd"] = (df["kills"] / df["deaths"].where(df["deaths"] > 0, 1)).round(2)
    df["adr"] = (df["dano"] / r).round(1)
    df["kast_pct"] = (100 * df["kast_rounds"] / r).round(1)
    df["hs_pct"] = (100 * df["headshots"] / tiros.where(tiros > 0)).round(1)
    df["fk_menos_fd"] = df["primeiros_abates"] - df["primeiras_mortes"]
    return df


# ---------------------------------------------------------------- resumos prontos

def resumo_jogadores(jogadores: pd.DataFrame, min_rounds=0) -> pd.DataFrame:
    """Agrega a tabela `jogadores` (já filtrada) em 1 linha por jogador."""
    somas = ["kills", "deaths", "assists", "score", "rounds", "dano", "headshots",
             "bodyshots", "legshots", "kast_rounds", "primeiros_abates", "primeiras_mortes"]
    g = jogadores.groupby("puuid")
    res = g[somas].sum()
    res["nome"] = g["nome"].first()
    res["time"] = g["time"].agg(lambda s: s.value_counts().index[0])
    res["partidas"] = g["match_id"].nunique()
    res["vitorias"] = g["venceu"].sum()
    res["agente_principal"] = g["agente"].agg(lambda s: s.value_counts().index[0])
    res["agentes"] = g["agente"].agg(lambda s: ", ".join(s.value_counts().index[:3]))
    res = _metricas(res.reset_index())
    res["win_pct"] = (100 * res["vitorias"] / res["partidas"]).round(1)
    res = res[res["rounds"] >= min_rounds]
    cols = ["nome", "time", "partidas", "win_pct", "rounds", "agente_principal", "agentes",
            "acs", "kd", "kills", "deaths", "assists", "adr", "kast_pct", "hs_pct",
            "primeiros_abates", "primeiras_mortes", "fk_menos_fd", "puuid"]
    return res[cols].sort_values("acs", ascending=False).reset_index(drop=True)


def resumo_times(base: Base, match_ids=None) -> pd.DataFrame:
    """1 linha por time: vitórias, % de rounds, ataque/defesa, pistols, first kill."""
    t = base.times if match_ids is None else base.times[base.times["match_id"].isin(match_ids)]
    r = base.rounds if match_ids is None else base.rounds[base.rounds["match_id"].isin(match_ids)]

    res = t.groupby("time").agg(partidas=("match_id", "nunique"), vitorias=("venceu", "sum"),
                                rounds_ganhos=("rounds_ganhos", "sum"), rounds_jogados=("rounds_jogados", "sum"))
    res["win_pct"] = 100 * res["vitorias"] / res["partidas"]
    res["rounds_pct"] = 100 * res["rounds_ganhos"] / res["rounds_jogados"]

    def taxa(df, col_time, cond):
        tot = df.groupby(col_time).size()
        ganhos = df[cond(df)].groupby(col_time).size()
        return 100 * ganhos.reindex(tot.index, fill_value=0) / tot

    res["ataque_pct"] = taxa(r, "time_ataque", lambda d: d["lado_vencedor"] == "Ataque")
    res["defesa_pct"] = taxa(r, "time_defesa", lambda d: d["lado_vencedor"] == "Defesa")
    p = r[r["pistol"]]
    pist = pd.concat([p.assign(time=p["vencedor"], v=1), p.assign(time=p["perdedor"], v=0)])
    res["pistol_pct"] = 100 * pist.groupby("time")["v"].mean()
    fb = r.dropna(subset=["time_primeiro_abate"])
    res["fk_pct"] = 100 * pd.concat([fb.assign(time=fb["time_ataque"]), fb.assign(time=fb["time_defesa"])]) \
        .assign(v=lambda d: d["time"] == d["time_primeiro_abate"]).groupby("time")["v"].mean()
    fbt = fb[fb["time_primeiro_abate"].notna()]
    res["conversao_fk_pct"] = 100 * fbt.groupby("time_primeiro_abate")["primeiro_abate_venceu"].mean()
    return res.round(1).sort_values(["win_pct", "rounds_pct"], ascending=False).reset_index()


#terminal

def main():
    ap = argparse.ArgumentParser(description="Trata os JSONs de partidas de VALORANT.")
    ap.add_argument("alvo", help="arquivo .json ou pasta com os JSONs")
    ap.add_argument("--csv", type=Path, help="pasta para exportar todas as tabelas em CSV")
    ap.add_argument("--sem-cache", action="store_true")
    args = ap.parse_args()

    base = carregar_base(args.alvo, usar_cache=not args.sem_cache)
    p = base.partidas
    print(f"Partidas: {len(p)} | Rounds: {len(base.rounds)} | Abates: {len(base.kills)} | "
          f"Jogadores únicos: {base.jogadores['puuid'].nunique()} | Times: {base.times['time'].nunique()}")
    print("\nPartidas por evento/fase:")
    print(p.groupby(["evento", "fase"]).size().to_string())
    print("\nPartidas por mapa:")
    print(p["mapa"].value_counts().to_string())
    if base.avisos:
        print(f"\n{len(base.avisos)} aviso(s):")
        for a in base.avisos[:20]:
            print("  -", a)
    if args.csv:
        args.csv.mkdir(parents=True, exist_ok=True)
        for nome, df in base.tabelas().items():
            df.to_csv(args.csv / f"{nome}.csv", index=False)
        print(f"\nTabelas exportadas para {args.csv}/")


if __name__ == "__main__":
    main()
