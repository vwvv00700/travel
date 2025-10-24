# travel/admin.py
import json
import string
import secrets
from typing import Any, Dict, List, Tuple

from itertools import groupby
from operator import attrgetter

from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse, path
from django.shortcuts import redirect, render
from .models import Place, Review, UploadEntry, AnalysisTool, PlaceAnalysis

from .services.LLM_analyzer import analyze_place_with_LLM
from .services.analysis_loader import create_or_update_analysis_from_json


# ── 주소 파서(대한민국 간단 규칙) ─────────────────────────────────────────────
CITY_SUFFIXES = ("특별시", "광역시", "자치시", "특별자치시", "도", "특별자치도")
GU_SUFFIXES = ("구", "군", "시")

def split_kr_address(addr: str) -> tuple[str | None, str | None, str | None]:
    if not addr:
        return (None, None, None)
    toks = addr.strip().split()
    country = toks[0] if toks else None
    city = None
    city_gu = None
    for i, t in enumerate(toks[1:], start=1):
        if any(t.endswith(suf) for suf in CITY_SUFFIXES):
            city = t
            if i + 1 < len(toks):
                t2 = toks[i + 1]
                if any(t2.endswith(suf) for suf in GU_SUFFIXES):
                    city_gu = t2
            break
    if not city and len(toks) >= 2:
        city = toks[1]
        if len(toks) >= 3:
            city_gu = toks[2]
    return (country, city, city_gu)


# ── place_id 27자리 난수 ────────────────────────────────────────────────────
_ALPHABET = string.ascii_letters + string.digits
def gen_unique_place_id(length: int = 27) -> str:
    while True:
        pid = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if not Place.objects.filter(place_id=pid).exists():
            return pid


# ── 업로드 폼 ────────────────────────────────────────────────────────────────
class UploadJSONForm(forms.Form):
    file = forms.FileField(help_text="루트에 구(key) → attractions/restaurants/accommodations 리스트가 있는 JSON")
    mode = forms.ChoiceField(
        choices=[("create", "신규만 생성"), ("upsert", "업서트(있으면 업데이트)")],
        initial="upsert",
    )


# ── 일반 Place 어드민 ────────────────────────────────────────────────
@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "place_id", "category", "rating", "reviewCnt", "lat", "lon",
        "city", "city_gu", "phone", "image_urls", "opening_hours", "regdate", "chgdate",
    )
    search_fields = ("name", "place_id", "address", "city", "city_gu")
    list_filter = ("category", "city", "city_gu")

# ── 일반 Review 어드민 ────────────────────────────────────────────────
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("name", "author", "place_id", "rating", "like", "short_content")
    search_fields = ("name", "author", "place_id", "content")
    list_filter = ("rating",)

    def short_content(self, obj):
        return (obj.content or "")[:60]
    short_content.short_description = "content"

# ── 장소 성격 어드민 ────────────────────────────────────────────────
@admin.register(PlaceAnalysis)
class PlaceAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "id", 
        "place_title", 
        "place_code", 
        "created_at", 
        "keywords_csv",
        "themes_csv",
        "season_spring", "season_summer", "season_autumn", "season_winter",
        "mbti_E", "mbti_I", "mbti_S", "mbti_N", "mbti_T", "mbti_F", "mbti_J", "mbti_P",
        "group_couple", "group_friends", "group_family", "group_solo",
        "age_20s", "age_30s", "age_40s", "age_50plus",
        "gender_female", "gender_male",
    )
    search_fields = ("place_code", "place_title")
    list_filter = ("created_at",)

