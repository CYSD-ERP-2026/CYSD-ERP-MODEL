
with open('tracker/tests.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Employee.objects.create( with create_test_employee(
content = content.replace('Employee.objects.create(', 'create_test_employee(')

helper = """
def create_test_employee(**kwargs):
    from tracker.models import Employee
    domain = kwargs.pop("domain", None)
    emp = Employee.objects.create(**kwargs)
    if domain:
        emp.domains.add(domain)
    return emp
"""

# add the helper right after imports
content = content.replace('from .models import Domain, Employee', 'from .models import Domain, Employee' + helper)

with open('tracker/tests.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Tests fixed!")
