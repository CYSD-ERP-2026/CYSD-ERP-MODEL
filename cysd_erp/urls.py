"""cysd_erp URL Configuration"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from tracker import views as tracker_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', tracker_views.RateLimitedLoginView.as_view(), name='login'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('dashboard/', include('tracker.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Admin site branding
admin.site.site_header = 'Enterprise ERP Administration'
admin.site.site_title = 'Enterprise ERP Admin'
admin.site.index_title = 'Dashboard'
admin.site.site_url = '/dashboard/'
