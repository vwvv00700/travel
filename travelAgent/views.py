from django.shortcuts import render

def main(request):
    return render(request, "main.html")

def select(request):
    return render(request, "select.html")

