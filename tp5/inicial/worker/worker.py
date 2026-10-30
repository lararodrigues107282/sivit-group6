import os
import json
import asyncio
import aio_pika
import asyncpg

DATABASE_URL = os.environ["DATABASE_URL"]
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq/")

INSERT_LEITURA = """
INSERT INTO vigilancia_reading (device_id, instant, parameter, value, unit)
SELECT d.id, $2::timestamptz, $3::varchar, $4::double precision, $5::varchar
FROM vigilancia_device d
WHERE d.serial_number = $1::varchar
ON CONFLICT (device_id, instant, parameter) DO NOTHING
"""

#    Exercise 3 (TP5)

async def process_message(message: aio_pika.IncomingMessage, db_pool: asyncpg.Pool):
    async with message.process(ignore_processed=True):
        try:
            data = json.loads(message.body.decode())
            
            # Extract fields published by the ingestion service
            device = data.get("dispositivo")
            instant = data.get("instante")
            parameter = data.get("parametro")
            value = data.get("valor")
            unit = data.get("unidade")

            # Write to PostgreSQL safely (idempotent with ON CONFLICT)
            async with db_pool.acquire() as conn:
                await conn.execute(INSERT_LEITURA, device, instant, parameter, value, unit)
            
            # Manual acknowledgement that processing succeeded
            await message.ack()
        except Exception as e:
            print(f"Error processing message: {e}", flush=True)
            # Reject and do not requeue if it's a poison message (goes to DLQ)
            await message.nack(requeue=False)

async def main():
    # Connect to PostgreSQL pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    
    # Connect to RabbitMQ
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        
        # Set prefetch count to control how many unacknowledged messages a worker takes at once (TP5 Ex. 3b)
        await channel.set_qos(prefetch_count=10)

        # Declare DLX and DLQ for poison messages (TP5 Ex. 3d)
        dlx = await channel.declare_exchange("readings.dlx", aio_pika.ExchangeType.DIRECT, durable=True)
        dlq = await channel.declare_queue("archive.dlq", durable=True)
        await dlq.bind(dlx, routing_key="archive")

        # Declare the main archive queue with arguments pointing to its DLQ
        queue_args = {
            "x-dead-letter-exchange": "readings.dlx",
            "x-dead-letter-routing-key": "archive",
            "x-max-length": 100_000,
        }
        queue = await channel.declare_queue("archive", durable=True, arguments=queue_args)

#           Exercise 2(TP5)

        # Bind queue to the topic exchange created in ingestion
        exchange = await channel.declare_exchange("readings", aio_pika.ExchangeType.TOPIC, durable=True)
        await queue.bind(exchange, routing_key="reading.*.*")

        print("[*] Archive worker waiting for messages. To exit press CTRL+C", flush=True)

        # Start consuming messages
        await queue.consume(lambda msg: process_message(msg, db_pool))
        
        # Keep running
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())