# ── 장소 성격 LLM 어드민 ────────────────────────────────────────────────
@admin.register(AnalysisTool)
class AnalysisToolAdmin(admin.ModelAdmin):
    # "+ Add" 없애기
    def has_add_permission(self, request):
        return False

    # 인덱스에 노출은 하되 Add는 감춤
    def get_model_perms(self, request):
        return {"change": True}

    # 리스트(모델 클릭/Change) → run 뷰로 리다이렉트
    def changelist_view(self, request, extra_context=None):
        return redirect("travel:llm_analysis")

    # 커스텀 URL 등록
    def get_urls(self):
        urls = super().get_urls()
        my = [
            path(
                "run/",
                self.admin_site.admin_view(self.run_view),  # 권한/CSRF 자동
                name="travel_analysis_tool_run",
            ),
        ]
        return my + urls

    # === 여기 안에 네 analyze_selected_places_view 로직 이식 ===
    def run_view(self, request):
        """
        GET: 카테고리별 장소 선택 화면
        POST: 선택한 장소들 분석 실행 후 결과 렌더
        템플릿: admin/travel/select_and_analyze.html
        """
        # admin 공통 컨텍스트
        base_ctx = self.admin_site.each_context(request)

        # GET — 장소 그룹핑 화면
        if request.method == "GET":
            all_places = Place.objects.all().order_by("category", "name")
            grouped_places = {}
            for category, places_in_category in groupby(all_places, key=attrgetter("category")):
                grouped_places[category] = list(places_in_category)

            ctx = {
                **base_ctx,
                "title": "장소 성격 LLM",
                "grouped_places": grouped_places,
                "post_url": reverse("travel:llm_analysis"),
            }
            return render(request, "travel/select_and_analyze.html", ctx)

        # POST — 분석 실행
        if request.method == "POST":
            results = []
            selected_ids = request.POST.getlist("place_ids")

            if not selected_ids:
                messages.warning(request, "선택된 장소가 없습니다.")
                return redirect(reverse("travel:llm_analysis"))

            selected_places = Place.objects.filter(id__in=selected_ids)

            for place in selected_places:
                place_raw_data = f"장소 이름: {place.name}\n"
                analysis_result_dict = analyze_place_with_LLM(place_raw_data)

                try:
                    analysis_result_json = json.dumps(analysis_result_dict, ensure_ascii=False, indent=2)
                except Exception:
                    analysis_result_json = str(analysis_result_dict)

                results.append({
                    "place_name": place.name,
                    "raw_data": place_raw_data,
                    "analysis_data": analysis_result_dict,  # 요약용 dict
                    "analysis_json": analysis_result_json,  # 디버그용 JSON 문자열
                })

            ctx = {
                **base_ctx,
                "title": "분석 결과",
                "analysis_results": results,
                "post_url": reverse("travel:llm_analysis"),
            }
            return render(request, "travel/select_and_analyze.html", ctx)
        
