from django.http import Http404
from .models import Enterprise

class TenantMiddleware:
    """
    Middleware that determines the current tenant (Enterprise) based on the request's subdomain.
    Attaches the enterprise to request.tenant.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get the hostname without port
        host = request.get_host().split(':')[0].lower()
        parts = host.split('.')
        
        # Determine subdomain:
        # e.g., 'cysd.localhost' -> parts = ['cysd', 'localhost']
        # e.g., 'cysd.myapp.com' -> parts = ['cysd', 'myapp', 'com']
        subdomain = None
        if len(parts) > 2:
            subdomain = parts[0]
        elif len(parts) == 2 and parts[1] == 'localhost':
            subdomain = parts[0]

        request.tenant = None

        # Exclude common non-tenant subdomains
        if subdomain and subdomain not in ('www', 'mail', 'api'):
            try:
                enterprise = Enterprise.objects.get(subdomain=subdomain)
                request.tenant = enterprise
            except Enterprise.DoesNotExist:
                raise Http404(f"No enterprise registered under subdomain '{subdomain}'.")
        
        # If accessing the app shell without a tenant (and not accessing global django admin or static files)
        # we can either default to a default tenant or require subdomain
        path = request.path
        is_exempt = (
            path.startswith('/admin/') or
            path.startswith('/static/') or
            path.startswith('/media/')
        )
        
        if not request.tenant and not is_exempt:
            raise Http404("No tenant workspace specified. Please access the application via your subdomain.")
        
        # Check tenant boundaries for authenticated users
        if request.user.is_authenticated and request.tenant:
            profile = getattr(request.user, 'employee_profile', None)
            if profile and profile.enterprise != request.tenant and not request.user.is_superuser:
                from django.contrib.auth import logout
                from django.contrib import messages
                from django.shortcuts import redirect
                logout(request)
                messages.error(request, f"You do not have permission to access the workspace for '{request.tenant.name}'.")
                return redirect('login')

        return self.get_response(request)
