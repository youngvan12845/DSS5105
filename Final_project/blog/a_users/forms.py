from django.forms import ModelForm
from django import forms
from django.contrib.auth.models import User
from .models import Profile
from .models import EmailVerificationCode

class ProfileForm(ModelForm):
    class Meta:
        model = Profile
        fields = ['image', 'displayname', 'info']
        widgets = {
            'image': forms.FileInput(),
            'displayname': forms.TextInput(attrs={'placeholder': 'Add display name'}),
            'info': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add information'})
        }

class EmailForm(ModelForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['email']

class UsernameForm(ModelForm):
    class Meta:
        model = User
        fields = ['username']

# 新增密码重置相关表单
class PasswordResetEmailForm(forms.Form):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'placeholder': 'Enter your email address',
            'class': 'form-control'
        })
    )

class VerifyCodeForm(forms.Form):
    email = forms.EmailField(widget=forms.HiddenInput())
    verification_code = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter 6-digit verification code',
            'class': 'form-control',
            'pattern': '\\d{6}',
            'title': 'Enter a 6-digit verification code'
        })
    )

class ResetPasswordForm(forms.Form):
    new_password = forms.CharField(
        widget=forms.PasswordInput(),
        min_length=8,
        required=True
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(),
        required=True
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password:
            if new_password != confirm_password:
                raise forms.ValidationError("Passwords do not match")
        
        return cleaned_data
  
    
class LoginEmailVerificationForm(forms.Form):
    verification_code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Enter 6-digit verification code',
            'style': 'text-align: center; font-size: 20px; letter-spacing: 8px; font-weight: bold;',
            'autocomplete': 'off',
            'maxlength': '6'
        }),
        label='Verification code',
        help_text='Enter the 6-digit verification code sent to your email'
    )
    
    def __init__(self, user=None, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_verification_code(self):
        code = self.cleaned_data['verification_code']
        
        if not self.user:
            raise forms.ValidationError("User information missing")
        
        try:
            verification = EmailVerificationCode.objects.filter(
                user=self.user,
                code=code,
                used=False
            ).latest('created_at')
            
            if verification.is_expired():
                raise forms.ValidationError("Verification code has expired. Please request a new one")
                
        except EmailVerificationCode.DoesNotExist:
            raise forms.ValidationError("Invalid verification code")
        
        return code