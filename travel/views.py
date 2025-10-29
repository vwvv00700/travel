import json
import re
import time
import uuid
from itertools import groupby
from operator import attrgetter

from django.contrib.auth import logout, login, authenticate
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView

from .models import ChatRoom, Place, TravelPlan, UserProfile
from .services.LLM_analyzer import analyze_place_with_LLM
from .services.analysis_loader import create_or_update_analysis_from_json

# ================== 여행 관련 view 함수 ==================
def travel_list(request):
    return render(request, "travel/travel_list.html")


def _render_select_page(request):
    all_places = (
        Place.objects
        .filter(analyses__isnull=True)
        .order_by("category", "name")
        .distinct()
    )
    grouped_places = {cat: list(items) for cat, items in groupby(all_places, key=attrgetter("category"))}

    ctx = {
        "title": "장소 LLM 분석 도구",
        "grouped_places": grouped_places,
        "post_url": request.path,
        "save_url": request.path,
        "hidden_count": Place.objects.exclude(analyses__isnull=True).count(),
    }
    return render(request, "travel/select_and_analyze.html", ctx)


def analyze_selected_places_view(request):
    if request.method == "GET":
        return _render_select_page(request)

    action = request.POST.get("action", "analyze")

    if action == "analyze":
        selected_ids = request.POST.getlist("place_ids")
        if not selected_ids:
            messages.warning(request, "선택된 장소가 없어.")
            return redirect(request.path)

        sel_ids = {int(x) for x in selected_ids if str(x).isdigit()}
        available_qs = Place.objects.filter(id__in=sel_ids, analyses__isnull=True).distinct()

        kept_ids = set(available_qs.values_list("id", flat=True))
        skipped = sel_ids - kept_ids
        if skipped:
            messages.warning(request, f"이미 분석된 {len(skipped)}개 장소는 제외했어.")

        if not available_qs.exists():
            messages.warning(request, "분석할 수 있는 새로운 장소가 없어.")
            return redirect(request.path)

        results = []
        start_time = time.time()

        for place in available_qs:
            place_raw_data = f"장소 이름: {place.name}\n"
            result_dict = analyze_place_with_LLM(place_raw_data)
            pretty_json = json.dumps(result_dict, ensure_ascii=False, indent=2)
            compact_json = json.dumps(result_dict, ensure_ascii=False, separators=(",", ":"))
            results.append({
                "place_pk": place.pk,
                "place_id": getattr(place, "place_id", None),
                "place_name": place.name,
                "analysis_dict": result_dict,
                "analysis_json_pretty": pretty_json,
                "analysis_json_compact": compact_json,
            })

        end_time = time.time()
        print(f"LLM 분석 시간 총 : {len(available_qs)} 개 ============> {round(end_time - start_time, 2)}")

        ctx = {
            "title": "분석 결과",
            "analysis_results": results,
            "post_url": request.path,
            "save_url": request.path,
        }
        return render(request, "travel/select_and_analyze.html", ctx)

    elif action == "save":
        key_pat = re.compile(r"^payload_(\d+)$")
        saved = errors = 0

        for key, val in request.POST.items():
            m = key_pat.match(key)
            if not m:
                continue
            try:
                place_pk = int(m.group(1))
                data = json.loads(val)
                sea = data.get("seasonality_analysis") or []
                if not isinstance(sea, list):
                    data["seasonality_analysis"] = []
                place = Place.objects.get(pk=place_pk)
                obj, created = create_or_update_analysis_from_json(place, data)
                saved += 1
            except Exception as e:
                errors += 1
                messages.error(request, f"[{key}] 저장 실패: {e}")

        if saved:
            messages.success(request, f"DB 저장 완료: {saved}건")
        if errors:
            messages.error(request, f"저장 실패: {errors}건")
        return redirect(request.path)

    return redirect(request.path)


def travel_plan_list(request):
    plans = TravelPlan.objects.all().order_by('-created_at')
    return render(request, 'travel/plan_list.html', {'plans': plans})


