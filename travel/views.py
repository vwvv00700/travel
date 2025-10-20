from django.shortcuts import render

# Create your views here.
def travel_list(request):
    print(f"request =======> {request.POST}")
    # request.POST.get('name')

    return render(request, "travel/travel_list.html")