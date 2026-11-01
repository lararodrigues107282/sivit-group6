# TP5 · Comunicação assíncrona: RabbitMQ

> **Ambiente de medição:** um único portátil Windows com Docker Desktop. Todos os serviços (PostgreSQL, portal, ingestão em Uvicorn com 1 worker, RabbitMQ 3.13 e os consumidores) correm na mesma máquina e disputam o mesmo CPU e disco. A carga foi gerada com a ferramenta `carga` da TP4; a profundidade das filas com `rabbitmqctl list_queues`; a latência e a ordem com `latencia_de_logs.py` e `ordem_de_logs.py`. Cada valor corresponde a uma execução.

## Arquitetura implementada

```
gateway ─HTTP─▶ ingestão ─publish─▶ [exchange readings (topic)] ─┬─▶ [archive] ─▶ archive_worker  (grava na BD)
                                                                  ├─▶ [alarms]  ─▶ alarms_worker   (detetor)
                                                                  └─▶ [display] ─▶ display_worker  (painel)
                       cada fila ── rejeitadas / expiradas / descartadas ──▶ [readings.dlx (direct)] ─▶ <fila>.dlq
```

- **Ingestão** (`tp5/inicial/ingestao/main.py`): valida o lote como na TP4 e publica cada leitura na exchange `readings`, com `delivery_mode=PERSISTENT`, `message_id = dispositivo|instante|parâmetro`, `_published_at` no corpo e *routing key* `reading.<parâmetro>.<dispositivo>`. As 10 publicações do lote seguem em paralelo (`asyncio.gather`), com *timeout* de 5 s. Se o broker falhar ou recusar, responde `503`. `POR_FILA=0` volta à escrita direta da TP4; `CONFIRMS=0` desliga os *publisher confirms*.
- **Consumidores** (`tp5/inicial/worker/`): o código comum (`comum.py`) declara a topologia (a fila durável, a sua DLQ, `x-message-ttl` de 1 h, `x-max-length` e `x-overflow`), aplica o `prefetch` e faz **ack manual depois de processar**. Mensagem malformada → `reject(requeue=False)` → DLQ. Erro transitório (por exemplo, BD em baixo) → `nack(requeue=True)`. Cada mensagem processada escreve uma linha JSON (`evento`, `ts`, `fila`, `latencia_ms`, `id`). Os botões das experiências (`PREFETCH`, `TRABALHO_MS`, `ACK_AUTOMATICO`, `MORRER_APOS`, `MORRER_ANTES_DO_ACK`, `SEM_ON_CONFLICT`, `MAX_MENSAGENS`, `POLITICA_CHEIA`) são variáveis de ambiente.
- `archive.py` grava com `INSERT … ON CONFLICT DO NOTHING` (idempotente); `alarms.py` aplica limiares (FC 40–130, SpO₂ ≥ 90, TEMP 35–39); `display.py` guarda o último valor de cada dispositivo e ignora leituras mais antigas do que a que já tem; `stats.py` é o 4.º consumidor do exercício 2.4.
- As filas são declaradas pelos **consumidores**, nunca pela ingestão.

## Exercício 1 · Broker e publicação

Gerador de carga contra `POST /v1/readings`, lotes de 10, **50 clientes concorrentes durante 15 s**.

| Modo | Débito (req/s) | p50 (ms) | p99 (ms) | Leituras perdidas |
|---|---|---|---|---|
| Escrita direta na BD (`POR_FILA=0`, como em TP4) | 250,6 | 122 | 941 | 0 |
| Publicação na fila, com *publisher confirms* | 135,7 | 239 | 1 652 | 10 (¹) |
| Publicação na fila, sem *publisher confirms* | 164,2 | 210 | 1 320 | 0 |

(¹) Um único pedido terminou com `ReadError` (a ligação caiu a meio). Não houve recusa do broker, e um gateway real reenviaria esse lote.

Estado das filas logo a seguir à medição com *confirms*:

```
name         messages  consumers
display      0         1
alarms       0         1
archive      13040     1
archive.dlq  3         0
alarms.dlq   3         0
display.dlq  3         0
```

