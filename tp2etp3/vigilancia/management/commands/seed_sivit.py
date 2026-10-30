"""Povoamento com dados sintéticos.

Sem volume de dados, o exercício do N+1 não impressiona. Por omissão:
20 doentes, 20 internamentos ativos, 60 dispositivos, 50 000 leituras.

  python manage.py seed_sivit
  python manage.py seed_sivit --leituras 200000 --limpar
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from vigilancia.models import Admission, Device, Patient, Reading

TIPOS = ["ECG", "SpO2", "PANI", "TEMP"]
PARAMETROS = {"ECG": ("FC", "bpm", 60, 100), "SpO2": ("SPO2", "%", 92, 100),
              "PANI": ("PAS", "mmHg", 100, 140), "TEMP": ("TEMP", "C", 36.0, 37.5)}


class Command(BaseCommand):
    help = "Cria dados sintéticos do SIVIT. Nunca usar dados clínicos reais."

    def add_arguments(self, parser):
        parser.add_argument("--doentes", type=int, default=20)
        parser.add_argument("--dispositivos-por-internamento", type=int, default=3)
        parser.add_argument("--leituras", type=int, default=50_000)
        parser.add_argument("--limpar", action="store_true")

    def handle(self, *args, **o):
        if o["limpar"]:
            Reading.objects.all().delete()
            Device.objects.all().delete()
            Admission.objects.all().delete()
            Patient.objects.all().delete()

        agora = timezone.now()
        patients = [Patient(code=f"D{n:04d}", name=f"Doente Sintético {n:04d}",
                            date_of_birth="1960-01-01")
                    for n in range(1, o["doentes"] + 1)]
        Patient.objects.bulk_create(patients, ignore_conflicts=True)
        # using("default"): um comando de povoamento escreve na primária e tem
        # de reler da primária. Ler de uma réplica logo a seguir a escrever é
        # a violação de read-your-writes que TP7 estuda, e aqui daria
        # simplesmente uma lista vazia.
        patients = list(Patient.objects.using("default").all())

        # Repetível: só abre internamento a quem não tem um ativo. Sem isto,
        # correr o seed duas vezes duplica internamentos e dispositivos, e os
        # números das tabelas das aulas seguintes deixam de bater certo.
        already_admitted = set(Admission.objects.using("default")
                               .filter(discharged_at__isnull=True)
                               .values_list("patient_id", flat=True))
        admissions = [Admission(patient=p, ward=f"ENF{(i % 4) + 1}",
                                bed=f"C{i:02d}",
                                admitted_at=agora - timedelta(days=random.randint(1, 10)))
                      for i, p in enumerate(patients) if p.pk not in already_admitted]
        Admission.objects.bulk_create(admissions)
        admissions = list(Admission.objects.using("default")
                          .filter(discharged_at__isnull=True, patient__code__startswith="D"))

        # O número de série é derivado do CÓDIGO DO DOENTE e não da chave
        # primária do internamento: assim SN-0001-0 existe sempre, mesmo
        # depois de correr o seed várias vezes, e os exemplos das aulas
        # seguintes continuam a funcionar.
        devices = []
        for a in admissions:
            n = int(a.patient.code.lstrip("D"))
            for k in range(o["dispositivos_por_internamento"]):
                devices.append(Device(
                    serial_number=f"SN-{n:04d}-{k}", type=TIPOS[k % len(TIPOS)],
                    admission=a))
        Device.objects.bulk_create(devices, ignore_conflicts=True)
        devices = list(Device.objects.using("default").filter(serial_number__startswith="SN-"))

        per_device = max(1, o["leituras"] // len(devices))
        batch = []
        for d in devices:
            param, unit, lo, hi = PARAMETROS[d.type]
            base = agora - timedelta(seconds=per_device)
            for s in range(per_device):
                batch.append(Reading(device=d, instant=base + timedelta(seconds=s),
                                     parameter=param, value=round(random.uniform(lo, hi), 1),
                                     unit=unit))
                if len(batch) >= 5000:
                    Reading.objects.bulk_create(batch, ignore_conflicts=True)
                    batch = []
        if batch:
            Reading.objects.bulk_create(batch, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS(
            f"patients={Patient.objects.using('default').count()} "
            f"admissions={Admission.objects.using('default').count()} "
            f"devices={Device.objects.using('default').count()} "
            f"readings={Reading.objects.using('default').count()}"))