# ── 업로드 전용 어드민 ────────────────────────────────────────────────
@admin.register(UploadEntry)
class UploadEntryAdmin(admin.ModelAdmin):
    """
    사이드바에 '데이터 업로드' 메뉴로 표시됨.
    목록 대신 업로드 폼 화면을 렌더링하고, POST 시 업로드 처리.
    """
    change_list_template = "admin/travel/dataimport/upload.html"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return True
    def has_delete_permission(self, request, obj=None): return False

    def changelist_view(self, request: HttpRequest, extra_context=None):
        form = UploadJSONForm(request.POST or None, request.FILES or None)

        # GET: 업로드 폼
        if request.method != "POST" or not form.is_valid():
            ctx = dict(
                self.admin_site.each_context(request),
                title="데이터 업로드",
                form=form,
                opts=UploadEntry._meta,
            )
            return TemplateResponse(request, self.change_list_template, ctx)

        # POST: 업로드 처리
        raw = form.cleaned_data["file"].read()
        text = raw.decode("utf-8-sig", errors="ignore")

        # 1) JSON 파싱
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            messages.error(request, f"JSON 파싱 실패: {e}")
            ctx = dict(self.admin_site.each_context(request), title="데이터 업로드", form=form, opts=UploadEntry._meta)
            return TemplateResponse(request, self.change_list_template, ctx)

        buckets: List[tuple[str, List[Dict[str, Any]]]] = []  # (category, items)

        def add_bucket(cat: str, items: Any):
            if isinstance(items, list):
                buckets.append((cat, items))

        # 최상단 키(구/군 등) 아래에 리스트가 있는 형태와 루트에 바로 리스트가 있는 형태 모두 지원
        if isinstance(data, dict):
            def extract(d: Dict[str, Any]):
                add_bucket("attractions", d.get("tourist_attractions"))
                add_bucket("restaurants", d.get("restaurants"))
                add_bucket("accommodations", d.get("accommodations"))
            found = False
            for v in data.values():
                if isinstance(v, dict) and any(isinstance(v.get(k), list) for k in ("tourist_attractions","restaurants","accommodations")):
                    extract(v); found = True
            if not found:
                extract(data)
        elif isinstance(data, list):
            buckets.append(("attractions", data))

        if not buckets:
            messages.error(request, "attractions / restaurants / accommodations 리스트를 찾지 못했어.")
            ctx = dict(self.admin_site.each_context(request), title="데이터 업로드", form=form, opts=UploadEntry._meta)
            return TemplateResponse(request, self.change_list_template, ctx)

        # 2) 저장
        mode = form.cleaned_data["mode"]
        p_created = p_updated = 0
        r_created = r_skipped = 0

        with transaction.atomic():
            for cat, items in buckets:
                for it in items:
                    place_name = (it.get("name") or it.get("title") or "").strip()
                    if not place_name:
                        continue

                    # place_id 확정(없으면 27자리 생성)
                    pid = (it.get("place_id") or "").strip() or gen_unique_place_id()

                    addr = it.get("address") or ""
                    country, city, city_gu = split_kr_address(addr)
                    review_total = it.get("reviews_total")
                    if review_total is None and isinstance(it.get("reviews"), list):
                        review_total = len(it["reviews"])

                    lat = it.get("latitude") or ""
                    lon = it.get("longitude") or ""

                    image_urls_str = ", ".join(it.get("image_urls"))
                    opening_hours_str = ", ".join(it.get("opening_hours"))
                    
                    place_row = {
                        "name": place_name,
                        "place_id": pid,
                        "category": cat,
                        "rating": it.get("rating"),
                        "reviewCnt": review_total,
                        "address": addr,
                        "country": country,
                        "city": city,
                        "city_gu": city_gu,
                        "lat": lat,
                        "lon": lon,
                        "image_urls": image_urls_str,
                        "opening_hours": opening_hours_str,
                        "phone": it.get("phone"),
                        "website": it.get("website"),
                    }

                    # place 저장 (place_id 기준)
                    if mode == "create":
                        if not Place.objects.filter(place_id=pid).exists():
                            Place.objects.create(**place_row); p_created += 1
                    else:
                        _, created = Place.objects.update_or_create(place_id=pid, defaults=place_row)
                        p_created += int(created); p_updated += int(not created)

                    # 리뷰 저장 (author 분리)
                    reviews = it.get("reviews")
                    if isinstance(reviews, list):
                        for rv in reviews:
                            author = (rv.get("author_name") or "").strip()
                            content = (rv.get("text") or rv.get("test") or "").strip()
                            like = rv.get("like") or 0
                            try:
                                Review.objects.get_or_create(
                                    name=place_name,
                                    place_id=pid,
                                    author=author,
                                    content=content,
                                    defaults={"rating": rv.get("rating"), "like": like},
                                )
                                r_created += 1
                            except Exception:
                                r_skipped += 1

        messages.success(
            request,
            f"Place 생성 {p_created} / 업데이트 {p_updated} | Review 생성 {r_created} / 스킵 {r_skipped}",
        )

        # 완료 후 리뷰 목록으로 리다이렉트(커스텀 AdminSite 네임스페이스 대응)
        site_ns = self.admin_site.name
        app, model = Review._meta.app_label, Review._meta.model_name
        return HttpResponseRedirect(reverse(f"{site_ns}:{app}_{model}_changelist"))

    # ② DB 저장 (create_or_update_analysis_from_json 연결)
    def save_view(self, request):
        if request.method != "POST":
            return redirect(reverse("admin:travel_analysis_tool_run"))

        # hidden 필드로 넘어온 payload_* 키를 모두 모음
        saved = 0
        errors = 0
        for key, val in request.POST.items():
            if not key.startswith("payload_"):
                continue
            try:
                place_id = int(key.split("_", 1)[1])
                place = Place.objects.get(id=place_id)
                data = json.loads(val)  # 문자열 → dict
                create_or_update_analysis_from_json(place, data)
                saved += 1
            except Exception as e:
                errors += 1

        if saved:
            messages.success(request, f"DB 저장 완료: {saved}건")
        if errors:
            messages.error(request, f"저장 실패: {errors}건")

        return redirect(reverse("admin:travel_analysis_tool_run"))
