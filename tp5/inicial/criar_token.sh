#!/usr/bin/env bash
# Cria (ou recupera) o utilizador de serviço `ingestao` no portal e imprime o
# seu token da API. A ingestão usa-o para chamar /api/v1/dispositivos/{serie}/,
# que desde TP3 exige autenticação: sem token, o portal responde 401 e todos
# os dispositivos parecem inválidos.
#
# Pressupõe rest_framework.authtoken em INSTALLED_APPS (TP3). Quem usou JWT em
# TP3 deve emitir o token da forma que lá implementou.
#
#   ./criar_token.sh     # imprime o token; colar o valor em PORTAL_TOKEN, no .env
set -euo pipefail
docker compose exec -T portal python manage.py shell -c "
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
u, _ = get_user_model().objects.get_or_create(username='ingestao')
print(Token.objects.get_or_create(user=u)[0].key)" | tr -d '\r'
