import argparse, asyncio, json, math, os, random, time
from datetime import datetime, timezone

import httpx


class Doente:
    def __init__(self, serial):
        self.serial = serial
        self.fc_base = random.uniform(65, 85)
        self.temp = random.uniform(36.4, 37.0)
        self.oclusao = 0
        self.t = 0

    def ler(self, prob_anomalia):
        self.t += 1

        fc = self.fc_base + 4 * math.sin(self.t / 10) + random.gauss(0, 2)

        if self.oclusao == 0 and random.random() < 0.01:
            self.oclusao = random.randint(3, 8)
        if self.oclusao > 0:
            spo2 = random.uniform(80, 88)
            self.oclusao -= 1
        else:
            spo2 = min(100, random.gauss(97, 1))

        self.temp = min(38.0, max(36.0, self.temp + random.gauss(0, 0.01)))
        temp = self.temp

        if random.random() < prob_anomalia:
            qual = random.choice(["fc", "spo2", "temp"])
            if qual == "fc":
                fc = random.choice([35, 180])
            elif qual == "spo2":
                spo2 = random.uniform(70, 80)
            else:
                temp = random.uniform(39.5, 41)

        agora = datetime.now(timezone.utc).isoformat()
        return [
            self._leitura(agora, "FC", fc, "bpm"),
            self._leitura(agora, "SPO2", spo2, "%"),
            self._leitura(agora, "TEMP", temp, "°C"),
        ]

    def _leitura(self, instante, parametro, valor, unidade):
        return {"dispositivo": self.serial, "instante": instante,
                "parametro": parametro, "valor": round(valor, 1), "unidade": unidade}


class Buffer:
    def __init__(self, caminho):
        self.caminho = caminho
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)

    def guardar(self, leituras):
        with open(self.caminho, "a", encoding="utf-8") as f:
            for l in leituras:
                f.write(json.dumps(l) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def ler(self):
        if not os.path.exists(self.caminho):
            return []
        with open(self.caminho, encoding="utf-8") as f:
            return [json.loads(linha) for linha in f if linha.strip()]

    def substituir(self, leituras):
        tmp = self.caminho + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for l in leituras:
                f.write(json.dumps(l) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.caminho)


async def enviar(cliente, url, leituras):
    try:
        r = await cliente.post(url, json=leituras)
    except httpx.HTTPError:
        return False
    if r.status_code >= 500:
        return False
    if r.status_code >= 400:
        print(f"Rejeitado ({r.status_code}): {r.text[:200]}", flush=True)
    return True


async def esvaziar_buffer(cliente, url, buffer, tamanho=500):
    pendentes = buffer.ler()
    reenviadas = 0
    while pendentes:
        lote = pendentes[:tamanho]
        if not await enviar(cliente, url, lote):
            break
        pendentes = pendentes[tamanho:]
        buffer.substituir(pendentes)
        reenviadas += len(lote)
    return reenviadas


async def principal(a):
    doentes = [Doente(f"SN-{i // 3 + 1:04d}-{i % 3}") for i in range(a.dispositivos)]
    buffer = Buffer(a.buffer)
    stats = {"enviadas": 0, "guardadas_no_buffer": 0, "reenviadas": 0}
    intervalo = 1 / a.frequencia
    fim = time.monotonic() + a.duracao if a.duracao else None
    ultimo_print = 0

    async with httpx.AsyncClient(timeout=a.timeout) as cliente:
        proximo = time.monotonic()
        while fim is None or time.monotonic() < fim:
            leituras = [l for d in doentes for l in d.ler(a.anomalias)]

            if await enviar(cliente, a.url, leituras):
                stats["enviadas"] += len(leituras)
                stats["reenviadas"] += await esvaziar_buffer(cliente, a.url, buffer)
            else:
                buffer.guardar(leituras)
                stats["guardadas_no_buffer"] += len(leituras)

            if time.monotonic() - ultimo_print >= 5:
                print(json.dumps({**stats, "pendentes": len(buffer.ler())}), flush=True)
                ultimo_print = time.monotonic()

            proximo += intervalo
            await asyncio.sleep(max(0, proximo - time.monotonic()))

    print(json.dumps({**stats, "pendentes": len(buffer.ler())}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://ingestao:8001/v1/readings")
    p.add_argument("--dispositivos", type=int, default=10, help="1 a 60")
    p.add_argument("--frequencia", type=float, default=1.0, help="leituras por segundo (Hz)")
    p.add_argument("--duracao", type=float, default=0, help="segundos (0 = sem fim)")
    p.add_argument("--anomalias", type=float, default=0.0, help="probabilidade, ex.: 0.02")
    p.add_argument("--buffer", default="/dados/buffer.jsonl")
    p.add_argument("--timeout", type=float, default=2.0)
    try:
        asyncio.run(principal(p.parse_args()))
    except KeyboardInterrupt:
        pass
