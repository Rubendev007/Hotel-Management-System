from datetime import date

from django.forms import ModelForm
from django.contrib.auth.forms import UserCreationForm
from django import forms
from django.contrib.auth.models import User
from .models import *


class editRoom(ModelForm):
    class Meta:
        model = Room
        fields = ["capacity", "numberOfBeds", "roomType", "price"]


class editBooking(ModelForm):
    class Meta:
        model = Booking
        fields = ["startDate", "endDate"]

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("startDate")
        end_date = cleaned_data.get("endDate")
        if start_date and start_date < date.today():
            self.add_error("startDate", "Check-in date cannot be in the past.")
        if start_date and end_date and end_date <= start_date:
            self.add_error("endDate", "Check-out date must be after check-in date.")
        return cleaned_data


class editDependees(ModelForm):
    class Meta:
        model = Dependees
        fields = ["booking", "name"]
