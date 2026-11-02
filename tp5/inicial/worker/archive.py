"""Consumidor de arquivo: grava cada leitura no PostgreSQL, de forma idempotente."""
import os

import asyncpg

from comum import MensagemInvalida, correr

DATABASE_URL = os.environ["DATABASE_URL"]
SEM_ON_CONFLICT = os.getenv("SEM_ON_CONFLICT", "0") == "1"   # Ex. 3c: ver os duplicados aparecer

INSERT_LEITURA = """
INSERT INTO vigilancia_reading (device_id, instant, parameter, value, unit)
SELECT d.id, $2::timestamptz, $3::varchar, $4::double precision, $5::varchar
FROM vigilancia_device d
WHERE d.serial_number = $1::varchar
"""
# ON CONFLICT: uma mensagem reentregue não cria uma segunda linha (consumidor idempotente).
COM_CONFLITO = INSERT_LEITURA + "ON CONFLICT (device_id, instant, parameter) DO NOTHING"
SQL = INSERT_LEITURA if SEM_ON_CONFLICT else COM_CONFLITO


async def preparar():
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)

    async def gravar(l):
        try:
            async with pool.acquire() as c:
                await c.execute(SQL, l["device"], l["instant"], l["parameter"], l["value"], l["unit"])
        except asyncpg.DataError as exc:
            # Dados que a BD nunca vai aceitar: permanente, vai para a DLQ.
            raise MensagemInvalida(str(exc)) from exc
        # Qualquer outro erro (BD em baixo, timeout...) sobe e é tratado como transitório.

    return gravar


if __name__ == "__main__":
    correr("archive", None, preparar)
