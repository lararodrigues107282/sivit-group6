# Respostas à TP3 - Laboratório de SIVIT

## Exercício 2: Idempotência demonstrada
1. Neste exercício, apliquei a semântica at-least-once, que quando combinada com mecanismos de idempotência origina um comportamento exactly-once.
O utilizador pode inserir diversas vezes o seu pedido caso não lhe chegue uma resposta de que este foi submetido, levando à possibilidade do servidor receber mais do que um pedido igual, mas nunca nenhum. Assim, verificámos a implementação de at-least-once na entrega.
Esta semântica combinada com o comportamento do UNIQUE CONSTRAINT e da função de idempotência aplicados ao sistema geram um comportamento exactly-once. Assim, independentemente do número de vezes que o cliente submete o seu pedido, este será apenas guardado uma vez na base de dados. Trata-se de exactly-once no efeito e não na entrega.

2. Ambas evitam duplicados, no entanto UNIQUE CONSTRAINT fá-lo pela identidade natural dos dados: compara os parâmetros de uma leitura e rejeita a inserção de uma segunda igual. Já a chave de idempotência avalia o identificador da operação definido pelo utilizador: compara o identificador enviado pelo utilizador em várias tentativas e, se estes forem iguais devolve a resposta já guardada. 
Só a primeira funciona quando a mesma informação chega através de diferentes identificadores de operação. Por exemplo, quando o utilizador gera uma nova chave a cada tentativa.
Só a segunda funciona quando a operação não tem um identificador natural. Por exemplo, é possível que um doente receba alta mais do que uma vez durante a sua vida, no entanto, por falha, duas altas podem referir-se à mesma operação, sendo o identificador definido pelo utilizador que permite eliminar essa duplicação. 

3. Se a resposta for guardada fora da transação permite-se ao sistema ficar num estado inconsistente, caso o servidor falhe entre o registo da operação e da chave. Existem dois casos possíveis, o sistema guarda a operação sem chave registada, levando à possibilidade de repetição do pedido com a mesma chave - como o sistema não a encontra, executa a operação novamente. Ou, o registo de uma chave sem qualquer informação associada, fazendo com que o utilizador repita o pedido com a chave já guardada - o sistema devolve resposta de sucesso mas a operação nunca foi executada.
Na mesma transação, ou a operação e chave são registadas, ou nenhuma.

4. Uma chave de idempotência deve ser guardada mais tempo do que a janela máxima de novas tentativas do utilizador. Este tempo deve ser avaliado consoante o modelo em que esta é implementada. O trade-off é a avaliação das vantagens de guardar a chave durante menos tempo - menor espaço utilizado e maior privacidade - e de a guardar durante mais tempo - maior proteção contra com tentativas tardias.

## Exercício 3: Medição de Desempenho com 50 000 Registos

1. Tabela Comparativa de Estratégias de Paginação

| Estratégia | Primeira Página | Página 500 | Tamanho da Resposta |
| :--- | :--- | :--- | :--- |
| **Sem Paginação** (No pagination) | Lento / Risco de Timeout | N/A (Devolve todos os registos) | Muito Grande |
| **Offset** (`?page=`) | Rápido | Muito Lento | Pequeno |
| **Cursor** (`?after=<instant>&limit=100`) | Rápido | Muito Rápido | Pequeno |

