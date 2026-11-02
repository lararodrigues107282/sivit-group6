"""Injeta mensagens malformadas, para a experiência da dead-letter queue (Ex. 3d).

  docker compose exec -T ingestao python - 5 < tp5/inicial/ferramentas/veneno.py

Uma poison message que o consumidor rejeita sempre bloquearia a fila se fosse
reencaminhada indefinidamente. Com a DLQ configurada, sai do caminho ao fim
da primeira rejeição e alguém tem de ir olhar para ela.
"""
import asyncio
import json
import os
import sys

import aio_pika


async def principal(n):
    ligacao = await aio_pika.connect_robust(os.environ["AMQP_URL"])
    canal = await ligacao.channel()
    exchange = await canal.declare_exchange(
        os.environ.get("EXCHANGE", "readings"),
        aio_pika.ExchangeType.TOPIC, durable=True)
    for i in range(n):
        await exchange.publish(
            aio_pika.Message(body=json.dumps({"lixo": i}).encode(),
                             delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key="reading.fc.VENENO")
    print(f"{n} mensagens malformadas publicadas")
    await ligacao.close()


if __name__ == "__main__":
    asyncio.run(principal(int(sys.argv[1]) if len(sys.argv) > 1 else 5))