1. **`delivery_mode=PERSISTENT` e `durable=True`: o que falha se faltar cada um?** São precisos os dois. Sem `durable=True`, a fila (ou a exchange) é apagada quando o RabbitMQ reinicia, e com ela todas as mensagens e *bindings*. Sem `PERSISTENT`, a fila sobrevive mas as mensagens só estavam em memória, por isso perdem-se e a fila volta vazia. Isto confirmou-se no exercício 4.1: depois de parar e voltar a arrancar o broker, as 5 mensagens que estavam em `alarms.dlq` e `display.dlq` continuavam lá.

2. **Porque é que o `message_id` é construído a partir do conteúdo?** Porque é a chave de deduplicação dos consumidores. Com `dispositivo|instante|parâmetro`, a mesma leitura tem sempre o mesmo id, mesmo que o gateway reenvie o lote ou o broker a reentregue depois de uma falha do consumidor. Um UUID aleatório daria um id novo a cada reenvio e tornaria impossível reconhecer a repetição.

3. **O contrato HTTP mudou? Porquê?** Não. Continua `POST /v1/readings` com resposta `202 Accepted` e o mesmo corpo. Foi por isso que escolhemos `202` em vez de `201` na TP4: "aceite" nunca quis dizer "gravado", e agora é literalmente assim, porque a leitura fica na fila e é gravada depois pelo `archive_worker`. Os gateways não precisaram de nenhuma alteração.

4. **A ingestão ficou mais rápida?** **Não, nesta máquina.** A publicação na fila deu 136–164 req/s contra 251 req/s com escrita direta, e o p99 subiu de 0,9 s para 1,3–1,7 s. Há duas razões:
   - **Mais trabalho por pedido:** com escrita direta, cada lote é um único `executemany`. Com fila, são 10 mensagens persistentes que o broker escreve em disco e copia para 3 filas.
   - **Disputa de recursos:** com escrita direta só trabalham a ingestão e o PostgreSQL. Com fila, ao mesmo tempo correm o RabbitMQ, 3 workers (cada um a escrever uma linha de log por mensagem) e o `archive_worker` a escrever no mesmo PostgreSQL.

   Desligar os *confirms* recupera cerca de 20%: é o custo de esperar pela confirmação de que o broker guardou a mensagem, que se troca pela garantia de saber se ela foi aceite.

   O estado das filas mostra o essencial: a `archive` ficou com 13 040 mensagens por gravar. **A fila não fez o trabalho desaparecer; adiou-o.** A vantagem da fila não é o débito da ingestão; é o isolamento, que o exercício 2 demonstra.

## Exercício 2 · Consumidores e as quatro razões

| Experiência | Métrica | Com fila | Sem fila (TP4) |
|---|---|---|---|
| Pico 10× (60 s) | Leituras perdidas | **0** (88 880 aceites = 88 880 gravadas) | **0** (medido com `POR_FILA=0`) |
| Consumidor lento (20 ms/leitura) | Débito da ingestão | **Inalterado**: 9,9 req/s, p99 107–113 ms | Estimado: +200 ms por pedido; não aguentaria a carga nominal |
| Consumidor em baixo (2 min) | Leituras perdidas | **0** (11 950 acumuladas e gravadas) | Pedidos falham; a perda depende do buffer de cada gateway |
| Novo consumidor | Linhas alteradas no produtor | **0** (ligado em ~3 s) | Uma chamada nova na ingestão, mais o tratamento das suas falhas |

### Pico

- **Carga:** 50 clientes durante 60 s com `--taxa 400` (10× a carga nominal de 40 req/s). A ingestão sustentou **147 req/s** (cerca de 1 480 leituras/s), p99 de 1 611 ms.
- **Fila `archive`:** subiu cerca de 1 000 mensagens/s durante o pico e atingiu a **profundidade máxima de 57 525** no fim. Desceu depois a um ritmo constante de ~470 mensagens/s, que é o débito do `archive_worker`, e **esvaziou em cerca de 2 minutos** (18:31:43 → 18:33:47).
- **Contagem:** 88 880 leituras aceites e **88 880 gravadas**, ou seja, 0 perdidas.
- **Sem fila (`POR_FILA=0`, mesma carga):** 252 req/s, p99 de 1 025 ms, 0 perdidas.

