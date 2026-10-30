# Respostas à TP5 - RabbitMQ e ingestão assíncrona

## Exercício 1: Publicação em vez de Escrita Direta

1. **`PERSISTENT` e `durable=True`:** É necessário usar os dois para garantir que as mensagens sobrevivem a um reinício do broker. Se faltar `durable=True` na declaração da fila ou do *exchange*, a topologia é apagada quando o RabbitMQ reinicia. Por outro lado, se faltar `PERSISTENT` nas mensagens, estas ficam apenas em memória, mesmo que a fila seja durável, e podem perder-se se o broker reiniciar.

2. **Chave de idempotência:** O `message_id`, criado a partir do conteúdo (`device|instant|parameter`), funciona como uma chave natural para identificar e evitar o processamento duplicado das mesmas leituras pelos consumidores.

3. **Contrato HTTP:** O contrato mantém-se igual, com o código `202 Accepted`. Assim, não foi necessário alterar nenhuma linha de código do `gateway` do laboratório anterior.

4. **Ganho de desempenho:** A ingestão fica mais rápida porque deixa de esperar pela escrita na base de dados para cada leitura. Em vez disso, a API publica a mensagem no RabbitMQ de forma assíncrona e devolve imediatamente uma resposta `202`.

## Exercício 2: As Quatro Razões (Experiências)

| **Experiência** | **Métrica** | **Com Fila (TP5)** | **Sem Fila (TP4)** |
|---|---|---|---|
| **Pico de 10x (60s)** | Leituras perdidas | **0** (as mensagens ficam armazenadas no broker) | Elevadas (rejeições ou timeouts na base de dados) |
| **Consumidor lento** | Débito de ingestão | **Inalterado** (o broker absorve o atraso através da fila) | A ingestão fica bloqueada à espera do processamento |
| **Consumidor em baixo** | Leituras perdidas | **0** (as mensagens acumulam-se na fila até o consumidor recuperar) | As leituras perdem-se imediatamente |
| **Novo consumidor** | Linhas alteradas no produtor | **0** (desacoplamento através de *exchanges* e *routing keys*) | É necessário alterar o código do produtor para adicionar novas chamadas |

## Exercício 3: Fiabilidade, Acks e Duplicados

1. **(a) `auto_ack=True` vs. Ack manual:** Com `auto_ack=True`, o RabbitMQ retira a mensagem da fila assim que a envia ao consumidor. Se o trabalhador falhar durante o processamento, a mensagem perde-se. Com o ack manual (`ack()`), a mensagem só é confirmada depois de o processamento terminar com sucesso. Se o processo falhar antes dessa confirmação, o canal fecha-se e o broker volta a colocar a mensagem na fila (*requeue* automático).

2. **(b) Justificação do `prefetch`:** Um `prefetch_count` de **10** oferece um bom equilíbrio. Se usarmos 1, os trabalhadores passam demasiado tempo à espera de novas mensagens pela rede. Se usarmos 100, um trabalhador pode receber demasiadas mensagens de uma só vez, incluindo mensagens mais complexas, enquanto os outros ficam sem trabalho.

3. **(c) Duplicação e Idempotência:**
   - **Com `ON CONFLICT` / restrição `UNIQUE`:** O número de linhas na base de dados corresponde ao número de mensagens distintas. As mensagens entregues novamente devido a falhas do trabalhador são ignoradas, evitando a inserção de duplicados.
   - **Sem `ON CONFLICT`:** As mensagens repetidas podem gerar linhas duplicadas na base de dados.
   - **Conclusão:** Como as confirmações manuais podem provocar reenvios quando um trabalhador falha, é necessário garantir a idempotência do lado do consumidor, através de restrições ou *upserts*.

4. **(d) Mensagens Poison (DLQ):** Configurámos um *dead-letter exchange* (`readings.dlx`) e uma fila de apoio (`archive.dlq`) para cada fila principal. Assim, quando uma mensagem chega corrompida e é rejeitada com `requeue=False`, é encaminhada para a DLQ em vez de bloquear o processamento. Os erros temporários, como uma falha na base de dados, devem provocar um *requeue*, enquanto os erros permanentes devem encaminhar a mensagem para a DLQ.

## Exercício 4: O que a fila estragou (Novos Problemas)

1. **O Broker como SPOF:** Se o RabbitMQ parar, a ingestão deixa de funcionar imediatamente. Passámos a depender de um único ponto de falha, embora o RabbitMQ suporte mecanismos de replicação e *clustering*, incluindo filas com *quorum*, que permitem reduzir este risco.

2. **Ordenação:** Com vários trabalhadores a processar mensagens em paralelo, as leituras do mesmo dispositivo podem ser processadas fora de ordem. Uma possível solução é particionar as filas ou utilizar chaves de encaminhamento associadas ao identificador de cada dispositivo.

3. **Latência não determinística:** Em períodos de maior carga, a profundidade das filas aumenta e o percentil p99 do tempo de processamento pode disparar. Por isso, tarefas críticas, como os alarmes, não devem depender de filas partilhadas com tarefas de arquivo mais pesadas. Podemos utilizar consumidores dedicados ou filas com prioridade.

4. **Visibilidade:** A acumulação de mensagens ou os atrasos no processamento podem passar despercebidos até começarem a afetar os recursos do sistema, como o disco ou a memória. Definimos um alerta para quando a profundidade da fila ultrapassar **10 000 mensagens durante mais de 5 minutos**.
