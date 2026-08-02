import re


def process_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    for pat, rep in replacements:
        content = re.sub(pat, rep, content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

views_replacements = [
    (r'enterprise=request\.tenant,\s*', ''),
    (r',\s*enterprise=request\.tenant', ''),
    (r'enterprise=request\.tenant', ''),
    (r'filter\(\s*,\s*', 'filter('),
    (r'get\(\s*,\s*', 'get('),
    (r',\s*\)', ')'),
    (r'request\.tenant\.subdomain', '"default"'),
    (r'request\.tenant', 'None')
]

process_file('tracker/views.py', views_replacements)

filters_replacements = [
    (r'enterprise=request\.tenant,\s*', ''),
    (r',\s*enterprise=request\.tenant', ''),
    (r'enterprise=request\.tenant', ''),
]
process_file('tracker/filters.py', filters_replacements)

api_views_replacements = [
    (r'if hasattr\(self\.request, \'tenant\'\) and self\.request\.tenant:', ''),
    (r'\s*return self\.queryset\.filter\(enterprise=self\.request\.tenant\)', '        return self.queryset')
]
process_file('tracker/api/views.py', api_views_replacements)

# Also fix templates base.html
base_replacements = [
    (r'\{% if not request\.tenant %\}', '{% if False %}'),
]
process_file('tracker/templates/base.html', base_replacements)
