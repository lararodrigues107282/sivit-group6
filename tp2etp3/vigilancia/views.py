from .filters import ReadingFilter, DeviceFilter, AdmissionFilter
from django.test.utils import CaptureQueriesContext
from .services import MODOS, linhas_painel
from django.shortcuts import render
from django.db import connection
from .models import Admission
from django.db.models import Subquery, OuterRef, Prefetch
from django.shortcuts import render
from django.db import connection
from .models import Admission
from django.db.models import Subquery, OuterRef, Prefetch
from .models import Reading, Device
import time
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from .models import Patient, Admission, Device, Reading
from .serializers import (
    PatientSerializer,
    AdmissionSerializer,
    DeviceSerializer,
    ReadingSerializer,
    )
from django.utils import timezone
from rest_framework.decorators import api_view
from .models import Admission, IdempotencyKey
from rest_framework.pagination import PageNumberPagination

def dashboard(request):
    modo = request.GET.get("modo", "subquery")
    if modo not in MODOS:
        modo = "subquery"
    with CaptureQueriesContext(connection) as ctx:
        inicio = time.perf_counter()
        rows = linhas_painel(modo)
        tempo_ms = (time.perf_counter() - inicio) * 1000
    context = {
        "rows": rows,
        "query_count": len(ctx.captured_queries),
        "total_time": round(tempo_ms, 2),
        "modo": modo,
        "modos": list(MODOS),
    }
    return render(request, "dashboard.html", context)

class ReadingPage(PageNumberPagination):
    page_size = 100

class ReadingCursor(CursorPagination):
    page_size = 100
    ordering = "-instant"

class PatientViewSet(viewsets.ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer


class AdmissionViewSet(viewsets.ModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = AdmissionSerializer
    filterset_class = AdmissionFilter


class DeviceViewSet(viewsets.ModelViewSet):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    filterset_class = DeviceFilter

    @action(detail=True, methods=["get"])
    def readings(self, request, pk=None):
        qs = Reading.objects.filter(device_id=pk)
        paginator = ReadingCursor()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            ReadingSerializer(page, many=True).data)

    @action(detail=True, methods=["get"], url_path="readings/latest")
    def latest(self, request, pk=None):
        l = Reading.objects.filter(device_id=pk).order_by("-instant").first()
        return Response(ReadingSerializer(l).data) if l else Response(status=404)

        # 1. SEM paginação
    @action(detail=True, methods=["get"], url_path="readings-all")
    def readings_all(self, request, pk=None):
        qs = Reading.objects.filter(device_id=pk).order_by("-instant")
        return Response(ReadingSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], url_path="readings-offset")
    def readings_offset(self, request, pk=None):
        qs = Reading.objects.filter(device_id=pk).order_by("-instant")
        paginator = ReadingPage()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            ReadingSerializer(page, many=True).data)

    @action(detail=True, methods=["get"], url_path="readings-keyset")
    def readings_keyset(self, request, pk=None):
        limit = min(int(request.query_params.get("limit", 100)), 1000)
        qs = Reading.objects.filter(device_id=pk).order_by("-instant")
        after = request.query_params.get("after")
        if after:
            qs = qs.filter(instant__lt=after)
        rows = list(qs[:limit])
        return Response({
            "results": ReadingSerializer(rows, many=True).data,
            "next_after": rows[-1].instant.isoformat() if len(rows) == limit else None,
        })
    
class ReadingViewSet(viewsets.ModelViewSet):
    queryset = Reading.objects.all()
    serializer_class = ReadingSerializer
    filterset_class = ReadingFilter

    def create(self, request):
        ser = self.get_serializer(data=request.data, many=True)
        ser.is_valid(raise_exception=True)
        objs = [Reading(**d) for d in ser.validated_data]
        with transaction.atomic():
            antes = Reading.objects.count()
            Reading.objects.bulk_create(objs, ignore_conflicts=True)
            inseridas = Reading.objects.count() - antes
        return Response({"recebidas": len(objs), "inseridas": inseridas},
                        status=status.HTTP_201_CREATED)
