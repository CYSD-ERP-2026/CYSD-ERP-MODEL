import re

with open('tracker/tests.py', 'r', encoding='utf-8') as f:
    content = f.read()

helper = """

def create_test_employee(**kwargs):
    from tracker.models import Employee
    domain = kwargs.pop("domain", None)
    emp = Employee.objects.create(**kwargs)
    if domain:
        emp.domains.add(domain)
    return emp

"""

if "def create_test_employee" not in content:
    content = content.replace("import json", "import json" + helper)

with open('tracker/tests.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Helper added!")
