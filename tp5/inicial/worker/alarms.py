"""Consumidor de alarmes: o 'detetor' que analisa todas as leituras.

O detetor real seria computacionalmente caro; aqui são limiares simples, e o
custo simula-se com TRABALHO_MS (Ex. 2.2).
"""
from comum import correr, registar

# (mínimo, máximo) aceitáveis por parâmetro
LIMITES = {"FC": (40, 130), "SPO2": (90, 101), "TEMP": (35.0, 39.0)}


async def detetar(l):
    limites = LIMITES.get(l["parameter"].upper())
    if limites and not (limites[0] <= l["value"] <= limites[1]):
        registar(evento="alarme", dispositivo=l["device"], parametro=l["parameter"],
                 valor=l["value"], instante=l["instant"].isoformat())


if __name__ == "__main__":
    correr("alarms", detetar)
