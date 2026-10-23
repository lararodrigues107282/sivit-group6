# Respostas à TP3 - Laboratório de SIVIT

Medições feitas no ambiente Docker Compose (PostgreSQL 16, Gunicorn com 3 workers), com a base de dados de teste preenchida pelos comandos de gestão `medir_n1` e `medir_paginacao`.

## Idempotência na ingestão de leituras

1. **Semântica de falha:** A ingestão de um lote corre dentro de `transaction.atomic()`. Se ocorrer um erro a meio (por exemplo, uma falha de ligação à base de dados), a transação faz *rollback* e nenhuma leitura do lote fica gravada. O gateway recebe o erro e pode reenviar o lote inteiro sem risco de duplicação. As leituras que já existiam são ignoradas por `bulk_create(ignore_conflicts=True)`, que não é tratado como erro.

2. **UNIQUE vs chave de idempotência:** A restrição `UniqueConstraint(device, instant, parameter)` garante a integridade dos dados: impede que a mesma medição fique duas vezes na base, independentemente de quantos pedidos a repetem. Por si só, não devolve uma resposta ao cliente. Uma chave de idempotência (`IdempotencyKey`) guarda a resposta de um pedido identificado por uma chave e devolve essa mesma resposta nos retries. Para as leituras, a chave natural (dispositivo, instante, parâmetro) é suficiente, porque identifica univocamente cada medição. A `IdempotencyKey` justifica-se em operações sem chave natural. A tabela existe na migração `0002`, mas ainda não é usada pela API.

3. **Resposta escrita fora da transação:** Se a resposta se perder depois do *commit*, o gateway repete o pedido. As leituras já estão gravadas, o UNIQUE impede os duplicados, e a segunda resposta devolve `inseridas: 0`. Se a falha ocorrer antes do *commit*, nada ficou gravado e o retry insere o lote completo. O teste `test_resposta_perdida_seguida_de_retry_e_correta` verifica este caso. Limitação: o valor `inseridas` é calculado pela diferença de `count()` antes e depois da inserção. Com pedidos concorrentes, outro pedido pode inserir leituras entre as duas contagens, e o número reportado fica errado, embora os dados estejam corretos. O valor deve ser lido como indicação, não como garantia.

4. **Tempo de retenção das chaves:** Uma chave deve ser guardada pelo menos durante a janela máxima de retry do gateway, com uma margem. Propomos 24 horas, usando o campo `created` para uma limpeza periódica. A limpeza ainda não está implementada.

## Paginação

Medição com 50 000 leituras num único dispositivo e página de 100 elementos. Mediana de 3 execuções.

| Estratégia | 1.ª página (ms) | Página 500 (ms) | Tamanho da 1.ª página (bytes) |
| :--- | ---: | ---: | ---: |
| Sem paginação | 37 008,3 | n/a (devolve tudo) | 4 850 001 |
| Offset (`?page=`) | 72,5 | 81,1 | 9 812 |
| Cursor (`?after=&limit=`) | 73,7 | 94,6 | 9 754 |

A ausência de paginação é a diferença mais clara: 37 segundos e 4,8 MB para mostrar 100 leituras. Entre offset e cursor, a diferença é pequena. Nesta consulta, o custo dominante é o `ORDER BY instant DESC`, que ordena as 50 000 linhas em todas as páginas. Por isso, a página 500 custa quase o mesmo que a primeira. A escolha entre offset e cursor não se justifica por estes números. O argumento para o cursor é teórico: com offset, a base de dados tem de percorrer e descartar todas as linhas anteriores à página pedida, e esse custo cresce com a profundidade da página.

## Plano de execução (EXPLAIN ANALYZE)

Consulta da página 500 (`OFFSET 49900 LIMIT 100`) sobre as 50 000 leituras, com e sem o índice composto `(device, -instant)`.

| Execução | Índice composto | Execution Time |
| :--- | :---: | ---: |
| Antes do `ANALYZE` | presente | 24,222 ms |
| Antes do `ANALYZE` | removido (em transação, com `ROLLBACK`) | 45,936 ms |
| Depois do `ANALYZE` | presente | 21,304 ms |
| Depois do `ANALYZE` | removido (em transação, com `ROLLBACK`) | 22,133 ms |

Observações:

- Em todas as execuções, o planeador usa o índice simples `vigilancia_reading_device_id_7cdac503` e faz um `Sort` em disco (*external merge*, 2840 kB). O índice composto não é escolhido.
- A estimativa do planeador mantém-se em 839 linhas, contra 50 000 reais, mesmo depois do `ANALYZE`. A causa provável é o filtro `device_id = (SELECT id ...)`, cujo valor só é conhecido em execução. Esta explicação não foi confirmada.
- A diferença de 24 para 46 ms na primeira execução é variação entre medições. Depois do `ANALYZE`, as duas versões ficam em 21 a 22 ms.
- Um `OFFSET 49900` obriga a ler 50 000 entradas de qualquer índice. O índice só evita o `Sort`, não as leituras. Por isso, o ganho de um índice para paginação em profundidade é limitado. Um índice compõe-se com a paginação por cursor, que pára ao fim de 100 linhas. Este cenário não foi medido.

## Contrato da API: OpenAPI vs `.proto`

A API está documentada em OpenAPI, gerada automaticamente pelo `drf-spectacular` em `/api/schema/` e visualizada no Swagger UI. O contrato usa JSON sobre HTTP, que qualquer navegador ou cliente HTTP consegue consumir.

Um ficheiro `.proto` (Protocol Buffers, usado em gRPC) descreve um contrato binário sobre HTTP/2, com geração de código e mensagens mais compactas. É uma boa escolha para tráfego de alta frequência entre componentes internos, por exemplo entre o gateway e o backend.

Escolhemos OpenAPI porque o portal e os clientes externos consomem JSON, e porque a documentação interativa é útil para a equipa. Um `.proto` seria a alternativa a considerar para o canal de ingestão do gateway se o volume de leituras o justificar. Tem como custo a necessidade de ferramentas específicas e a impossibilidade de testar os endpoints diretamente no navegador.
