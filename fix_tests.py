import re

with open('tracker/tests.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove Enterprise from imports
content = re.sub(r',\s*Enterprise', '', content)
content = re.sub(r'Enterprise,\s*', '', content)
content = re.sub(r'\bEnterprise\b', '', content)

# Remove MultiTenantDataIsolationTests entirely (everything until class RoleBasedPermissionTests)
content = re.sub(r'class MultiTenantDataIsolationTests\(TestCase\):.*?class RoleBasedPermissionTests', 'class RoleBasedPermissionTests', content, flags=re.DOTALL)

# Remove enterprise setup and kwargs
content = re.sub(r'self\.tenant = \.objects\.create\(name=" Enterprise A", subdomain="cysd-role"\)', '', content)
content = re.sub(r'self\.tenant\s*=\s*\.objects\.create\(.*?\)', '', content)
content = re.sub(r'enterprise=self\.tenant,?\s*', '', content)
content = re.sub(r',\s*enterprise=self\.tenant', '', content)

# Fix DevSwitchTests enterprise stuff
content = re.sub(r'self\.enterprise.*?=\s*\.objects\.get_or_create\(.*?defaults=\{.*?\}\s*\)', '', content, flags=re.DOTALL)
content = re.sub(r'self\.assertEqual\(employee\.enterprise, self\.enterprise\)', '', content)

# Remove HTTP_HOST kwargs
content = re.sub(r',\s*HTTP_HOST=[\'"][^\'"]+[\'"]', '', content)
content = re.sub(r'HTTP_HOST=[\'"][^\'"]+[\'"],\s*', '', content)

# Remove any stray empty setup
content = re.sub(r'# Get or create an \s*\n', '', content)

# Save
with open('tracker/tests.py', 'w', encoding='utf-8') as f:
    f.write(content)