O pico mostra para que serve a fila: as leituras chegaram três vezes mais depressa do que o arquivo as conseguia gravar, e o excesso esperou na fila em vez de se perder ou de travar a ingestão. O custo é a **consistência eventual**: no pior momento, a BD estava 57 525 leituras atrás do que tinha sido aceite.

Nesta experiência, a escrita direta também não perdeu nada e foi mais rápida, porque o PostgreSQL aguenta o pico gravando em lote. O ponto lento do sistema com fila é o `archive_worker`, que grava uma leitura de cada vez. A fila ganha quando o consumidor é **mais lento do que o pico**, que é o caso do detetor de arritmias (experiência seguinte).

### Consumidor lento

`TRABALHO_MS=20` e `PREFETCH=1` no `alarms_worker` (capacidade teórica de 50 leituras/s por worker). Carga de 10 req/s × 10 leituras (100 leituras/s) durante 60 s.

| Detetor | Débito da ingestão (req/s) | p50 (ms) | p99 (ms) |
|---|---|---|---|
| Normal | 9,9 | 69 | 161 |
| Lento, 1 *worker* | 9,9 | 61 | 109 |
| Lento, 2 *workers* | 9,9 | 61 | 107 |
| Lento, 4 *workers* | 9,9 | 59 | 113 |

| *Workers* de alarmes | Profundidade da fila `alarms` ao fim de 60 s |
|---|---|
| 1 | 3 345 |
| 2 | 765 |
| 4 | 0 |

A ingestão não deu pela lentidão do detetor: o débito e a latência ficaram iguais, e as diferenças são ruído. O atraso ficou contido na fila `alarms`. Na prática, cada *worker* processou ~43 leituras/s, e não as 50 teóricas, por causa da ida e volta ao broker entre mensagens com `prefetch=1`. Por isso 2 *workers* ficaram ligeiramente abaixo das 100 leituras/s que chegavam, e com 4 sobrou capacidade. **Escalar resolveu o problema sem tocar em código** (`--scale alarms_worker=4`).

Sem fila, a ingestão chamaria o detetor diretamente: 10 × 20 ms = **+200 ms por pedido**. Com 5 clientes, ficaria limitada a cerca de 25 req/s e não aguentaria a carga nominal de 40 req/s. É a falha em cascata da TP4, agora provocada pelo detetor em vez do portal.

### Consumidor em baixo

`archive_worker` parado durante **2 minutos**, com carga constante de 10 req/s (100 leituras/s).

- **Acumuladas:** a `archive` ficou com **11 950 mensagens** e 0 consumidores (todas as aceites). A ingestão manteve o ritmo e um p99 de 132 ms, sem dar pela falha.
- **Recuperação:** depois de `docker compose start archive_worker`, a fila **esvaziou em menos de 30 s**.
- **Contagem:** **11 950 leituras gravadas**, ou seja, 0 perdidas.

Sem fila, cada pedido teria falhado durante os 2 minutos. A leitura só sobreviveria se o gateway a guardasse e reenviasse, o que depende de cada gateway ter disco e lógica para isso. Com a fila, essa responsabilidade passa para um único componente durável.

### Novo consumidor

O `stats.py` tem 10 linhas, porque reutiliza o `comum.py`. Para o ligar: `docker compose --profile fanout up -d --build stats_worker`, que levou **~3 s** (build 2,0 s com a imagem em cache, mais o arranque 1,0 s). O consumidor declarou ele próprio a fila `stats` e a `stats.dlq`, fez o *bind* à exchange `readings` e passou logo a receber uma cópia de todas as leituras. **A ingestão não foi alterada nem reiniciada**: continuou "Up 16 minutes". O código já estava escrito antes da medição; escrevê-lo de raiz levaria cerca de um minuto, dentro do que o guião prevê.

**Cuidado observado:** uma fila durável continua a existir depois de o consumidor desaparecer, e enche-se em silêncio. Se o `stats_worker` fosse apenas parado, a fila `stats` acumularia todas as leituras até `x-max-length`, e a partir daí o broker recusaria publicações (`reject-publish`) e a ingestão passaria a responder `503`. Retirar um consumidor implica apagar a sua fila (ver 4.4).

## Exercício 3 · Fiabilidade e idempotência

