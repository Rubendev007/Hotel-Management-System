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


class SeasonForm(ModelForm):
    class Meta:
        model = Season
        fields = ["name", "start_date", "end_date", "markup_percentage", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "start_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "end_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "markup_percentage": forms.NumberInput(
                attrs={"min": "-100", "step": "0.01", "class": "form-control"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "Season name",
            "start_date": "Starts on",
            "end_date": "Ends on",
            "markup_percentage": "Markup (%)",
            "is_active": "Enable this season",
        }
        help_texts = {
            "markup_percentage": "Use a negative percentage for a discount, down to -100%.",
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        markup = cleaned_data.get("markup_percentage")

        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be on or after the start date.")
        if markup is not None and markup < -100:
            self.add_error("markup_percentage", "Markup cannot be lower than -100%.")
        return cleaned_data


class editDependees(ModelForm):
    class Meta:
        model = Dependees
        fields = ["booking", "name"]
