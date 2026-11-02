"""Leituras processadas fora de ordem, por dispositivo, a partir dos logs (Ex. 4.2).

  docker compose logs --no-log-prefix alarms_worker | python3 tp5/inicial/ferramentas/ordem_de_logs.py

Os consumidores escrevem uma linha JSON por mensagem processada, com o
instante do processamento (ts) e o message_id (dispositivo|instante|parametro).
Para cada dispositivo, ordenam-se as mensagens pela hora a que foram
processadas e conta-se quantas vezes uma leitura foi processada depois de
outra mais recente.
"""
import json
import sys
from collections import defaultdict

por_dispositivo = defaultdict(list)
for linha in sys.stdin:
    inicio = linha.find("{")
    if inicio < 0:
        continue
    try:
        d = json.loads(linha[inicio:])
    except Exception:
        continue
    ident = str(d.get("id", ""))
    if d.get("evento") != "processado" or ident.count("|") != 2:
        continue
    dispositivo, instante, _ = ident.split("|")
    por_dispositivo[dispositivo].append((d["ts"], instante))

pares = fora = 0
for lista in por_dispositivo.values():
    lista.sort()
    for (_, anterior), (_, seguinte) in zip(lista, lista[1:]):
        pares += 1
        fora += seguinte < anterior

print(json.dumps({
    "dispositivos": len(por_dispositivo),
    "pares_consecutivos": pares,
    "fora_de_ordem": fora,
    "percentagem": round(100 * fora / pares, 2) if pares else None,
}))