**(a) Acks.** 200 mensagens na `archive` com o consumidor parado. O consumidor arranca com `MORRER_APOS=20` e termina (`os._exit(1)`) ao fim de 20. Depois é reposto um consumidor saudável.

| Modo | Publicadas | Gravadas antes da morte | Na fila depois | Na BD depois de repor o consumidor | Perdidas |
|---|---|---|---|---|---|
| `auto_ack=True` | 200 | 20 | 0 | 20 | **180** |
| ack manual | 200 | 20 | 180 | 200 | **0** |

Com ack automático, o broker considera a mensagem tratada no momento da entrega e apaga-a. O *prefetch* não se aplica, e o consumidor recebeu as 200 de uma vez. Gravou 20, morreu, e as outras 180 morreram com ele: **90% de perda num único crash**. Com ack manual depois de processar, as mensagens sem ack voltaram à fila e o consumidor saudável gravou-as todas.

**(b) Prefetch.** 3 000 mensagens na fila `alarms`, consumidas por **2 *workers*** sem trabalho artificial.

| prefetch | Mensagens processadas em ___ s | Débito | Por *worker* | Atraso se um *worker* morrer |
|---|---|---|---|---|
| 1 | 3 000 em 1,59 s | 1 887 msg/s | 1 594 / 1 406 (53/47 %) | até 1 mensagem reentregue |
| 10 | 3 000 em 1,16 s | 2 586 msg/s | 1 701 / 1 299 (57/43 %) | até 10 |
| 100 | 3 000 em 0,83 s | 3 634 msg/s | 1 797 / 1 203 (60/40 %) | até 100 |

Mais *prefetch* dá mais débito, porque o *worker* nunca fica parado à espera da próxima mensagem depois de cada ack. Mas a distribuição piora (quem arranca primeiro reserva um bloco maior), e um *worker* que morra deixa mais mensagens por reentregar. Se ficar "pendurado" sem fechar a ligação, essas mensagens só voltam quando o *heartbeat* expirar. As medições duraram menos de 2 s cada, por isso têm ruído, mas a tendência é clara.

**Escolha para o arquivo: `prefetch=10`.** Ganha a maior parte do débito face a 1 e um crash atrasa no máximo 10 leituras. Subir para 100 pouco adiantaria, porque o limite do arquivo é a BD (~470 gravações/s no pico). **Para os alarmes, `prefetch=1`:** o detetor é pesado, a carga fica bem distribuída pelos *workers*, e nenhum alarme fica preso atrás de um bloco de mensagens num *worker* lento ou morto.

**(c) Duplicação.** 200 mensagens. O consumidor grava e morre antes do ack (`MORRER_APOS=20`, `MORRER_ANTES_DO_ACK=1`). Em ambos os casos houve **duas mortes**, cada uma deixando uma leitura gravada e sem ack, que o broker reentregou. Depois, um consumidor saudável esvaziou a fila.

| Consumidor | Publicadas | Linhas na BD | Leituras distintas | Duplicadas |
|---|---|---|---|---|
| com `ON CONFLICT` | 200 | 200 | 200 | **0** |
| sem `ON CONFLICT` (e sem `UNIQUE`) | 200 | 202 | 200 | **2** |

Uma duplicada por cada morte. A reentrega é inevitável com ack manual: é o preço de não perder mensagens (*at-least-once*). Se duplica ou não, depende do consumidor. O `archive_worker` é idempotente graças ao `ON CONFLICT (device_id, instant, parameter) DO NOTHING`, apoiado pela restrição `UNIQUE` e por um `message_id` derivado do conteúdo. No fim, os 2 duplicados foram apagados e a restrição `uniq_reading` foi reposta.

**(d) Dead-letter queue.** Injetámos **5 mensagens malformadas** (`{"lixo": i}`, com o `veneno.py`) no meio de 240 leituras normais. Cada consumidor rejeitou-as com `reject(requeue=False)` (motivo no log: `KeyError: 'device'`) e o broker encaminhou-as pela `readings.dlx` para a DLQ da própria fila: **5 em `archive.dlq`, 5 em `alarms.dlq` e 5 em `display.dlq`**. As filas principais ficaram a 0 e as 240 leituras boas foram processadas. A mensagem envenenada saiu do caminho à primeira rejeição, em vez de ficar num ciclo de reentregas a bloquear a fila. Os erros transitórios seguem outro caminho: a BD em baixo dá `nack(requeue=True)` e não DLQ.

