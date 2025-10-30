from django import forms
from .models import DiaryEntry, Travel

class DiaryEntryForm(forms.ModelForm):
    class Meta:
        model = DiaryEntry
        fields = ['diary', 'photo', 'comment']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        travel_diary = kwargs.pop('travel_diary', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['diary'].queryset = Travel.objects.filter(author=user)
        if travel_diary:
            self.fields['diary'].initial = travel_diary
            self.fields['diary'].widget = forms.HiddenInput()

class TravelForm(forms.ModelForm):
    class Meta:
        model = Travel
        fields = ['name', 'description', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
