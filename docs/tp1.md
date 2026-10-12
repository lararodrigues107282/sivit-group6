# Respostas TP1 - Lab SIVIT

## Exercício 1

1. Processos no host:
Sim, aparecem na lista de processos do host Linux (no Docker Desktop, a VM WSL2): visto da VM, o `nginx: master process` tem o PID 1985. No Windows não aparecem (`tasklist | findstr nginx` não devolve nada), porque o "host" Linux é a VM. Isto acontece porque um contentor não tem kernel nem Sistema Operativo próprio como uma máquina virtual: é um processo normal a correr no kernel do host, isolado do resto. Um contentor é um processo, mais namespaces (o que vê), mais cgroups (o que pode consumir).

2. Namespaces:
Os namespaces em /proc/<pid>/ns/ definem o que cada processo tem autorização para "ver":
- pid: a árvore de processos
- net: as interfaces de rede e portas
- mnt: os pontos de montagem do sistema de ficheiros
- ipc: a comunicação entre processos
- uts: o nome da máquina (hostname)
- user: os utilizadores e grupos
- cgroup: a vista dos cgroups
- time: os relógios do sistema

Aparecem ainda `pid_for_children` e `time_for_children`, que indicam o namespace em que os processos filhos vão ser criados.

3. ps aux:
Os dois comandos mostram PIDs diferentes para o mesmo processo porque o contentor está preso ao seu próprio namespace de PIDs. Dentro do contentor (`docker exec web ps aux`), o nginx principal é o PID 1 e só se veem os processos do contentor. Visto do host (a VM), o mesmo processo é o PID 1985, porque o host está no namespace raiz e vê os processos de toda a máquina.

4. Limite de memória:
O script de Python tentou alocar cerca de 200 MB, ultrapassando o limite de 64 MB definido para o contentor, e foi morto: o contentor terminou com código de saída 137 (128 + 9, o sinal SIGKILL). O cgroup define e mede o limite de memória; o OOM Killer do kernel é quem age quando o limite é ultrapassado, matando o processo.


## Exercício 4

| Contexto                    | p50 (ms) | p95 (ms) | p99 (ms) |
| :-------------------------- | :------: | :------: | :------: |
| Local function call         |  0.0001  |  0.0001  |  0.0006  |
| HTTP to localhost           |   1.18   |   1.68   |   3.49   |
| HTTP between containers     |   1.07   |   1.49   |   1.93   |
| HTTP to a UMinho server     |  460.56  |  508.38  |  543.28  |
| HTTP to a server in the USA |  313.80  |  378.25  |  421.45  |

- Plataforma: Windows 11, Docker Desktop (WSL2).
- Servidores remotos: www.uminho.pt e dynamodb.us-east-1.amazonaws.com (Virginia, EUA), com ligação nova em cada pedido e 50 amostras. Com tão poucas amostras o p99 é praticamente o máximo, por isso o p50 e o p95 são os valores mais fiáveis. Repetindo a medição aos EUA, o p50 foi 326,90 ms (contra 313,80 ms), o que mostra a variação entre execuções.
- Reutilizando a ligação (p50): UMinho 364,41 ms e EUA 99,88 ms.

1. Ordens de magnitude:
A chamada local demorou cerca de 0.0001 ms, enquanto o pedido ao servidor nos EUA demorou 313,80 ms (p50). Isto é cerca de 3 milhões de vezes mais, ou seja, cerca de 6,5 ordens de magnitude.

2. p99 entre contentores:
O p99 (1.93 ms) sobe em relação ao p50 (1.07 ms) porque, mesmo sendo local, o tráfego HTTP tem de passar pela stack de rede (TCP/IP). Nessas percentagens mais altas começam a pesar pequenas variações como trocas de contexto no CPU, contenção de recursos ou eventuais pausas do runtime de Python.

3. Efeito N+1:
- Sequencial: os tempos, no caso os 30 pedidos a 4 ms, somam-se até aos 120 ms. Contudo, isto é só a soma dos p95, não o p95 real do pedido.
- Probabilidade: um p95 de 4 ms quer dizer que 5% das chamadas passam dos 4 ms. A probabilidade de as 30 ficarem todas abaixo é 0,95^30 ≈ 0,21, por isso cerca de 79% dos pedidos apanham pelo menos uma chamada lenta.
- Paralelo: o pedido demora o tempo da chamada mais lenta. Para o p95 do pedido ser 4 ms, cada chamada teria de ficar abaixo de 4 ms em 99,8% dos casos, mas só 95% ficam. Logo o p95 do pedido é superior aos 4 ms.

4. Falácia refutada:
A falácia nº 2, "a latência é zero", é refutada pelos valores: 0,0001 ms numa chamada local contra 1,07 ms entre contentores, cerca de 4 ordens de magnitude sem sair do computador, e 313,80 ms até aos EUA (cerca de 6,5 ordens). Nos EUA, reutilizar a ligação baixa o p50 de 314 para 100 ms, ou seja, abrir uma ligação nova custa cerca de 3 vezes mais, o que é consistente com o handshake TCP e TLS acrescentarem idas e voltas. Na UMinho, reutilizar a ligação só baixa de 460 para 364 ms, por isso o custo está sobretudo no que acontece depois de a ligação estar aberta (tempo de resposta do servidor e transferência da página). Assim, o servidor da UMinho, apesar de mais perto, é mais lento do que o dos EUA: a latência não depende só da distância.