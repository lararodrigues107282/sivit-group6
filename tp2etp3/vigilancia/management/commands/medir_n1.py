import statistics
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from vigilancia.models import Admission, Device, Patient, Reading
from vigilancia.services import MODOS

TIPOS = ["ECG", "SpO2", "TEMP"]


class Command(BaseCommand):
    help = "Mede queries e tempo do painel em cada variante (exercício 4 do TP2)."

    def add_arguments(self, parser):
        parser.add_argument("--admissoes", type=int, default=20)
        parser.add_argument("--dispositivos", type=int, default=3)
        parser.add_argument("--repeticoes", type=int, default=5)

    def preparar(self, n_admissoes, n_dispositivos):
        """Cria dados sintéticos (códigos N1-...). Não toca nos restantes."""
        agora = timezone.now()
        for i in range(n_admissoes):
            paciente, _ = Patient.objects.get_or_create(
                code=f"N1-{i:04d}",
                defaults={"name": f"Doente N1 {i:04d}", "date_of_birth": "1960-01-01"},
            )
            admissao = Admission.objects.filter(patient=paciente, discharged_at__isnull=True).first()
            if admissao is None:
                admissao = Admission.objects.create(
                    patient=paciente, ward="Medicina 2", bed=str(i),
                    admitted_at=agora - timedelta(days=1),
                )
            for j in range(n_dispositivos):
                dispositivo, criado = Device.objects.get_or_create(
                    serial_number=f"N1-{i:04d}-{j}",
                    defaults={"type": TIPOS[j % len(TIPOS)], "admission": admissao},
                )
                if criado:
                    Reading.objects.bulk_create([
                        Reading(device=dispositivo, instant=agora - timedelta(seconds=k),
                                parameter="HR", value=80 + k % 5, unit="bpm")
                        for k in range(20)
                    ])

    def handle(self, *args, **opts):
        self.preparar(opts["admissoes"], opts["dispositivos"])
        self.stdout.write(
            f"Dados: {opts['admissoes']} admissões x {opts['dispositivos']} dispositivos "
            f"(mediana de {opts['repeticoes']} execuções)"
        )
        self.stdout.write("| Variante | Nº de queries | Tempo (ms) |")
        self.stdout.write("|---|---:|---:|")
        for nome, funcao in MODOS.items():
            funcao()  # aquecimento
            tempos, queries = [], []
            for _ in range(opts["repeticoes"]):
                with CaptureQueriesContext(connection) as ctx:
                    inicio = time.perf_counter()
                    funcao()
                    tempos.append((time.perf_counter() - inicio) * 1000)
                queries.append(len(ctx.captured_queries))
            self.stdout.write(
                f"| {nome} | {statistics.median(queries):.0f} | {statistics.median(tempos):.2f} |"
            )
