from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('consommation.api_urls')),  # API endpoints
    path('', include('consommation.urls')),  # Traditional views (for backward compatibility)
]