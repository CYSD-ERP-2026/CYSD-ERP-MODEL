def organization_context(request):
    """
    Context processor to inject dynamic tenant (Enterprise) variables
    globally into templates.
    """
    tenant = getattr(request, 'tenant', None)

    logo_url = None
    if tenant and tenant.logo:
        try:
            logo_url = tenant.logo.url
        except ValueError:
            pass

    return {
        'enterprise_name': tenant.name if tenant else 'Enterprise ERP',
        'enterprise_logo': logo_url,
    }