*O que se faz com a DLQ, e quem é responsável por olhar para ela?* A DLQ não é um caixote do lixo; é uma **caixa de pendentes clínicos**: cada mensagem é uma leitura que ninguém processou. Precisa de:
1. um alerta logo que tenha mensagens (ver 4.4);
2. um responsável, a equipa de operações e integração, que lê o motivo (cabeçalho `x-death` e log do consumidor) e corrige a causa (por exemplo, gateway com firmware avariado ou bug na ingestão);
3. um procedimento para reenviar para a fila principal o que for recuperável e descartar, com registo, o que não for.

Uma DLQ que ninguém vigia é só outra forma de perder dados.

**(e) Limite de tamanho.** Fila `archive` com `x-max-length=100`, consumidor parado e 300 leituras enviadas (30 lotes).

| Política | Na fila | `archive.dlq` | Resposta da ingestão |
|---|---|---|---|
| `reject-publish` | 100 | 0 | 10 pedidos `202`, **20 pedidos `503`** (200 leituras recusadas) |
| `drop-head` | 100 | **200** | 30 pedidos `202`, 0 erros |

Com `reject-publish`, a partir da 100.ª mensagem o broker respondeu *nack*, a ingestão (com *confirms*) devolveu `503` e **o gateway fica a saber** que tem de guardar e reenviar. Com `drop-head`, a ingestão aceitou tudo, mas o broker descartou as 200 **mais antigas** para dar lugar às novas. Aqui foram parar à DLQ porque a fila tem DLX; sem DLX, ter-se-iam perdido em silêncio.

**Escolha para o SIVIT:**
- **Arquivo: `reject-publish`.** O arquivo é o registo clínico e legal; um buraco silencioso no histórico de um doente não é aceitável. É preferível recusar e passar a pressão para os gateways, que guardam e reenviam.
- **Fila de alarmes: `drop-head` é defensável.** Uma leitura com minutos já não serve para disparar um alarme, e descartar as mais antigas mantém o detetor no presente.

**Consequência a ter em conta:** com `reject-publish`, a recusa foi só da `archive`. As filas `alarms` e `display` receberam as 300, por isso o reenvio do gateway vai entregá-las outra vez. Mais uma razão para todos os consumidores serem idempotentes.

*Uma fila sem limite não é segura: é uma falha de memória adiada.*

## Exercício 4 · Os novos problemas

1. **O broker é um SPOF.** Com o RabbitMQ parado:
   - o `/health/ready` passou a responder `unavailable` (`ConnectionError broker`);
   - os **19 pedidos receberam `503`**, em ~6 ms cada, sem a ingestão ficar pendurada, e 190 leituras foram recusadas (ficam no buffer dos gateways).

   Ao voltar a arrancar o broker, em menos de 20 s, o `ready` voltou a `ok` e os pedidos seguintes tiveram 0 erros. A ingestão e os três consumidores **religaram-se sozinhos** (`connect_robust`), sem reinício, e as mensagens persistentes das DLQ sobreviveram.

   **Ganhámos ou perdemos disponibilidade?** Sem mais nada, perdemos: a ingestão passou a depender de mais um componente e, com ele em baixo, nenhuma leitura entra. Mas é uma troca deliberada. Em vez de depender do arquivo, do detetor e do painel, a ingestão depende só do broker, que é um componente desenhado para ser replicado. **Solução:** um cluster RabbitMQ de 3 nós com *quorum queues* (réplicas por consenso Raft), para que a falha de um nó não pare as filas. É requisito do Trabalho 2.

