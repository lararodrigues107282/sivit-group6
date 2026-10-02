# Respostas à TP1 - Laboratório de SIVIT

## Exercício 1: Um contentor não é uma máquina

1. **Os processos aparecem no host?** Sim[cite: 21]. Isto demonstra que um contentor não é uma máquina virtual pesada com o seu próprio sistema operativo, mas sim um conjunto de processos normais a correr diretamente no *host*, mantidos em isolamento pelas funcionalidades do *kernel*[cite: 22].
2. **Namespaces:** Os diferentes *namespaces* visíveis em `/proc/<pid>/ns/` servem para isolar os recursos que o processo consegue ver e usar[cite: 21]. Por exemplo, o *namespace* `pid` isola a árvore de processos, o `net` isola as portas e interfaces de rede, o `mnt` isola o sistema de ficheiros e o `ipc` isola a comunicação entre processos.
3. **ps aux (Host vs Contentor):** Os resultados são totalmente diferentes porque o contentor está confinado ao seu próprio *namespace* de PIDs[cite: 21]. Como resultado, ele pensa que é o único sistema a correr e vê apenas os seus próprios processos (começando no PID 1). O *host*, por outro lado, tem visibilidade global sobre tudo.
4. **Limite de memória:** O processo Python tentou alocar cerca de 200MB de RAM, excedendo o orçamento rígido de 64MB que lhe foi atribuído, o que fez com que o *kernel* o "matasse" (*OOM Killed*)[cite: 22]. O mecanismo do *kernel* que aplica e policia estes limites de recursos chama-se `cgroups`[cite: 22].

## Exercício 4: Tabela de Latências e Análise

| Contexto | p50 (ms) | p95 (ms) | p99 (ms) |
| :--- | :---: | :---: | :---: |
| Local function call | 0.0001 | 0.0001 | 0.0006 |
| HTTP to localhost | 1.18 | 1.68 | 3.49 |
| HTTP between containers | 1.07 | 1.49 | 1.93 |
| HTTP to a UMinho server | 310.33 | 338.46 | 338.46 |
| HTTP to a server in the USA | 77.43 | 84.76 | 88.61 |

1. **Ordens de magnitude:** A chamada local de função demorou 0.0001 ms, enquanto o pedido intercontinental ao servidor dos EUA demorou 77.43 ms. Isto representa uma diferença brutal de quase 6 ordens de magnitude (aproximadamente 774 mil vezes mais lento).
2. **p99 elevado entre contentores:** O p99 (1.93 ms) é consideravelmente superior ao p50 (1.07 ms) porque, mesmo comunicando dentro da mesma máquina, os pedidos HTTP são forçados a percorrer a *stack* de rede do sistema operativo (TCP/IP). Isto expõe a comunicação a atrasos introduzidos pelo escalonamento de processos no CPU ou pausas do *garbage collector* do Python.
3. **Efeito N+1:** Caso os 30 pedidos remotos fossem feitos sequencialmente, o p95 total seria cumulativo: 30 × 4 ms = 120 ms. Se fossem executados em paralelo, o p95 da operação completa manter-se-ia muito próximo dos 4 ms originais, pois o tempo total seria ditado essencialmente pelo pedido mais lento do grupo.
4. **Refutação de falácias:** Os valores recolhidos refutam categoricamente a segunda falácia das redes distribuídas: "A latência é zero". Os números comprovam que, assim que abandonamos o acesso em memória (0.0001 ms) para aceder à rede, o tempo base dispara logo para >1 ms, aumentando massivamente à medida que introduzimos distância física.