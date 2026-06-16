from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth import get_user_model
from django import forms
from django.utils.translation import gettext_lazy as _

User = get_user_model()

class UserCreationForm(forms.ModelForm):
    password_1 = forms.CharField(widget=forms.PasswordInput(
        attrs={'placeholder': 'Enter your password'}))
    password_2 = forms.CharField( widget=forms.PasswordInput(
        attrs={'placeholder': 'Comfirm your password' }))

    class Meta:
        model = User
        fields = ['email', 'first_name', 'phone_number']


    def clean_email(self):
        email = self.cleaned_data.get('email')
        qs = User.objects.filter(email=email)
        if qs.exists():
            raise forms.ValidationError(_('This email exist in database'))
        return email
    

    def clean(self):
        cleaned_data = super().clean()
        password_1 = self.cleaned_data.get('password_1')
        password_2 = self.cleaned_data.get('password_2')

        if password_1 and password_2 and password_1 != password_2:
            self.add_error(
                'password_2', 'les mot de passe doivent être pareil')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password_1'])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):

    password = ReadOnlyPasswordHashField(
        help_text="ça ne peut pas être modifié par l'administrateur")

    class Meta:
        model = User
        fields = ("email", 'password', 'first_name', 'last_name',
                  'phone_number')


    def clean_password(self):
        return self.initial['password']