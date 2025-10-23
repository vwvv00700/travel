# travel/models.py
from django.db import models
from django.utils import timezone

# ----- 장소 테이블 ------------------------------------------
class Place(models.Model):
    # 장소 기본 정보
    name = models.CharField(max_length=200)  # 장소명
    place_id = models.CharField(max_length=120, blank=True, null=True, unique=True, db_index=True)
    category = models.CharField(max_length=40)  # attractions / restaurants / accommodations

    # 평점/리뷰수
    rating = models.FloatField(blank=True, null=True)
    reviewCnt = models.IntegerField(blank=True, null=True)

    # 주소
    address = models.CharField(max_length=300, blank=True, null=True)
    country = models.CharField(max_length=50, blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    city_gu = models.CharField(max_length=50, blank=True, null=True)

    # 연락처/사이트
    phone = models.CharField(max_length=100, blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    # 위도 / 경도
    lat = models.CharField(max_length=50, blank=True, null=True)
    lon = models.CharField(max_length=50, blank=True, null=True)

    # 생성/수정
    regdate = models.DateTimeField(auto_now_add=True)
    chgdate = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Place"
        verbose_name_plural = "Places"
        indexes = [models.Index(fields=["category", "city", "city_gu"])]

    def __str__(self):
        return f"{self.name} ({self.category})"

# ----- 장소별 성격 분석 테이블 ------------------------------------------
class PlaceAnalysis(models.Model):
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="analyses")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)  # 있으면 편함

    # 추가: place_id와 name(읽기용 복제 컬럼)
    place_code = models.CharField(max_length=50, db_index=True)  # FK id 복사본
    place_title = models.CharField(max_length=200)  # 장소명 복사본

    # 시즌별 점수
    season_spring = models.IntegerField(null=True, blank=True)
    season_summer = models.IntegerField(null=True, blank=True)
    season_autumn = models.IntegerField(null=True, blank=True)
    season_winter = models.IntegerField(null=True, blank=True)

    # MBTI
    mbti_E = models.IntegerField(null=True, blank=True)
    mbti_I = models.IntegerField(null=True, blank=True)
    mbti_S = models.IntegerField(null=True, blank=True)
    mbti_N = models.IntegerField(null=True, blank=True)
    mbti_T = models.IntegerField(null=True, blank=True)
    mbti_F = models.IntegerField(null=True, blank=True)
    mbti_J = models.IntegerField(null=True, blank=True)
    mbti_P = models.IntegerField(null=True, blank=True)

    # 방문자 그룹
    group_couple = models.IntegerField(null=True, blank=True)
    group_friends = models.IntegerField(null=True, blank=True)
    group_family = models.IntegerField(null=True, blank=True)
    group_solo = models.IntegerField(null=True, blank=True)

    # 연령대
    age_20s = models.IntegerField(null=True, blank=True)
    age_30s = models.IntegerField(null=True, blank=True)
    age_40s = models.IntegerField(null=True, blank=True)
    age_50plus = models.IntegerField(null=True, blank=True)

    # 성별
    gender_female = models.IntegerField(null=True, blank=True)
    gender_male = models.IntegerField(null=True, blank=True)

    # 키워드/테마
    keywords_csv = models.TextField(blank=True, default="")
    themes_csv = models.TextField(blank=True, default="")

    # 원본 JSON도 같이 저장
    raw_json = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["place"], name="unique_analysis_per_place"),
        ]

    def __str__(self):
        return f"{self.place.name} 분석 ({self.created_at:%Y-%m-%d})"

# ----- 장소 리뷰 테이블 ------------------------------------------
class Review(models.Model):
    # 리뷰 작성자
    author = models.CharField(max_length=200, blank=True, null=True)
    # 
    name = models.CharField(max_length=200, blank=True, null=True)
    # 어떤 장소에 대한 리뷰인지(문자열 키, FK 아님)
    place_id = models.CharField(max_length=120, db_index=True)
    rating = models.FloatField(blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    like = models.IntegerField(blank=True, null=True, default=0)

    class Meta:
        verbose_name = "Review"
        verbose_name_plural = "Reviews"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "place_id", "author", "content"],
                name="uniq_review_placeid_author_content",
            )
        ]

    def __str__(self):
        who = self.author or "anonymous"
        return f"{who} → {self.place_id}"


class UploadEntry(Place):
    class Meta:
        proxy = True
        verbose_name = "데이터 업로드"
        verbose_name_plural = "데이터 업로드"

class AnalysisTool(models.Model):
    class Meta:
        managed = False
        verbose_name = "장소 성격 LLM"
        verbose_name_plural = verbose_name
        default_permissions = ()  # add/change/delete/view 자동권한 생성 안 함