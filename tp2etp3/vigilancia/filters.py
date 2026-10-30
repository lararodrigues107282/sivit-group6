import django_filters

from .models import Admission, Device, Reading


class ReadingFilter(django_filters.FilterSet):
    device = django_filters.CharFilter(field_name="device__serial_number")
    desde = django_filters.IsoDateTimeFilter(field_name="instant", lookup_expr="gte")
    ate = django_filters.IsoDateTimeFilter(field_name="instant", lookup_expr="lte")

    class Meta:
        model = Reading
        fields = ["parameter"]


class DeviceFilter(django_filters.FilterSet):
    class Meta:
        model = Device
        fields = ["type", "admission", "serial_number"]


class AdmissionFilter(django_filters.FilterSet):
    class Meta:
        model = Admission
        fields = ["ward"]
