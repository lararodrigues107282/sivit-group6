#!/usr/bin/env bash
# Utilitários de inspeção do broker (material da TP5, adaptado aos nomes do guião).
#
#   ./tp5/inicial/ferramentas/fila.sh profundidade [fila]
#   ./tp5/inicial/ferramentas/fila.sh tabela
#   ./tp5/inicial/ferramentas/fila.sh purgar
set -euo pipefail
cd "$(dirname "$0")/../../.."          # raiz do repositório, onde está o .env

rabbit() { docker compose exec -T rabbitmq rabbitmqctl "$@" 2>/dev/null; }

case "${1:-tabela}" in
  profundidade)
    rabbit list_queues name messages --quiet --no-table-headers \
      | awk -v f="${2:-archive}" '$1==f {print $2}'
    ;;
  tabela)
    printf '%-22s %10s %10s %12s\n' FILA MENSAGENS PRONTAS CONSUMIDORES
    rabbit list_queues name messages messages_ready consumers --quiet --no-table-headers \
      | awk '{printf "%-22s %10s %10s %12s\n", $1, $2, $3, $4}'
    ;;
  purgar)
    for f in archive alarms display stats archive.dlq alarms.dlq display.dlq stats.dlq; do
      rabbit purge_queue "$f" >/dev/null 2>&1 || true
    done
    echo "filas purgadas"
    ;;
  *) echo "uso: $0 {profundidade [fila]|tabela|purgar}" >&2; exit 2 ;;
esac
