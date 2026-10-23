import statistics
import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from vigilancia.models import Device, Reading

N = 50_000
TAMANHO_PAGINA = 100
PAGINA_ALVO = 500
LOTE = 5000


class Command(BaseCommand):
    help = "Mede a paginação com 50 000 leituras (TP3, exercício 3)."

    def add_arguments(self, parser):
        parser.add_argument("--repeticoes", type=int, default=3)

    def preparar(self):
        """Cria (uma vez) 50 000 leituras num dispositivo dedicado, P-50K-0."""
        dispositivo, _ = Device.objects.get_or_create(serial_number="P-50K-0", defaults={"type": "ECG"})
        if dispositivo.readings.count() == N:
            return dispositivo
        dispositivo.readings.all().delete()
        base = timezone.now().replace(microsecond=0)
        lote = []
        for k in range(N):
            lote.append(Reading(device=dispositivo, instant=base - timedelta(seconds=k),
                                parameter="HR", value=60 + k % 40, unit="bpm"))
            if len(lote) == LOTE:
                Reading.objects.bulk_create(lote)
                lote = []
        if lote:
            Reading.objects.bulk_create(lote)
        return dispositivo

    def medir(self, cliente, url, params, repeticoes):
        tempos = []
        for _ in range(repeticoes):
            inicio = time.perf_counter()
            resposta = cliente.get(url, params)
            tempos.append((time.perf_counter() - inicio) * 1000)
        assert resposta.status_code == 200, (url, resposta.status_code)
        return statistics.median(tempos), len(resposta.content)

    def handle(self, *args, **opts):
        dispositivo = self.preparar()
        utilizador, _ = User.objects.get_or_create(username="bench")
        cliente = APIClient()
        cliente.force_authenticate(user=utilizador)

        # Cursor da página 500 = instante da última leitura da página 499
        posicao = (PAGINA_ALVO - 1) * TAMANHO_PAGINA - 1
        instante_cursor = (Reading.objects.filter(device=dispositivo)
                           .order_by("-instant").values_list("instant", flat=True)[posicao])

        base = f"/api/v1/devices/{dispositivo.id}"
        r = opts["repeticoes"]

        definicoes = {
            "REST_FRAMEWORK": {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []},
            "ALLOWED_HOSTS": list(settings.ALLOWED_HOSTS) + ["testserver"],
        }
        with override_settings(**definicoes):
            t1, s1 = self.medir(cliente, f"{base}/readings-all/", {}, r)
            t_offset1, s_offset1 = self.medir(cliente, f"{base}/readings-offset/", {"page": 1}, r)
            t_offset500, s_offset500 = self.medir(cliente, f"{base}/readings-offset/",
                                                  {"page": PAGINA_ALVO}, r)
            t_key1, s_key1 = self.medir(cliente, f"{base}/readings-keyset/",
                                        {"limit": TAMANHO_PAGINA}, r)
            t_key500, s_key500 = self.medir(cliente, f"{base}/readings-keyset/",
                                            {"limit": TAMANHO_PAGINA, "after": instante_cursor.isoformat()}, r)

        self.stdout.write(f"Leituras no dispositivo: {N}; página = {TAMANHO_PAGINA}; mediana de {r} execuções")
        self.stdout.write("| Estratégia | 1.ª página (ms) | Página 500 (ms) | Tamanho 1.ª página (bytes) |")
        self.stdout.write("|---|---:|---:|---:|")
        self.stdout.write(f"| Sem paginação | {t1:.1f} | n/a (devolve tudo) | {s1} |")
        self.stdout.write(f"| Offset (?page=) | {t_offset1:.1f} | {t_offset500:.1f} | {s_offset1} |")
        self.stdout.write(f"| Cursor (?after=&limit=) | {t_key1:.1f} | {t_key500:.1f} | {s_key1} |")
