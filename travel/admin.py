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
from django.urls import reverse, path
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from .models import Place, Review, UploadEntry, AnalysisTool, PlaceAnalysis

from .services.LLM_analyzer import analyze_place_with_LLM
from .services.analysis_loader import create_or_update_analysis_from_json
from .models import Place, Review, UploadEntry, AnalysisTool, PlaceAnalysis

# ── 3. 유틸리티 함수 정의 ───────────────────────────────────────────────────────

# 주소 파서(대한민국 간단 규칙)
CITY_SUFFIXES = ("특별시", "광역시", "자치시", "특별자치시", "도", "특별자치도")
GU_SUFFIXES = ("구", "군", "시")

def split_kr_address(addr: str) -> tuple[str | None, str | None, str | None]:
    if not addr:
        return (None, None, None)
    toks = addr.strip().split()
    country = toks[0] if toks else None
    city = None
    city_gu = None
    
    # 1. 시/도 찾기
    for i, t in enumerate(toks[1:], start=1):
        if any(t.endswith(suf) for suf in CITY_SUFFIXES):
            city = t
            # 2. 구/군/시 찾기 (바로 다음 토큰 확인)
            if i + 1 < len(toks):
                t2 = toks[i + 1]
                if any(t2.endswith(suf) for suf in GU_SUFFIXES):
                    city_gu = t2
            break
            
    # 시/도 접미사가 없는 경우 (예: "대한민국 서울 강남구...")
    if not city and len(toks) >= 2:
        city = toks[1]
        if len(toks) >= 3:
            city_gu = toks[2]
            
    return (country, city, city_gu)


# place_id 27자리 난수 생성
_ALPHABET = string.ascii_letters + string.digits
def gen_unique_place_id(length: int = 27) -> str:
    while True:
        pid = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if not Place.objects.filter(place_id=pid).exists():
            return pid


# ── 4. 폼 정의 ──────────────────────────────────────────────────────────────────

class UploadJSONForm(forms.Form):
    file = forms.FileField(help_text="루트에 구(key) → attractions/restaurants/accommodations 리스트가 있는 JSON")
    mode = forms.ChoiceField(
        choices=[("create", "신규만 생성"), ("upsert", "업서트(있으면 업데이트)")],
        initial="upsert",
    )


# ── 5. Admin 클래스 정의 ────────────────────────────────────────────────────────

# 일반 Place 어드민
# ── 일반 Place 어드민 ────────────────────────────────────────────────
@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    # original list_display에서 Place 모델에 없는 필드(lat, lon, image_urls, opening_hours)를 제거하고 정리했습니다.
    list_display = (
        "name", "place_id", "category", "rating", "reviewCnt", "lat", "lon",
        "city", "city_gu", "phone", "image_urls", "opening_hours", "regdate", "chgdate",
    )
    search_fields = ("name", "place_id", "address", "city", "city_gu")
    list_filter = ("category", "city", "city_gu")


# 일반 Review 어드민
# ── 일반 Review 어드민 ────────────────────────────────────────────────
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("name", "author", "place_id", "rating", "like", "short_content")
    search_fields = ("name", "author", "place_id", "content")
    list_filter = ("rating",)

    def short_content(self, obj):
        return (obj.content or "")[:60]
    short_content.short_description = "content"


# ✅ 업로드 전용 어드민(프록시 모델: UploadEntry)
@admin.register(UploadEntry)
class UploadEntryAdmin(admin.ModelAdmin):
    """
    사이드바에 '데이터 업로드' 메뉴로 표시되며, 업로드 폼 및 처리 로직을 담당합니다.
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

        # 데이터 구조 분석: 루트에 리스트가 있거나, 키 아래에 리스트가 있는 형태 지원
        if isinstance(data, dict):
            def extract(d: Dict[str, Any]):
                add_bucket("attractions", d.get("tourist_attractions"))
                add_bucket("restaurants", d.get("restaurants"))
                add_bucket("accommodations", d.get("accommodations"))
                
            found = False
            # 최상위 딕셔너리의 값들을 순회하며 리스트를 포함하는 딕셔너리를 찾음
            for v in data.values():
                if isinstance(v, dict) and any(isinstance(v.get(k), list) for k in ("tourist_attractions","restaurants","accommodations")):
                    extract(v); found = True
            
            # 찾지 못했다면 루트 딕셔너리 자체가 데이터 컨테이너일 수 있음
            if not found:
                extract(data)
                
        elif isinstance(data, list):
            # 루트가 바로 리스트인 경우 (관광지로 간주)
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
                    
                    # 확장 필드 처리 (Place 모델에 필드가 없다면 주석 처리하거나 모델에 추가해야 함)
                    # if 'lat' in PlaceAdmin.list_display: place_row["lat"] = it.get("latitude") or ""
                    # if 'lon' in PlaceAdmin.list_display: place_row["lon"] = it.get("longitude") or ""
                    # if 'image_urls' in PlaceAdmin.list_display: place_row["image_urls"] = ", ".join(it.get("image_urls") or [])
                    # if 'opening_hours' in PlaceAdmin.list_display: place_row["opening_hours"] = ", ".join(it.get("opening_hours") or [])


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
                            if not content or not author: # 리뷰 내용이나 저자가 없으면 스킵
                                r_skipped += 1
                                continue
                                
                            try:
                                Review.objects.get_or_create(
                                    name=place_name,
                                    place_id=pid,
                                    author=author,
                                    content=content,
                                    defaults={"rating": rv.get("rating"), "like": rv.get("like") or 0},
                                )
                                r_created += 1
                            except Exception:
                                r_skipped += 1

        messages.success(
            request,
            f"Place 생성 {p_created} / 업데이트 {p_updated} | Review 생성 {r_created} / 스킵 {r_skipped}",
        )

        # 완료 후 리뷰 목록으로 리다이렉트
        site_ns = self.admin_site.name
        app, model = Review._meta.app_label, Review._meta.model_name
        return HttpResponseRedirect(reverse(f"{site_ns}:{app}_{model}_changelist"))
