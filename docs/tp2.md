# Respostas à TP2 - Laboratório de SIVIT

## Exercício 2: Isolamento da Camada de Dados
1. **Tipo de Falha:** De acordo com a taxonomia estudada, trata-se de uma falha de *Crash* (falha por paragem) do lado da base de dados, pois o serviço foi interrompido abruptamente e deixou de responder aos pedidos do portal.
2. **Compreensão do Erro:** O erro apresentado não é compreensível para um utilizador final. Como a aplicação está em modo `DEBUG=True`, o Django devolve um *Stack Trace* detalhado com caminhos de ficheiros internos, o que num ambiente de produção representaria uma grave falha de segurança.
3. **Recuperação:** A recuperação foi imediata e autónoma. Assim que o contentor `sivitDB` foi reiniciado, a aplicação voltou a processar o login com sucesso no *refresh* seguinte, sem necessidade de reiniciar o portal.

## Exercício 3: Arquitetura de Produção
1. **Mapeamento de Camadas:** O Nginx atua como a camada de Apresentação (Web Server), o Gunicorn com o Django formam a camada de Aplicação, e o PostgreSQL representa a camada de Dados.
2. **Workers do Gunicorn:** O parâmetro `--workers 3` permite que o Gunicorn crie três processos distintos, possibilitando que o servidor processe até três pedidos HTTP em simultâneo.
3. **Ficheiros Estáticos:** O Nginx fica responsável por servir os ficheiros estáticos (CSS/JS) porque é altamente otimizado para ler ficheiros diretamente do disco, libertando o Gunicorn para processar apenas lógica Python.
4. **Timeout:** O `proxy_read_timeout 10s` garante que, se a camada de aplicação bloquear, o Nginx não fica à espera infinitamente e liberta a ligação ao fim de 10 segundos (devolvendo um erro 504 Gateway Timeout).

## Exercício 4: O Efeito N+1
| Abordagem | Nº de Queries | Tempo de Execução (ms) |
| :--- | :---: | :---: |
| Naive | 9 | [Inserir Tempo Ex: 36.25] |
| + select_related | [Inserir Valor] | [Inserir Tempo] |
| + prefetch_related | [Inserir Valor] | [Inserir Tempo] |
| + subquery for last reading | 2 | [Inserir Tempo Ex: 16.01] |