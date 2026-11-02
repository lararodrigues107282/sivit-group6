###Código partilhado pelos consumidores da TP5 (archive, alarms, display, stats).

###Cada consumidor só tem de dizer o nome da sua fila e o que fazer com uma
###leitura. Tudo o resto vive aqui: ligação ao broker, declaração da fila com a
###sua DLQ, prefetch, acks, e as variáveis de ambiente das experiências.

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

import aio_pika

AMQP_URL = os.environ.get("AMQP_URL", "amqp://sivit:devpass@rabbitmq/")
EXCHANGE = "readings"          # topic, declarada também pela ingestão
DLX = "readings.dlx"           # direct; cada fila manda as rejeitadas para a SUA dlq
BINDING = "reading.*.*"        # reading.<parametro>.<dispositivo>: todas as leituras

# Botões das experiências (README da TP5). Mudam-se sem tocar no código:
#   PREFETCH=1 TRABALHO_MS=50 docker compose up -d alarms_worker
PREFETCH = int(os.getenv("PREFETCH", "10"))
ACK_AUTOMATICO = os.getenv("ACK_AUTOMATICO", "0") == "1"
TRABALHO_MS = float(os.getenv("TRABALHO_MS", "0"))
MORRER_APOS = int(os.getenv("MORRER_APOS", "0"))
MORRER_ANTES_DO_ACK = os.getenv("MORRER_ANTES_DO_ACK", "0") == "1"
MAX_MENSAGENS = int(os.getenv("MAX_MENSAGENS", "100000"))
POLITICA_CHEIA = os.getenv("POLITICA_CHEIA", "reject-publish")

CAMPOS = ("device", "instant", "parameter", "value", "unit")


class MensagemInvalida(Exception):
    """Erro permanente: repetir não ajuda, a mensagem vai para a DLQ."""


def registar(**campos):
    """Uma linha JSON por evento no stdout: é o que as ferramentas de medição leem."""
    print(json.dumps(campos, ensure_ascii=False), flush=True)


def ler_leitura(corpo: bytes) -> dict:
    """Valida e converte o corpo publicado pela ingestão. Lança MensagemInvalida."""
    try:
        dados = json.loads(corpo)
        leitura = {c: dados[c] for c in CAMPOS}
        leitura["instant"] = datetime.fromisoformat(leitura["instant"])  # o asyncpg quer datetime
        leitura["value"] = float(leitura["value"])
        publicado = dados.get("_published_at")
        leitura["_published_at"] = datetime.fromisoformat(publicado) if publicado else None
        return leitura
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise MensagemInvalida(f"{type(exc).__name__}: {exc}") from exc


def morrer():
    """Simula um crash: termina sem fechar a ligação (o broker reentrega o que não teve ack)."""
    registar(evento="morte", ts=time.time())
    os._exit(1)


async def tratar(msg, fila: str, processar, contagem: list):
    """Trata UMA mensagem: validar, trabalhar, ack. Separado do ciclo para se poder testar."""
    try:
        leitura = ler_leitura(msg.body)
    except MensagemInvalida as exc:
        # Erro permanente (mensagem envenenada): rejeitar SEM requeue -> DLQ.
        registar(evento="rejeitado", fila=fila, id=msg.message_id, motivo=str(exc))
        if not ACK_AUTOMATICO:
            await msg.reject(requeue=False)
        return

    try:
        if TRABALHO_MS:
            await asyncio.sleep(TRABALHO_MS / 1000)     # trabalho artificial (Ex. 2.2 e 3)
        await processar(leitura)
    except MensagemInvalida as exc:
        registar(evento="rejeitado", fila=fila, id=msg.message_id, motivo=str(exc))
        if not ACK_AUTOMATICO:
            await msg.reject(requeue=False)
        return
    except Exception as exc:
        # Erro transitório (ex.: BD em baixo): devolver à fila, não à DLQ.
        registar(evento="erro_transitorio", fila=fila, id=msg.message_id,
                 erro=f"{type(exc).__name__}: {exc}")
        if not ACK_AUTOMATICO:
            await asyncio.sleep(1)                      # não martelar a BD enquanto recupera
            await msg.nack(requeue=True)
        return

    contagem[0] += 1
    limite = MORRER_APOS or (1 if MORRER_ANTES_DO_ACK else 0)
    if MORRER_ANTES_DO_ACK and contagem[0] >= limite:
        morrer()                                        # processou, mas o ack nunca sai (Ex. 3c)

    if not ACK_AUTOMATICO:
        await msg.ack()                                 # ack manual, só DEPOIS de processar

    publicado = leitura["_published_at"]
    latencia = (datetime.now(timezone.utc) - publicado).total_seconds() * 1000 if publicado else None
    registar(evento="processado", ts=time.time(), fila=fila,
             latencia_ms=round(latencia, 1) if latencia is not None else None,
             id=msg.message_id)

    if MORRER_APOS and contagem[0] >= MORRER_APOS:
        morrer()                                        # morre a meio do lote (Ex. 3a)


async def consumir(fila: str, processar):
    """Liga ao broker, declara a topologia da fila e consome para sempre."""
    ligacao = await aio_pika.connect_robust(AMQP_URL)
    canal = await ligacao.channel()
    await canal.set_qos(prefetch_count=PREFETCH)        # mensagens sem ack em simultâneo (Ex. 3b)

    # Topologia declarada pelo CONSUMIDOR: acrescentar uma fila não mexe no produtor (Ex. 2.4).
    exchange = await canal.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    dlx = await canal.declare_exchange(DLX, aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await canal.declare_queue(f"{fila}.dlq", durable=True)
    await dlq.bind(dlx, routing_key=fila)

    argumentos = {
        "x-dead-letter-exchange": DLX,
        "x-dead-letter-routing-key": fila,              # cada fila para a SUA dlq
        "x-message-ttl": 3_600_000,                     # 1 h na fila no máximo
        "x-max-length": MAX_MENSAGENS,                  # fila limitada (Ex. 3e)
        "x-overflow": POLITICA_CHEIA,                   # reject-publish ou drop-head
    }
    queue = await canal.declare_queue(fila, durable=True, arguments=argumentos)
    await queue.bind(exchange, routing_key=BINDING)

    registar(evento="pronto", fila=fila, prefetch=PREFETCH, ack_automatico=ACK_AUTOMATICO,
             trabalho_ms=TRABALHO_MS, morrer_apos=MORRER_APOS,
             morrer_antes_do_ack=MORRER_ANTES_DO_ACK)

    contagem = [0]
    # Uma mensagem de cada vez: o detetor é CPU-bound, e a ordem dentro de um worker mantém-se.
    async with queue.iterator(no_ack=ACK_AUTOMATICO) as mensagens:
        async for msg in mensagens:
            await tratar(msg, fila, processar, contagem)


def correr(fila: str, processar, preparar=None):
    """Ponto de entrada dos scripts: correr("archive", gravar)."""
    async def principal():
        nonlocal processar
        if preparar:
            processar = await preparar()
        await consumir(fila, processar)
    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        sys.exit(0)
