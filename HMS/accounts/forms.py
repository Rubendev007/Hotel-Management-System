from django.forms import ModelForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django import forms

from .models import *


# class CreateUserForm(UserCreationForm):
#     class Meta:
#         model = User
#         fields = ['username', 'email', 'password1', 'password1']

class CreateUserForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name',
                  'email', 'password1', 'password2']


class CreateEmployeeForm(ModelForm):
    class Meta:
        model = Employee
        fields = ["salary", "phoneNumber"]


class editEmployee(ModelForm):
    class Meta:
        model = Employee
        fields = ["salary"]


class editUser(ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]


class editGuest(ModelForm):
    class Meta:
        model = Guest
        fields = ["phoneNumber"]


class ROLES(forms.Form):
    ROLES_TYPES = [
        ('receptionist', 'receptionist'),
        ('staff', 'staff'),
        ('housekeeping', 'Housekeeping'),
    ]
    ROLES_TYPES = forms.CharField(
        widget=forms.RadioSelect(choices=ROLES_TYPES))
