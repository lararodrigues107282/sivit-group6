# Respostas à TP4 - Microserviço de ingestão

As medições foram feitas no Docker Compose, num portátil, com o portal em Gunicorn (3 workers) e a ingestão em Uvicorn (1 worker). Usámos a ferramenta `carga` do material inicial, e cada valor corresponde a uma execução.

## O endpoint de ingestão

1. **`ON CONFLICT … DO NOTHING`** O `ON CONFLICT` é mais seguro porque é a própria base de dados que verifica e insere, apenas em uma operação. Se fizéssemos `SELECT` e depois `INSERT` em Python, como noutros casos, dois pedidos ao mesmo tempo podiam ambos ver que a leitura não existe e inseri-la duas vezes. Na nossa TP3 usámos `bulk_create(ignore_conflicts=True)`, que no PostgreSQL já gera um `ON CONFLICT`, por isso também não tinha este problema.

2. **`202` em vez de `201`:** `201` diz que a leitura já foi gravada. `202` diz apenas que o pedido foi aceite. Como na TP a escrita vai passar para uma fila, com `202` o contrato com os gateways continua certo e não é preciso mudar os clientes.

3. **`ready` ou `live`:** O `live` só verifica se o processo responde. Já `ready` verifica também se a base de dados responde em menos de 1 segundo. Deste modo se:
   - O balanceador usar o `ready` e a base de dados ficar lenta, todas as réplicas falham ao mesmo tempo e o serviço fica todo indisponível;
   - Usar o `live`, as réplicas continuam a receber pedidos que não conseguem tratar, e esses pedidos acabam em timeout.

   Ou seja, o `ready` é responsável por decidir para onde vai o tráfego e o `live` quando reiniciar o processo.

## `async`:  ajuda ou piora?

50 clientes concorrentes durante 10 s. Cada endpoint espera 200 ms.

| Endpoint            | Débito (req/s) | p50 (ms) | p99 (ms) |
| :---                | ---:           | ---:     | ---:     |
| `/teste/bloqueante` | 5,1            | 9 488    | 10 059   |
| `/teste/assincrono` | 230,5          | 206      | 398      |
| `/teste/thread`     | 191,8          | 252      | 364      |

1. **Porque é que o bloqueante colapsa:** O *event loop* é um único *thread* que vai fazendo avançar a máquina de estados de cada pedido, e só passa para outro pedido quando o atual faz `await`. Por outro lado, o `time.sleep` não faz `await`, assim o *loop* fica parado 200 ms e os pedidos são atendidos um a um: 1 / 0,2 s = 5 pedidos/s, que foi o que medimos. Já com `asyncio.sleep` as 50 esperas sobrepõem-se. A versão `thread` fica um pouco abaixo porque o *pool* de *threads* do FastAPI tem 40 *threads* (40 / 0,2 s = 200 pedidos/s).

2. **`psycopg2` dentro de `async def`** é a variante bloqueante: cada consulta para o *event loop*, como o `time.sleep`. Por isso usamos o `asyncpg`.

3. **Workers necessários:** Cerca de 46 (230 / 5). Uma vez que cada worker é um processo com o seu próprio *pool* de ligações à base de dados e 46 × 20 ligações ultrapassa largamente o limite do PostgreSQL (100), esta não é uma solução aceitável. 

## Falha em cascata

A ingestão pergunta ao portal se cada dispositivo do lote tem internamento ativo. Medimos com 50 clientes, 15 s e lotes de 10 leituras.

| Configuração                 | Débito (req/s) | Leituras perdidas    | p99 (ms)    |
| :---                         | ---:           | ---:                 | ---:        |
| Sem validação (referência)   | 313,4          | 0                    | 792         |
| Síncrono, portal saudável    | 10,8           | 0                    | 5 391       |
| Síncrono, portal a 3 s       | 13,0 ?1        | 2 460 (100%)         | 8 866       |
| + timeout 500 ms             | 8,1            | 0                    | 5 952       |
| + retry com backoff e jitter | 5,0 ?1         | 1 000 (100%)         | ≥ 10 112 ?2 |
| + circuit breaker            | 264,2          | 0                    | 2 108       |
| + cache local 60 s           | 265,0          | 0                    | 948         |

?1 Todos os pedidos falharam, por isso o débito útil foi 0.
?2 Todos os pedidos foram cortados pelo timeout de 10 s da ferramenta de carga.

**Porque é que a ingestão parou, se o portal estava só lento?** Cada pedido à ingestão fica à espera das respostas do portal. Com 3 s de atraso e 3 workers, o portal só consegue responder a cerca de 1 pedido por segundo, e os pedidos acumulam-se na ingestão até rebentarem por timeout. A lentidão do portal passou para a ingestão através da chamada síncrona. Mesmo com o portal saudável já se nota o efeito: o débito cai de 313 para 10,8 req/s, porque cada lote faz cerca de 9 chamadas seguidas ao portal.

**O que cada padrão mudou:**

- **Timeout 500 ms:** deixou de perder leituras, mas continua lento. A chamada desiste ao fim de 0,5 s e a leitura é aceite sem validação. Cada lote ainda espera até 0,5 s por cada dispositivo.
- **Retry:** pior do que só o timeout, com 100% de perdas. Com 3 tentativas por dispositivo, cada pedido passa dos 10 s. Repetir não ajuda quando o portal está sempre lento.
- **Circuit breaker:** o débito volta a 264 req/s, sem perdas. Depois de 5 falhas seguidas, deixa de chamar o portal durante 10 s e aceita logo as leituras.
- **Cache 60 s:** o mesmo débito, com p99 mais baixo, e as leituras ficam validadas. Os dispositivos já validados não voltam a ir ao portal. Durante a medição, o portal não recebeu nenhuma chamada.

Quando não conseguimos validar, aceitamos a leitura e marcamo-la para reconciliação (*fail open*). Clinicamente, perder um sinal vital é pior do que aceitar uma leitura de um dispositivo que pode não estar associado.

A cache é **replicação com consistência eventual e um limite explícito de desatualização** (B6): a ingestão guarda uma cópia dos dados do portal que pode estar até 60 s desatualizada.

## Simulador de gateway

O simulador está em `tp4/inicial/gateway/simulador.py` e corre com:

```bash
docker compose run --rm gateway --dispositivos 10 --frequencia 1 --anomalias 0.02
```

Gera FC com variabilidade, SpO₂ com oclusões ocasionais e temperatura com deriva lenta. É configurável (número de dispositivos, frequência, endereço) e pode injetar valores anómalos. Quando a ingestão não responde, guarda as leituras num ficheiro local e reenvia-as quando ela volta. Respostas `4xx` não são guardadas, porque repetir não as torna válidas.

| Teste                        | Resultado                                                                   |
| :---                         | :---                                                                        |
| Envio normal                 | 360 leituras enviadas, 360 gravadas                                         |
| Ingestão parada durante 15 s | 510 leituras guardadas no buffer e todas reenviadas quando voltou           |
| Buffer entre execuções       | As 120 leituras que ficaram no ficheiro foram enviadas na execução seguinte |
| Anomalias a 5%               | Valores como FC 35 bpm, SpO₂ 75,9% e TEMP 40,1 ºC chegaram à base de dados  |

Isto é comunicação persistente feita à mão (B4). Na TP é o RabbitMQ que faz este papel.

**Nota:** acrescentámos `portal` ao `ALLOWED_HOSTS` do Django já que sem isso o portal recusava as chamadas da ingestão.
