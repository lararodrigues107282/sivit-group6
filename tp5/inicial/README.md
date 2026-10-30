# TP4 · Material inicial

O que é dado pronto para o TP4, além do guião. O resto, o serviço `ingestao`
(`main.py`, `Dockerfile`) e o simulador de *gateway*, é trabalho vosso.

| Ficheiro | Para quê |
|---|---|
| `docker-compose.override.yml` | junta ao compose de TP2/TP3 o serviço `ingestao` e o gerador de carga `carga` |
| `env.tp4.exemplo` | variáveis novas, a acrescentar ao `.env` |
| `portal/vigilancia/middleware.py` | latência artificial no portal (`LATENCIA_MS`), para a experiência A do exercício 3 |
| `portal/vigilancia/management/commands/seed_sivit.py` | povoamento: 20 doentes internados, 60 dispositivos (`SN-0001-0` a `SN-0020-2`) e leituras |
| `criar_token.sh` | cria o utilizador de serviço `ingestao` no portal e imprime o seu token |
| `ferramentas/` | gerador de carga com débito, p50/p95/p99 e leituras perdidas |
| `ingestao/requirements.txt` | as versões de FastAPI, asyncpg e httpx usadas nas medições de referência |

## Instalação no vosso repositório

1. Copiar `docker-compose.override.yml`, `criar_token.sh` e a pasta
   `ferramentas/` para a raiz do repositório, e `ingestao/requirements.txt`
   para a pasta `ingestao/`.
2. Acrescentar ao `.env` as linhas de `env.tp4.exemplo`.
3. Copiar `portal/vigilancia/` por cima da vossa app `vigilancia`. Se já
   tinham o *middleware* da extensão E4 de TP2, basta confirmar que lê
   `LATENCIA_MS`.
4. Registar o *middleware* no fim de `MIDDLEWARE`, em `settings.py`:

   ```python
   MIDDLEWARE = [
       ...
       "vigilancia.middleware.LatenciaArtificialMiddleware",
   ]
   ```

## Arranque

```bash
docker compose up -d --build sivitDB portal
docker compose exec portal python manage.py seed_sivit --leituras 2000
./criar_token.sh                     # colar o valor em PORTAL_TOKEN, no .env
docker compose up -d --build ingestao
curl -s localhost:8001/saude/pronto
```

## Medir

O gerador de carga corre num contentor na rede do compose e imprime uma linha
JSON com o que as tabelas do guião pedem.

```bash
# exercício 2: as três variantes, 50 clientes durante 10 s
docker compose run --rm carga http://ingestao:8001/teste/bloqueante --concorrencia 50 --duracao 10

# exercício 3: lotes de 10 leituras; o resultado traz debito_req_s, p99_ms e leituras_perdidas
docker compose run --rm carga http://ingestao:8001/v1/leituras --metodo POST --lote 10 --concorrencia 50 --duracao 15
```

Para pôr o portal a 3 s e voltar ao normal:

```bash
LATENCIA_MS=3000 docker compose up -d portal
LATENCIA_MS=0    docker compose up -d portal
```

Para mudar de padrão no exercício 3, recriar só a ingestão:

```bash
MODO_VALIDACAO=timeout docker compose up -d ingestao
```

## Notas

- Os números de série que o gerador de carga envia (`SN-0001-0` a
  `SN-0020-2`) são os que o `seed_sivit` cria, todos associados a um
  internamento ativo. Para ter um dispositivo sem internamento, retirar-lho
  pela API ou pelo admin.
- Uma leitura de um dispositivo que não existe no portal **não dá erro**: o
  `INSERT … SELECT` do guião não encontra o dispositivo e não insere nada.
  Contem com isto quando compararem leituras enviadas com linhas na base de
  dados.
