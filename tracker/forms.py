from django import forms

from .models import Enterprise


class EnterpriseForm(forms.ModelForm):
    class Meta:
        model = Enterprise
        fields = ['name', 'subdomain', 'logo']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Enter enterprise name (e.g., Acme Corp)',
            }),
            'subdomain': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'subdomain (e.g., acme)',
            }),
            'logo': forms.ClearableFileInput(attrs={
                'class': 'form-control',
            }),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name or name.strip() == '':
            raise forms.ValidationError("Enterprise name cannot be empty.")
        return name.strip()

    def clean_subdomain(self):
        subdomain = self.cleaned_data.get('subdomain')
        if not subdomain or subdomain.strip() == '':
            raise forms.ValidationError("Subdomain cannot be empty.")
        subdomain = subdomain.strip().lower()
        if not subdomain.isalnum():
            raise forms.ValidationError("Subdomain must be alphanumeric only (letters and numbers).")
        if Enterprise.objects.filter(subdomain=subdomain).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This subdomain is already taken.")
        return subdomain