2. **Ordenação.** Carga com 1 cliente, 30 req/s e apenas 6 dispositivos (muitas leituras consecutivas do mesmo), `TRABALHO_MS=5` no `alarms_worker`.

   | *Workers* de alarmes | Pares consecutivos por dispositivo | Fora de ordem | % |
   |---|---|---|---|
   | 1 | 6 224 | **0** | 0 % |
   | 4 | 10 488 | **669** | **6,4 %** |

   Um *worker* processa a fila pela ordem. Com 4, cada um recebe o seu bloco (*prefetch*), e basta um ser mais rápido para a leitura das 18:00:01 de um monitor ser processada antes da das 18:00:00. (Os totais de pares não coincidem porque, com 1 *worker* a 5 ms/leitura, ficaram mensagens por processar que entraram na segunda medição. A comparação de percentagens mantém-se.)

   **Onde importa no SIVIT:**
   - **Arquivo:** não importa, porque cada linha guarda o seu `instant` e quem consulta ordena por ele.
   - **Painel:** importa, porque podia mostrar um valor antigo como atual. O nosso `display.py` já se protege, porque só substitui por uma leitura mais recente.
   - **Alarmes:** **importa muito**. Um detetor de arritmias analisa sequências; com a ordem trocada vê padrões que não existem ou falha os que existem.

   **Como se resolve:** **partição por dispositivo**. Todas as leituras de um monitor vão sempre para a mesma fila, por exemplo `alarms.0` a `alarms.N` com uma *consistent hash exchange* sobre o dispositivo, e cada fila tem um único consumidor. Há paralelismo entre dispositivos e ordem dentro de cada um, que é a consistência causal do B6. No Kafka isto é nativo: a chave da mensagem determina a partição.

3. **Latência não determinística.** Distribuição do tempo entre publicação e processamento no `alarms_worker` (1 *worker*, sem trabalho artificial):

   | Carga | Amostras | p50 (ms) | p99 (ms) | p99/p50 |
   |---|---|---|---|---|
   | Normal (40 req/s, 400 leituras/s) | 11 950 | 12,6 | 29,2 | 2,3 |
   | Pico (217 req/s, ~2 200 leituras/s) | 65 510 | 7,4 | 261,0 | **35,3** |

   Em carga normal a latência é previsível. No pico, a maioria das leituras continua rápida, mas **a cauda explode**: o p99 é 9× o p99 normal e 35× o p50. A latência passa a depender de quantas mensagens estão à frente na fila. No fim do pico, a `archive` tinha 15 925 mensagens em atraso e a `alarms` já estava a 0: separar as filas protegeu os alarmes do arquivo, mas a latência dos alarmes subiu na mesma, porque a fila `alarms` recebe todas as leituras. Com um detetor realmente pesado é pior. Na experiência 2.2 (20 ms/leitura, 1 *worker*) ficaram 3 345 mensagens na fila, a ~43 por segundo, ou seja, **mais de um minuto** de espera para a última leitura.

   **Decisão para os alarmes:** um alarme com SLO de 2 s (B8) **não pode depender da profundidade de uma fila que recebe todas as leituras**. Os alarmes precisam de:
   - consumidores dedicados, dimensionados com folga e escalados à parte;
   - **prioridade**: uma fila própria para leituras suspeitas, ou uma *priority queue*, que não espera atrás do tráfego normal;
   - um **pré-filtro barato** que só encaminhe para o detetor pesado as leituras que o justificam.

4. **Visibilidade.** Durante as experiências, a fila `archive` chegou a 57 525 mensagens sem qualquer aviso. Uma fila esquecida (`stats`) teria enchido em silêncio até a ingestão começar a responder `503`. Os alertas que definimos:

   | Alerta | Condição | Justificação |
   |---|---|---|
   | Fila acumulada | profundidade > **10 000 durante 5 min** | Um pico normal escoa em 2–3 min (medido em 2.1). Se persiste, o consumidor não acompanha |
   | Fila sem consumidor | `consumers = 0` durante > 1 min | Consumidor morto ou fila órfã: vai encher até `x-max-length` |
   | DLQ não vazia | qualquer `*.dlq` com > 0 mensagens | Cada mensagem é uma leitura clínica não processada |
   | Atraso nos alarmes | `alarms` > 1 000 mensagens, ou mensagem mais antiga com > 2 s | O SLO dos alarmes exige um limite muito mais apertado do que o do arquivo |

   As métricas já existem no broker (`rabbitmqctl list_queues name messages consumers`, a API da consola de gestão e o *plugin* `rabbitmq_prometheus`). Os alertas definem-se no Prometheus e no Alertmanager.
