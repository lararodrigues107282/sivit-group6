"""Regras de domínio do painel de admissões.

Sem HTTP: a view só orquestra. A API (TP3) e o consumidor de filas (TP5)
vão reutilizar estas funções.

Cada variante faz o mesmo trabalho, com um número diferente de queries:
  ingenuo          -> N+1 em todo o lado
  select_related   -> o doente vem num JOIN
  prefetch         -> os dispositivos vêm numa query extra
  subquery         -> a última leitura vem numa subquery (versão final)
"""
from django.db.models import OuterRef, Prefetch, Subquery

from .models import Admission, Device, Reading


def _admissoes_ativas():
    return Admission.objects.filter(discharged_at__isnull=True)


def _ultima_leitura(dispositivo):
    leitura = dispositivo.readings.order_by("-instant").first()
    return leitura.value if leitura else None


def linhas_ingenuo():
    linhas = []
    for admissao in _admissoes_ativas():
        for dispositivo in admissao.devices.all():
            linhas.append((admissao.patient.name, dispositivo.type, _ultima_leitura(dispositivo)))
    return linhas


def linhas_select_related():
    linhas = []
    for admissao in _admissoes_ativas().select_related("patient"):
        for dispositivo in admissao.devices.all():
            linhas.append((admissao.patient.name, dispositivo.type, _ultima_leitura(dispositivo)))
    return linhas


def linhas_prefetch():
    admissoes = _admissoes_ativas().select_related("patient").prefetch_related("devices")
    linhas = []
    for admissao in admissoes:
        for dispositivo in admissao.devices.all():
            linhas.append((admissao.patient.name, dispositivo.type, _ultima_leitura(dispositivo)))
    return linhas


def linhas_subquery():
    ultima = Reading.objects.filter(device=OuterRef("pk")).order_by("-instant").values("value")[:1]
    dispositivos = Device.objects.annotate(ultimo_valor=Subquery(ultima))
    admissoes = _admissoes_ativas().select_related("patient").prefetch_related(
        Prefetch("devices", queryset=dispositivos)
    )
    return [
        (admissao.patient.name, dispositivo.type, dispositivo.ultimo_valor)
        for admissao in admissoes
        for dispositivo in admissao.devices.all()
    ]


MODOS = {
    "ingenuo": linhas_ingenuo,
    "select_related": linhas_select_related,
    "prefetch": linhas_prefetch,
    "subquery": linhas_subquery,
}


def linhas_painel(modo="subquery"):
    return MODOS.get(modo, linhas_subquery)()
