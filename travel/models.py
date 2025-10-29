from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
import uuid

# ----- 장소 테이블 ------------------------------------------
class Place(models.Model):
    name = models.CharField(max_length=200)
    place_id = models.CharField(max_length=120, blank=True, null=True, unique=True, db_index=True)
    category = models.CharField(max_length=40)

    rating = models.FloatField(blank=True, null=True)
    reviewCnt = models.IntegerField(blank=True, null=True)

    address = models.CharField(max_length=300, blank=True, null=True)
    country = models.CharField(max_length=50, blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    city_gu = models.CharField(max_length=50, blank=True, null=True)

    phone = models.CharField(max_length=100, blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    lat = models.CharField(max_length=50, blank=True, null=True)
    lon = models.CharField(max_length=50, blank=True, null=True)

    image_urls = models.TextField(blank=True, null=True)
    opening_hours = models.TextField(blank=True, null=True)

    regdate = models.DateTimeField(auto_now_add=True)
    chgdate = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Place"
        verbose_name_plural = "Places"
        indexes = [models.Index(fields=["category", "city", "city_gu"])]

    def __str__(self):
        return f"{self.name} ({self.category})"


# ----- 장소별 성격 분석 ------------------------------------------
class PlaceAnalysis(models.Model):
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="analyses")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    place_code = models.CharField(max_length=50, db_index=True)
    place_title = models.CharField(max_length=200)

    season_spring = models.IntegerField(null=True, blank=True)
    season_summer = models.IntegerField(null=True, blank=True)
    season_autumn = models.IntegerField(null=True, blank=True)
    season_winter = models.IntegerField(null=True, blank=True)

    mbti_E = models.IntegerField(null=True, blank=True)
    mbti_I = models.IntegerField(null=True, blank=True)
    mbti_S = models.IntegerField(null=True, blank=True)
    mbti_N = models.IntegerField(null=True, blank=True)
    mbti_T = models.IntegerField(null=True, blank=True)
    mbti_F = models.IntegerField(null=True, blank=True)
    mbti_J = models.IntegerField(null=True, blank=True)
    mbti_P = models.IntegerField(null=True, blank=True)

    group_couple = models.IntegerField(null=True, blank=True)
    group_friends = models.IntegerField(null=True, blank=True)
    group_family = models.IntegerField(null=True, blank=True)
    group_solo = models.IntegerField(null=True, blank=True)

    age_20s = models.IntegerField(null=True, blank=True)
    age_30s = models.IntegerField(null=True, blank=True)
    age_40s = models.IntegerField(null=True, blank=True)
    age_50plus = models.IntegerField(null=True, blank=True)

    gender_female = models.IntegerField(null=True, blank=True)
    gender_male = models.IntegerField(null=True, blank=True)

    keywords_csv = models.TextField(blank=True, default="")
    themes_csv = models.TextField(blank=True, default="")

    raw_json = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["place"], name="unique_analysis_per_place"),
        ]

    def __str__(self):
        return f"{self.place.name} 분석 ({self.created_at:%Y-%m-%d})"


# ----- 리뷰 ------------------------------------------
class Review(models.Model):
    author = models.CharField(max_length=200, blank=True, null=True)
    name = models.CharField(max_length=200, blank=True, null=True)
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


# ----- Proxy ------------------------------------------
class UploadEntry(Place):
    class Meta:
        proxy = True
        verbose_name = "데이터 업로드"
        verbose_name_plural = "데이터 업로드"


# ----- LLM용 ------------------------------------------
class AnalysisTool(models.Model):
    class Meta:
        managed = False
        verbose_name = "장소 성격 LLM"
        verbose_name_plural = verbose_name
        default_permissions = ()


# ----- 여행 계획 ------------------------------------------
class TravelPlan(models.Model):
    title = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Travel Plan"
        verbose_name_plural = "Travel Plans"

    def __str__(self):
        return f"{self.title} ({self.destination})"


# ----- 채팅방 ------------------------------------------
class ChatRoom(models.Model):
    name = models.CharField(max_length=100)
    plan = models.ForeignKey(
        'TravelPlan', on_delete=models.CASCADE, related_name="chat_rooms", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Chat Room"
        verbose_name_plural = "Chat Rooms"

    def __str__(self):
        return self.name


# ----- 사용자 프로필 ------------------------------------------

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    nickname = models.CharField(max_length=50)
    gender = models.CharField(max_length=10, blank=True)
    age_range = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=50, blank=True)
    language = models.CharField(max_length=50, blank=True)
    travel_style = models.CharField(max_length=50, blank=True)
    budget = models.CharField(max_length=50, blank=True)
    smoking = models.CharField(max_length=20, blank=True)  # 흡연 여부
    drinking = models.CharField(max_length=20, blank=True) # 음주 여부
    sns = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nickname
