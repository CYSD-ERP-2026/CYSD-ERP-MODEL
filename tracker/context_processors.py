def organization_context(request):
    """
    Context processor to inject static organization variables
    globally into templates.
    """
    return {
        'enterprise_name': 'CYSD ERP',
        'enterprise_logo': None,
    }
