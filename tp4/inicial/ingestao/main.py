import os, time, random, asyncio, logging, httpx
from contextlib import asynccontextmanager
from datetime import datetime

import asyncpg
from fastapi import FastAPI, Response, status
from pydantic import BaseModel, ConfigDict, Field

DATABASE_URL = os.environ["DATABASE_URL"]
INSERT_LEITURA = """
INSERT INTO vigilancia_reading (device_id, instant, parameter, value, unit)
SELECT d.id, $2::timestamptz, $3::varchar, $4::double precision, $5::varchar
FROM vigilancia_device d
WHERE d.serial_number = $1::varchar
ON CONFLICT (device_id, instant, parameter) DO NOTHING
"""


class Reading(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    device: str = Field(alias="dispositivo")
    instant: datetime = Field(alias="instante")
    parameter: str = Field(alias="parametro")
    value: float = Field(alias="valor")
    unit: str = Field(alias="unidade")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
    yield
    await app.state.pool.close()


app = FastAPI(title="SIVIT ingestão", lifespan=lifespan)

"""Exercicio 1"""

@app.get("/health/live")
async def live():
    """Verifica que o processo está vivo."""
    return {"status": "ok"}


@app.get("/health/ready")
async def ready(response: Response):
    """Verifica se esta pronto a receber tráfego."""
    try:
        async with asyncio.timeout(1):
            async with app.state.pool.acquire() as c:
                await c.fetchval("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "error": type(exc).__name__}

"""Exercicio 2"""

@app.post("/v1/readings", status_code=202)
async def ingest(batch: list[Reading]):
    serials = {r.device for r in batch}
    estado = {s: await validar(s) for s in serials}

    aceites = [r for r in batch if estado[r.device] is not False]
    por_reconciliar = [s for s, v in estado.items() if v is None]
    if por_reconciliar:
        log.warning("Aceites sem validação (reconciliar): %s", por_reconciliar)

    rows = [(r.device, r.instant, r.parameter, r.value, r.unit) for r in aceites]
    async with app.state.pool.acquire() as c:
        await c.executemany(INSERT_LEITURA, rows)
    return {"received": len(batch), "accepted": len(aceites), "unvalidated": por_reconciliar}

@app.get("/teste/bloqueante")
async def teste_bloqueante():
    time.sleep(0.2)
    return {"ok": True}


@app.get("/teste/assincrono")
async def teste_assincrono():
    await asyncio.sleep(0.2)
    return {"ok": True}


@app.get("/teste/thread")
def teste_thread():
    time.sleep(0.2)
    return {"ok": True}


"""Exercicio 3"""


PORTAL = os.getenv("PORTAL", "http://portal:8000")
HEADERS = {"Authorization": f"Token {os.getenv('PORTAL_TOKEN', '')}"}
MODO = os.getenv("MODO_VALIDACAO", "off")
log = logging.getLogger("ingestao")


def tem_admissao(dados) -> bool:
    res = dados.get("results", [])
    return len(res) > 0 and res[0]["admission"] is not None


async def validar_ingenuo(serial: str) -> bool:
    async with httpx.AsyncClient() as cli:
        r = await cli.get(f"{PORTAL}/api/v1/devices/",
                          params={"serial_number": serial}, headers=HEADERS)
    return r.status_code == 200 and tem_admissao(r.json())

cliente = httpx.AsyncClient(timeout=0.5)

async def chamar_portal(serial: str) -> bool:
    r = await cliente.get(f"{PORTAL}/api/v1/devices/",
                          params={"serial_number": serial}, headers=HEADERS)
    r.raise_for_status()
    return tem_admissao(r.json())

async def validar_timeout(serial: str):
    try:
        return await chamar_portal(serial)
    except httpx.HTTPError:
        return None

async def chamar_com_retry(serial: str, tentativas=3, base=0.1) -> bool:
    for n in range(tentativas):
        try:
            return await chamar_portal(serial)
        except httpx.HTTPError:
            if n == tentativas - 1:
                raise
            espera = random.uniform(0, base * 2 ** n)
            await asyncio.sleep(espera)

async def validar_retry(serial: str):
    try:
        return await chamar_com_retry(serial)
    except httpx.HTTPError:
        return None

class CircuitBreaker:
    def __init__(self, max_falhas=5, pausa=10):
        self.max_falhas = max_falhas
        self.pausa = pausa
        self.falhas = 0
        self.aberto_desde = None

    def pode_chamar(self) -> bool:
        if self.aberto_desde is None:
            return True
        if time.monotonic() - self.aberto_desde >= self.pausa:
            return True
        return False

    def sucesso(self):
        self.falhas = 0
        self.aberto_desde = None

    def falha(self):
        self.falhas += 1
        if self.falhas >= self.max_falhas:
            self.aberto_desde = time.monotonic()

breaker = CircuitBreaker()

async def validar_breaker(serial: str):
    if not breaker.pode_chamar():
        return None
    try:
        r = await chamar_com_retry(serial)
        breaker.sucesso()
        return r
    except httpx.HTTPError:
        breaker.falha()
        return None

cache = {}
TTL = 60

async def validar_cache(serial: str):
    agora = time.monotonic()
    if serial in cache and cache[serial][1] > agora:
        return cache[serial][0]
    resultado = await validar_breaker(serial)
    if resultado is not None:
        cache[serial] = (resultado, agora + TTL)
    return resultado

async def validar(serial: str):
    if MODO == "off":       return True
    if MODO == "ingenuo":   return await validar_ingenuo(serial)
    if MODO == "timeout":   return await validar_timeout(serial)
    if MODO == "retry":     return await validar_retry(serial)
    if MODO == "breaker":   return await validar_breaker(serial)
    if MODO == "cache":     return await validar_cache(serial)
    raise ValueError(f"MODO_VALIDACAO desconhecido: {MODO}")
