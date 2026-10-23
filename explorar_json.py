import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path


#leitura

def carregar(caminho: Path):
    abrir = gzip.open if caminho.suffix == ".gz" else open
    with abrir(caminho, "rt", encoding="utf-8") as f:
        texto = f.read()
    try:
        return [json.loads(texto)]
    except json.JSONDecodeError:
        return [json.loads(l) for l in texto.splitlines() if l.strip()]


def listar_arquivos(alvo: Path):
    if alvo.is_file():
        return [alvo]
    padroes = ("*.json", "*.jsonl", "*.json.gz", "*.jsonl.gz")
    return sorted(p for pad in padroes for p in alvo.rglob(pad))


#schema

class Schema:
    def __init__(self, max_exemplos=3, max_itens=500):
        self.info = defaultdict(lambda: {"tipos": Counter(), "n": 0, "exemplos": [], "tamanhos": []})
        self.max_exemplos = max_exemplos
        self.max_itens = max_itens  # limita itens visitados por lista

    def visitar(self, valor, caminho="$"):
        d = self.info[caminho]
        d["n"] += 1
        d["tipos"][type(valor).__name__] += 1

        if isinstance(valor, dict):
            for k, v in valor.items():
                self.visitar(v, f"{caminho}.{k}")
        elif isinstance(valor, list):
            d["tamanhos"].append(len(valor))
            for item in valor[: self.max_itens]:
                self.visitar(item, f"{caminho}[]")
        else:
            if len(d["exemplos"]) < self.max_exemplos and valor not in d["exemplos"]:
                d["exemplos"].append(valor)

    def imprimir(self, profundidade_max=99):
        for caminho in sorted(self.info):
            nivel = caminho.count(".") + caminho.count("[]")
            if nivel > profundidade_max:
                continue
            d = self.info[caminho]
            tipos = "/".join(t for t, _ in d["tipos"].most_common())
            linha = f"{'  ' * nivel}{caminho}  <{tipos}>  n={d['n']}"
            if d["tamanhos"]:
                t = d["tamanhos"]
                linha += f"  len[min={min(t)} méd={sum(t) / len(t):.1f} máx={max(t)}]"
            if d["exemplos"]:
                ex = ", ".join(repr(e)[:40] for e in d["exemplos"])
                linha += f"  ex: {ex}"
            print(linha)


#extração para tabela

def partir(caminho: str):
    """'$.rounds[].kills[]' -> ['rounds', '[]', 'kills', '[]']"""
    partes = []
    for seg in caminho.lstrip("$").split("."):
        if not seg:
            continue
        nome = seg.replace("[]", "")
        if nome:
            partes.append(nome)
        partes.extend(["[]"] * seg.count("[]"))
    return partes


def pegar(valor, partes):
    if not partes:
        yield valor
        return
    p, resto = partes[0], partes[1:]
    if p == "[]":
        if isinstance(valor, list):
            for item in valor:
                yield from pegar(item, resto)
    elif isinstance(valor, dict) and p in valor:
        yield from pegar(valor[p], resto)


#main

def main():
    ap = argparse.ArgumentParser(description="Explora a estrutura de arquivos JSON.")
    ap.add_argument("alvo", type=Path, help="arquivo ou pasta")
    ap.add_argument("--profundidade", type=int, default=99, help="nível máximo mostrado")
    ap.add_argument("--max-exemplos", type=int, default=3)
    ap.add_argument("--extrair", help="caminho de uma lista de objetos, ex: '$.rounds[]'")
    ap.add_argument("--csv", type=Path, help="arquivo de saída para --extrair")
    args = ap.parse_args()

    arquivos = listar_arquivos(args.alvo)
    print(f"{len(arquivos)} arquivo(s) encontrado(s)\n")

    if args.extrair:
        import pandas as pd

        linhas = []
        for arq in arquivos:
            for doc in carregar(arq):
                for item in pegar(doc, partir(args.extrair)):
                    if isinstance(item, dict):
                        item = {**item, "_arquivo": arq.name}
                    linhas.append(item)
        df = pd.json_normalize(linhas)  # achata objetos aninhados em colunas a.b.c
        print(df.head(20).to_string())
        print(f"\n{len(df)} linhas x {len(df.columns)} colunas")
        if args.csv:
            df.to_csv(args.csv, index=False)
            print(f"Salvo em {args.csv}")
        return

    schema = Schema(max_exemplos=args.max_exemplos)
    for arq in arquivos:
        for doc in carregar(arq):
            schema.visitar(doc)
    schema.imprimir(args.profundidade)


if __name__ == "__main__":
    main()
