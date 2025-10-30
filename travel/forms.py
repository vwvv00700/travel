from django import forms
from .models import DiaryEntry, Travel, Tag

class DiaryEntryForm(forms.ModelForm):
    tag_string = forms.CharField(
        label="태그",
        required=False,
        help_text="쉼표(,)로 태그를 구분하여 입력하세요. (예: #서울, #맛집, #야경)"
    )

    class Meta:
        model = DiaryEntry
        fields = ['diary', 'media_file', 'comment', 'tag_string']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        travel_diary = kwargs.pop('travel_diary', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['diary'].queryset = Travel.objects.filter(author_id=user.id)
        if travel_diary:
            self.fields['diary'].initial = travel_diary
            self.fields['diary'].widget = forms.HiddenInput()
        
        if self.instance and self.instance.pk:
            self.fields['tag_string'].initial = ', '.join(tag.name for tag in self.instance.tags.all())

    def save(self, commit=True):
        print("DEBUG: DiaryEntryForm.save called.")
        instance = super().save(commit=False)
        
        def save_tags():
            print("DEBUG: DiaryEntryForm.save_tags called.")
            instance.tags.clear()
            tag_string = self.cleaned_data.get('tag_string', '')
            print(f"DEBUG: tag_string from form: '{tag_string}'")
            if tag_string:
                tag_names = [name.strip() for name in tag_string.split(',') if name.strip()]
                print(f"DEBUG: Processed tag_names: {tag_names}")
                for tag_name in tag_names:
                    if tag_name.startswith('#'):
                        tag_name = tag_name[1:]
                    if tag_name: # Ensure not empty after stripping
                        tag, _created = Tag.objects.get_or_create(name=tag_name)
                        instance.tags.add(tag)
                        print(f"DEBUG: Added tag: {tag.name}")

        if commit:
            instance.save()
            save_tags()
        else:
            # If commit is false, the view MUST call form.save_tags() after saving the instance.
            self.save_tags = save_tags
            
        return instance

class TravelForm(forms.ModelForm):
    class Meta:
        model = Travel
        fields = ['name', 'description', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
