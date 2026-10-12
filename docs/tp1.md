# Respostas TP1 - Lab SIVIT

## Exercício 1

1. Processos no host:
Sim, eles aparecem. Isto acontece uma vez que um contentor não corre um SO Sistema Operativo próprio como numa máquina virtual, estes são apenas processos normais a correr diretamente no kernel do host, estando isolados do resto do sistema.

2. Namespaces:
Os namespaces em /proc/<pid>/ns/ definem o que cada processo tem autorização para "ver":
-- pid: a árvore de processos
-- net: as interfaces de rede e portas
-- mnt: os pontos de montagem do sistema de ficheiros
-- ipc: a comunicação entre processos

3. ps aux:
Estes comandos mostram processoas diferentes porque o contentor está preso ao seu próprio namespace de PIDs. Basicamente, para ele só existem os seus processos (com o processo principal a ser o PID 1). Por sua vez o host está no namespace raiz e consegue ver os processos de toda a máquina, incluindo os do contentor.

4. Limite de memória:
O script de Python tentou alocar à volta de 200MB, ultrapassando o limite de 64MB definido para o contentor. Quando isto acontece, o kernel intervém e mata o processo (OOM Killer). O mecanismo responsável por impor estes limites de recursos são os cgroups.


## Exercício 4

| Contexto                    | p50 (ms) | p95 (ms) | p99 (ms) |
| :-------------------------- | :------: | :------: | :------: |
| Local function call         |  0.0001  |  0.0001  |  0.0006  |
| HTTP to localhost           |   1.18   |   1.68   |   3.49   |
| HTTP between containers     |   1.07   |   1.49   |   1.93   |
| HTTP to a UMinho server     |  310.33  |  338.46  |  338.46  |
| HTTP to a server in the USA |  77.43   |  84.76   |  88.61   |

1. Ordens de magnitude:
A chamada local demorou cerca de 0.0001 ms, enquanto o pedido ao servidor nos EUA demorou 77.43 ms. Neste caso temos de uma diferença gigantesca de 6 ordens de magnitude.

2. p99 entre contentores:
O p99 (1.93 ms) sobe em relação ao p50 (1.07 ms) porque, mesmo sendo local, o tráfego HTTP tem de passar pela stack de rede (TCP/IP). Nessas percentagens mais altas começam a pesar pequenas variações como trocas de contexto no CPU, contenção de recursos ou eventuais pausas do runtime de Python.

3. Efeito N+1:
Sequencial: os tempos somam-se, logo 30 pedidos a 4 ms somam se até aos 120 ms. Contudo, isto é só a soma dos p95, não o p95 real do pedido.
Probabilidade: um p95 de 4 ms quer dizer que 5% das chamadas passam dos 4 ms. A probabilidade de as 30 ficarem todas abaixo é 0,95^30 = 0,21, por isso cerca de 79% dos pedidos apanham pelo menos uma chamada lenta.
Paralelo: o pedido demora o tempo da chamada mais lenta. Para o p95 do pedido ser 4 ms, cada chamada teria de ficar abaixo de 4 ms em 99,8% dos casos, mas só 95% ficam. Logo o p95 do pedido é superior aos 4 ms.

4. Falácia refutada:
A falácia nº 2, "a latência é zero" é refutada pelo facto de que temos 0,0001 ms numa chamada local contra os 1,07 ms entre contentores. Posteriormente, até aos EUA são 77,43 ms. Para concluir, como o servidor da Universidade (310 ms) ficou mais lento do que o dos EUA apesar de estar mais perto, podemos concluir que a latência não depende apenas da distância.