from rest_framework import serializers
from .models import Patient, Admission, Device, Reading

LIMITS = {"HR": (20, 250), "SPO2": (50, 100), "TEMP": (30, 45)}

class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ["id", "code", "name", "date_of_birth"]
        read_only_fields = ["id"]

class AdmissionSerializer(serializers.ModelSerializer):
    patient = serializers.SlugRelatedField(
        slug_field="code", queryset=Patient.objects.all()
    )

    class Meta:
        model = Admission
        fields = ["id", "patient", "ward", "bed", "admitted_at", "discharged_at"]
        read_only_fields = ["id"]

    def validate(self, data):
            admission = data.get("admitted_at", getattr(self.instance, "admitted_at", None))
            dismission = data.get("discharged_at", getattr(self.instance, "discharged_at", None))
            if admission and dismission and dismission < admission:
                raise serializers.ValidationError("discharge before admission")
            return data

class DeviceSerializer(serializers.ModelSerializer):
    admission = serializers.PrimaryKeyRelatedField(
        queryset=Admission.objects.all(), allow_null=True, required=False)
    
    class Meta:
        model = Device
        fields = ["id", "serial_number", "type", "admission"]
        read_only_fields = ["id"]



class ReadingSerializer(serializers.ModelSerializer):
    device = serializers.SlugRelatedField(
        slug_field="serial_number", queryset=Device.objects.all()
    )

    class Meta:
        model = Reading
        fields = ["device", "instant", "parameter", "value", "unit"]
        validators = []

    def validate(self, data):
        lo, hi = LIMITS.get(data["parameter"], (float("-inf"), float("inf")))
        if not lo <= data["value"] <= hi:
            raise serializers.ValidationError("value outside plausible range")
        return data