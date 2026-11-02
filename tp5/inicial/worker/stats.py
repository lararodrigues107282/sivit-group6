"""Quarto consumidor (Ex. 2.4): estatísticas por parâmetro. Zero linhas mudadas na ingestão."""
from collections import Counter

from comum import correr

contagem = Counter()


async def contar(l):
    contagem[l["parameter"]] += 1


if __name__ == "__main__":
    correr("stats", contar)
