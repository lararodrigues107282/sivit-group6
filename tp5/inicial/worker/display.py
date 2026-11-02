"""Consumidor do painel da enfermaria: mantém o último valor de cada dispositivo.

Num sistema real faria push para os ecrãs (WebSocket); aqui guarda o estado
em memória, que é o que o painel mostraria.
"""
from comum import correr

ultimo = {}   # (dispositivo, parametro) -> (instante, valor)


async def atualizar(l):
    chave = (l["device"], l["parameter"])
    if chave not in ultimo or l["instant"] >= ultimo[chave][0]:
        ultimo[chave] = (l["instant"], l["value"])


if __name__ == "__main__":
    correr("display", atualizar)
