import random
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from .models import Patient, Admission, Device, Reading


class DropResponseMiddleware:
    """Simula a perda da resposta depois de o servidor processar o pedido.
    Ativar em settings.MIDDLEWARE só para a demonstração (exercício 2, passo 2)."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if random.random() < 0.3:
            raise ConnectionAbortedError("reply lost")
        return response


class IdempotenciaIngestaoTests(TestCase):
    """Reenviar o mesmo lote não pode duplicar leituras (UniqueConstraint)."""

    def setUp(self):
        user = User.objects.create_user(username="gateway-1", password="x")
        token = Token.objects.create(user=user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        patient = Patient.objects.create(
            code="D0001", name="Doente Pseudonimizado", date_of_birth="1960-01-01")
        admission = Admission.objects.create(
            patient=patient, ward="Medicina 2", bed="4",
            admitted_at=timezone.now() - timedelta(days=1))
        self.device = Device.objects.create(
            serial_number="SN-0001-0", type="SpO2", admission=admission)

        self.inicio = timezone.now().replace(microsecond=0)

    def lote(self, n):
        """Gera n leituras (SpO2), todas com instantes distintos."""
        return [
            {
                "device": self.device.serial_number,
                "instant": (self.inicio + timedelta(seconds=i)).isoformat(),
                "parameter": "SPO2",
                "value": 95.0,
                "unit": "%",
            }
            for i in range(n)
        ]

    def test_reenviar_o_mesmo_lote_nao_duplica(self):
        lote = self.lote(10)

        for _ in range(3):  # simula três tentativas do gateway
            resp = self.client.post("/api/v1/readings/", lote, format="json")
            self.assertEqual(resp.status_code, 201)

        self.assertEqual(Reading.objects.count(), 10)

    def test_lote_parcialmente_repetido_insere_so_as_novas(self):
        self.client.post("/api/v1/readings/", self.lote(10), format="json")

        lote_maior = self.lote(15)  # as 10 primeiras repetem-se, mais 5 novas
        resp = self.client.post("/api/v1/readings/", lote_maior, format="json")

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["recebidas"], 15)
        self.assertEqual(resp.json()["inseridas"], 5)  # só as 5 novas
        self.assertEqual(Reading.objects.count(), 15)

    def test_resposta_perdida_seguida_de_retry_e_correta(self):
        """Caso do enunciado: o servidor grava, a resposta perde-se, o cliente repete."""
        lote = self.lote(10)
        # primeira tentativa: o servidor processa, mas o cliente não recebe resposta
        self.client.post("/api/v1/readings/", lote, format="json")
        # retry do cliente
        self.client.post("/api/v1/readings/", lote, format="json")

        self.assertEqual(Reading.objects.count(), 10)
