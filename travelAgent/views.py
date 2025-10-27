from django.shortcuts import render

def main(request):
    return render(request, "index.html")

def select(request):
    return render(request, "select.html")