def travel_plan_new(request):
    if request.method == 'POST':
        TravelPlan.objects.create(
            title=request.POST.get('title'),
            destination=request.POST.get('destination'),
            start_date=request.POST.get('start_date'),
            end_date=request.POST.get('end_date'),
            description=request.POST.get('description'),
        )
        return redirect('travel_plan_list')
    return render(request, 'travel/plan_new.html')


def travel_plan_edit(request, pk):
    plan = get_object_or_404(TravelPlan, pk=pk)
    if request.method == 'POST':
        plan.title = request.POST.get('title')
        plan.destination = request.POST.get('destination')
        plan.start_date = request.POST.get('start_date')
        plan.end_date = request.POST.get('end_date')
        plan.description = request.POST.get('description')
        plan.save()
        return redirect('travel_plan_list')
    return render(request, 'travel/plan_edit.html', {'plan': plan})


def chat_view(request, room_name):
    room, created = ChatRoom.objects.get_or_create(name=room_name)
    context = {'room': room}
    return render(request, 'travel/chat_room.html', context)


# ================== 회원가입 ==================
def signup_view(request):
    if request.method == 'POST':
        try:
            # 입력값 가져오기
            nickname = request.POST.get('nickname', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            password2 = request.POST.get('password2', '').strip()
            gender = request.POST.get('gender', '')
            age_range = request.POST.get('age_range', '')
            country = request.POST.get('country', '')
            language = request.POST.get('language', '')
            travel_style = request.POST.get('travel_style', '')
            budget = request.POST.get('budget', '')
            smoking_raw = request.POST.get('smoking', 'No')
            drinking_raw = request.POST.get('drinking', 'No')
            sns = request.POST.get('sns', '')
            bio = request.POST.get('bio', '')

            # 비밀번호 확인
            if password != password2:
                messages.error(request, "비밀번호가 일치하지 않습니다.")
                return redirect('travel:signup')

            # 이메일 중복 체크
            if User.objects.filter(username=email).exists():
                messages.error(request, "이미 존재하는 이메일입니다.")
                return redirect('travel:signup')

            # BooleanField 처리
            smoking = True if smoking_raw in ['예', '흡연', 'Yes'] else False
            drinking = True if drinking_raw in ['즐김', '가끔', 'Yes'] else False

            # User 생성
            user = User.objects.create_user(
                username=email,
                password=password,
                email=email,
                first_name=nickname or email
            )

            # UserProfile 생성
            UserProfile.objects.create(
                user=user,
                uuid=uuid.uuid4(),
                nickname=nickname or email,
                gender=gender,
                age_range=age_range,
                country=country,
                language=language,
                travel_style=travel_style,
                budget=budget,
                smoking=smoking,
                drinking=drinking,
                sns=sns,
                bio=bio
            )

            # 자동 로그인
            user = authenticate(username=email, password=password)
            if user:
                login(request, user)
                messages.success(request, f"{nickname or email}님 환영합니다!")
                return redirect('main')
            else:
                messages.error(request, "회원가입은 되었지만 자동 로그인에 실패했습니다.")
                return redirect('travel:login')

        except Exception as e:
            messages.error(request, f"회원가입 중 오류 발생: {e}")
            return redirect('travel:signup')

    return render(request, 'chat/signup.html')

# ================== 로그인 ==================
class CustomLoginView(LoginView):
    template_name = 'chat/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse('main')

    def form_valid(self, form):
        user = form.get_user()
        display_name = getattr(user.userprofile, 'nickname', user.username)
        messages.success(self.request, f"{display_name}님 환영합니다!")
        return super().form_valid(form)


# ================== 로그아웃 ==================
def logout_view(request):
    logout(request)
    return render(request, 'chat/logout.html')


# ================== 메인 ==================
def main(request):
    room, created = ChatRoom.objects.get_or_create(name='general')
    return render(request, 'travel/main.html', {'room_name': room.name})
