from django.test import TestCase


## Teste do envio de respostas iguais para a base de dados - verificar UniqueConstraint.

import random

class DropResponseMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        if random.random() < 0.3:
            raise ConnectionAbortedError("reply lost")
        return response


#Função teste a correr na powershell

"""
send() {
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if resp=$(curl -sf -X POST localhost/api/v1/readings/ \
         -H 'Content-Type: application/json' \
         -H "Authorization: Token $TOKEN" \
         -d @data.json); then
      echo "tentativa $attempt: $resp"
      return
    fi
    echo "tentativa $attempt: falhou, a repetir..."
  done
}
"""
