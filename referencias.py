# characterId -> (nome, função)
AGENTES = {
    "add6443a-41bd-e414-f6ad-e58d267f4e95": ("Jett", "Duelista"),
    "f94c3b30-42be-e959-889c-5aa313dba261": ("Raze", "Duelista"),
    "eb93336a-449b-9c1b-0a54-a891f7921d69": ("Phoenix", "Duelista"),
    "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc": ("Reyna", "Duelista"),
    "7f94d92c-4234-0a36-9646-3a87eb8b5c89": ("Yoru", "Duelista"),
    "bb2a4828-46eb-8cd1-e765-15848195d751": ("Neon", "Duelista"),
    "0e38b510-41a8-5780-5e8f-568b2a4f2d6c": ("Iso", "Duelista"),
    "df1cb487-4902-002e-5c17-d28e83e78588": ("Waylay", "Duelista"),
    "320b2a48-4d9b-a075-30f1-1f93a9b638fa": ("Sova", "Iniciador"),
    "5f8d3a7f-467b-97f3-062c-13acf203c006": ("Breach", "Iniciador"),
    "6f2a04ca-43e0-be17-7f36-b3908627744d": ("Skye", "Iniciador"),
    "601dbbe7-43ce-be57-2a40-4abd24953621": ("KAY/O", "Iniciador"),
    "dade69b4-4f5a-8528-247b-219e5a1facd6": ("Fade", "Iniciador"),
    "e370fa57-4757-3604-3648-499e1f642d3f": ("Gekko", "Iniciador"),
    "b444168c-4e35-8076-db47-ef9bf368f384": ("Tejo", "Iniciador"),
    "8e253930-4c05-31dd-1b6c-968525494517": ("Omen", "Controlador"),
    "9f0d8ba9-4140-b941-57d3-a7ad57c6b417": ("Brimstone", "Controlador"),
    "707eab51-4836-f488-046a-cda6bf494859": ("Viper", "Controlador"),
    "41fb69c1-4189-7b37-f117-bcaf1e96f1bf": ("Astra", "Controlador"),
    "95b78ed7-4637-86d9-7e41-71ba8c293152": ("Harbor", "Controlador"),
    "1dbf2edd-4729-0984-3115-daa5eed44993": ("Clove", "Controlador"),
    "7c8a4701-4de6-9355-b254-e09bc2a34b72": ("Miks", "Controlador"),
    "117ed9e3-49f3-6512-3ccf-0cada7e3823b": ("Cypher", "Sentinela"),
    "1e58de9c-4950-5125-93e9-a0aee9f98746": ("Killjoy", "Sentinela"),
    "569fdd95-4d10-43ab-ca70-79becc718b46": ("Sage", "Sentinela"),
    "22697a3d-45bf-8dd7-4fec-84a9e28c69d7": ("Chamber", "Sentinela"),
    "cc8b64c8-4b25-4ff9-6e7f-37b4da43d235": ("Deadlock", "Sentinela"),
    "efba5359-4016-a1e5-7626-b1ae76895940": ("Vyse", "Sentinela"),
    "92eeef5d-43b5-1d4a-8d03-b3927a09034b": ("Veto", "Sentinela"),
}

# weapon / damageItem (sempre comparado em MAIÚSCULAS) -> (nome, categoria)
ARMAS = {
    "2F59173C-4BED-B6C3-2191-DEA9B58BE9C7": ("Faca", "Corpo a corpo"),
    "29A0CFAB-485B-F5D5-779A-B59F85E204A8": ("Classic", "Pistola"),
    "42DA8CCC-40D5-AFFC-BEEC-15AA47B42EDA": ("Shorty", "Pistola"),
    "44D4E95C-4157-0037-81B2-17841BF2E8E3": ("Frenzy", "Pistola"),
    "1BAA85B4-4C70-1284-64BB-6481DFC3BB4E": ("Ghost", "Pistola"),
    "410B2E0B-4CEB-1321-1727-20858F7F3477": ("Bandit", "Pistola"),
    "E336C6B8-418D-9340-D77F-7A9E4CFE0702": ("Sheriff", "Pistola"),
    "F7E1B454-4AD4-1063-EC0A-159E56B58941": ("Stinger", "SMG"),
    "462080D1-4035-2937-7C09-27AA2A5C27A7": ("Spectre", "SMG"),
    "910BE174-449B-C412-AB22-D0873436B21B": ("Bucky", "Escopeta"),
    "EC845BF4-4F79-DDDA-A3DA-0DB3774B2794": ("Judge", "Escopeta"),
    "AE3DE142-4D85-2547-DD26-4E90BED35CF7": ("Bulldog", "Rifle"),
    "4ADE7FAA-4CF1-8376-95EF-39884480959B": ("Guardian", "Rifle"),
    "EE8E8D15-496B-07AC-E5F6-8FAE5D4C7B1A": ("Phantom", "Rifle"),
    "9C82E19D-4575-0200-1A81-3EACF00CF872": ("Vandal", "Rifle"),
    "C4883E50-4494-202C-3EC3-6B8A9284F00B": ("Marshal", "Sniper"),
    "5F0AAF7A-4289-3998-D5FF-EB9A5CF7EF5C": ("Outlaw", "Sniper"),
    "A03B24D3-4319-996D-0F8C-94BBFBA1DFC7": ("Operator", "Sniper"),
    "55D8A0F4-4274-CA67-FE2C-06AB45EFDF58": ("Ares", "Metralhadora"),
    "63E6C2B6-4A8E-869C-3D4C-E38355226584": ("Odin", "Metralhadora"),
    "8DB0A1BF-4A50-832A-4566-FAAAA6D250CA": ("Warden", "Outra"),
    # armas que vêm de habilidades: não estão na lista pública de armas;
    # nomes inferidos pelo agente que as usa nesta base (conferir se precisar)
    "95336AE4-45D4-1032-CFAF-6BAD01910607": ("Overdrive (Neon)", "Habilidade"),
    "856D9A7E-4B06-DC37-15DC-9D809C37CB90": ("Headhunter (Chamber)", "Habilidade"),
    "39099FB5-4293-DEF4-1E09-2E9080CE7456": ("Tour de Force (Chamber)", "Habilidade"),
}

