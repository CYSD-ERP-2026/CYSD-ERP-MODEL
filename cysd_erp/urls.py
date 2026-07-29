"""cysd_erp URL Configuration"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from tracker import views as tracker_views

schema_view = get_schema_view(
   openapi.Info(
      title="CYSD ERP API",
      default_version='v1',
      description="API endpoints for the CYSD Enterprise ERP system",
      contact=openapi.Contact(email="admin@cysd.org"),
   ),
   public=True,
   permission_classes=(permissions.IsAuthenticated,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', tracker_views.RateLimitedLoginView.as_view(), name='login'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('dashboard/', include('tracker.urls')),
    
    # API endpoints
    path('api/v1/', include('tracker.api.urls')),
    
    # API Documentation
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Admin site branding
admin.site.site_header = 'Enterprise ERP Administration'
admin.site.site_title = 'Enterprise ERP Admin'
admin.site.index_title = 'Dashboard'
admin.site.site_url = '/dashboard/'
