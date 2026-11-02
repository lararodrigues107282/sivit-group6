"""Percentis da latência publicação -> processamento, a partir dos logs (Ex. 4.3).

  docker compose logs --no-log-prefix --since 1m alarms_worker | python3 tp5/inicial/ferramentas/latencia_de_logs.py

Os consumidores escrevem uma linha JSON por mensagem processada, com o campo
latencia_ms. Este script lê o que vier no stdin, ignora o resto, e imprime a
distribuição. O p99 contra o p50 é a medição decisiva do exercício 4.3.
"""
import json
import statistics
import sys

valores = []
for linha in sys.stdin:
    inicio = linha.find("{")
    if inicio < 0:
        continue
    try:
        d = json.loads(linha[inicio:])
    except Exception:
        continue
    if isinstance(d, dict) and d.get("latencia_ms") is not None:
        valores.append(float(d["latencia_ms"]))

if not valores:
    print("sem amostras de latência nos logs")
    sys.exit(0)

v = sorted(valores)
def p(q):
    return v[min(len(v) - 1, int(len(v) * q))]

print(json.dumps({
    "amostras": len(v),
    "media_ms": round(statistics.mean(v), 1),
    "p50_ms": round(p(.50), 1),
    "p95_ms": round(p(.95), 1),
    "p99_ms": round(p(.99), 1),
    "max_ms": round(v[-1], 1),
    "razao_p99_p50": round(p(.99) / p(.50), 1) if p(.50) else None,
}, indent=2))
