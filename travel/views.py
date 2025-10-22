from django.shortcuts import render, get_object_or_404, redirect
from .models import ChatRoom
from django.contrib.auth.forms import UserCreationForm

# Create your views here.
def travel_list(request):
    print(f"request =======> {request.POST}")
    # request.POST.get('name')

    return render(request, "travel/travel_list.html")

def signup_view(request, room_name):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('travel:login')  # URL 네임 확인, travel.urls에서 login 이름 사용
    else:
        form = UserCreationForm()
    return render(request, 'chat/signup.html', {'form': form})

def chat_view(request, room_name):
    room = get_object_or_404(ChatRoom, room_name=room_name)
    return render(request, 'chat/match_chat.html', {
        'room_name': room.room_name
    })