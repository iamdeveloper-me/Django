from bootstrap_datepicker_plus import DatePickerInput, TimePickerInput, DateTimePickerInput, MonthPickerInput, YearPickerInput
from django import forms
from organizations.models import Client
import datetime

class DateMatchingForm(forms.Form):
    clients = forms.ModelChoiceField(queryset=Client.objects.all().order_by('uuid', 'name'))
    start_date = forms.DateField(widget=DatePickerInput(format='%Y-%m-%d'))
    start_time = forms.DateField(widget=TimePickerInput())
    end_date = forms.DateField(widget=DateTimePickerInput(format='%Y-%m-%d'))
    end_time = forms.DateField(widget=TimePickerInput())