ESCUDOS = {
    "": "Sem escudo",
    "4DEC83D5-4902-9AB3-BED6-A7A390761157": "Leve",
    "822BCAB2-40A2-324E-C137-E09195AD7692": "Pesado",
    "B1B9086D-41BD-A516-5D29-E3B34A6F1644": "Regenerativo",
}

# mapId -> nome. Os mapas usam codinomes internos (Triad = Haven, Jam = Lotus...).
MAPAS = {
    "/Game/Maps/Ascent/Ascent": "Ascent",
    "/Game/Maps/Bonsai/Bonsai": "Split",
    "/Game/Maps/Canyon/Canyon": "Fracture",
    "/Game/Maps/Duality/Duality": "Bind",
    "/Game/Maps/Foxtrot/Foxtrot": "Breeze",
    "/Game/Maps/Infinity/Infinity": "Abyss",
    "/Game/Maps/Jam/Jam": "Lotus",
    "/Game/Maps/Juliett/Juliett": "Sunset",
    "/Game/Maps/Pitt/Pitt": "Pearl",
    "/Game/Maps/Plummet/Plummet": "Summit",
    "/Game/Maps/Port/Port": "Icebox",
    "/Game/Maps/Triad/Triad": "Haven",
}

# Conversão de coordenadas do jogo (x, y) para o minimapa em [0, 1]:
#   mini_x = y_jogo * xMult + xAdd
#   mini_y = x_jogo * yMult + yAdd
# (sim, x e y trocam de lugar; é assim que o jogo define)
MINIMAPA = {
    "Ascent":   (7.0e-05, -7.0e-05, 0.813895, 0.573242),
    "Split":    (7.8e-05, -7.8e-05, 0.842188, 0.697578),
    "Fracture": (7.8e-05, -7.8e-05, 0.556952, 1.155886),
    "Bind":     (5.9e-05, -5.9e-05, 0.576941, 0.967566),
    "Breeze":   (7.0e-05, -7.0e-05, 0.465123, 0.833078),
    "Abyss":    (8.1e-05, -8.1e-05, 0.5, 0.5),
    "Lotus":    (7.2e-05, -7.2e-05, 0.454789, 0.917752),
    "Sunset":   (7.8e-05, -7.8e-05, 0.5, 0.515625),
    "Pearl":    (7.8e-05, -7.8e-05, 0.480469, 0.916016),
    "Summit":   (7.5e-05, -7.5e-05, 0.047401, 0.978891),
    "Icebox":   (7.2e-05, -7.2e-05, 0.460214, 0.304687),
    "Haven":    (7.5e-05, -7.5e-05, 1.09345, 0.642728),
}

# Nome da habilidade quando o damageType é "Ability"
HABILIDADES = {
    "GrenadeAbility": "Habilidade C",
    "Ability1": "Habilidade Q",
    "Ability2": "Habilidade E",
    "Ultimate": "Ultimate",
}

# Faixas de compra pelo valor TOTAL do equipamento do time no round (ajustável)
FAIXAS_COMPRA = [
    (5_000, "Eco"),
    (10_000, "Semi-eco"),
    (20_000, "Semi-compra"),
    (float("inf"), "Compra completa"),
]

JANELA_TRADE_MS = 5_000  # morte "trocada" se o assassino morrer até 5 s depois

# Coesão: morte "isolada" = aliado vivo mais próximo a mais de X metros
LIMIAR_ISOLADO_M = 20
DIST_MAX_VALIDA_M = 150  # acima disso a coordenada do JSON é considerada inválida


def nome_agente(cid):
    if cid is None:
        return ("Desconhecido", "Desconhecido")
    return AGENTES.get(cid.lower(), (f"Agente {cid[:8]}", "Desconhecido"))


def nome_arma(wid):
    if not wid:
        return ("Nenhuma", "Nenhuma")
    return ARMAS.get(wid.upper(), (f"Arma {wid[:8]}", "Outra"))


def nome_mapa(map_id):
    return MAPAS.get(map_id, map_id.rsplit("/", 1)[-1])


def faixa_compra(valor_time):
    for limite, nome in FAIXAS_COMPRA:
        if valor_time < limite:
            return nome
    return FAIXAS_COMPRA[-1][1]
