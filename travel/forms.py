from django import forms
from .models import DiaryEntry, Travel

class DiaryEntryForm(forms.ModelForm):
    class Meta:
        model = DiaryEntry
        fields = ['travel', 'photo', 'comment']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        travel_diary = kwargs.pop('travel_diary', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['travel'].queryset = Travel.objects.filter(author=user)
        if travel_diary:
            self.fields['travel'].initial = travel_diary

class TravelForm(forms.ModelForm):
    class Meta:
        model = Travel
        fields = ['name', 'description', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
