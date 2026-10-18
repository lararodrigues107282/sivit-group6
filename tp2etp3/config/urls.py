from django.contrib import admin
from django.urls import path, include
from vigilancia.views import dashboard
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from vigilancia import views as api

router = DefaultRouter()
router.register("patients", api.PatientViewSet)
router.register("admissions", api.AdmissionViewSet)
router.register("devices", api.DeviceViewSet)
router.register("readings", api.ReadingViewSet, basename="reading")

urlpatterns = [
    path('admin/', admin.site.urls), 
    path("api/v1/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema")),
    path('', dashboard, name='dashboard'),
]