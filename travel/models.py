from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

# Django 기본 User
User = get_user_model()

# =======================================================
# 1. 장소 관련 모델
# =======================================================

class Place(models.Model):
    # 장소 기본 정보
    name = models.CharField(max_length=200)
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

    # 이미지 경로
    image_urls = models.TextField(blank=True, null=True)

    # 오픈시간
    opening_hours = models.TextField(blank=True, null=True)

    # 생성/수정
    regdate = models.DateTimeField(auto_now_add=True)
    chgdate = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Place"
        verbose_name_plural = "Places"
        indexes = [models.Index(fields=["category", "city", "city_gu"])]

    def __str__(self):
        return f"{self.name} ({self.category})"

class PlaceAnalysis(models.Model):
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="analyses")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # 읽기용 복제 컬럼
    place_code = models.CharField(max_length=50, db_index=True)
    place_title = models.CharField(max_length=200)

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

    # 원본 JSON
    raw_json = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["place"], name="unique_analysis_per_place"),
        ]

    def __str__(self):
        return f"{self.place.name} 분석 ({self.created_at:%Y-%m-%d})"

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

class AnalysisTool(models.Model):
    class Meta:
        managed = False
        verbose_name = "장소 성격 LLM"
        verbose_name_plural = verbose_name
        default_permissions = ()

# =======================================================
# 2. 사용자, 여행 계획, 채팅 관련
# =======================================================

class TravelPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    location_city = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_seeking_partner = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.location_city}"

class ChatRoom(models.Model):
    room_name = models.CharField(max_length=100, unique=True)
    participants = models.ManyToManyField(User)
    travel_plan1 = models.ForeignKey(TravelPlan, on_delete=models.CASCADE, related_name='chatrooms_as_plan1')
    travel_plan2 = models.ForeignKey(TravelPlan, on_delete=models.CASCADE, related_name='chatrooms_as_plan2')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"ChatRoom({self.id}): {self.travel_plan1} <-> {self.travel_plan2}"

class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender.username}: {self.message[:20]}"

class ChatReport(models.Model):
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='reports')
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reporter.username} → {self.message.id}"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    intro = models.CharField(max_length=255, blank=True, null=True)
    interests = models.CharField(max_length=255, blank=True, null=True, default="")
    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, blank=True, null=True)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)

    def age(self):
        if not self.birth_date:
            return None
        today = timezone.now().date()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

    def __str__(self):
        return f"Profile of {self.user.username}"

# =======================================================
# 3. 데이터 업로드용 프록시 모델
# =======================================================

class UploadEntry(Place):
    """Place 모델 상속, 데이터 업로드/관리용"""
    class Meta:
        proxy = True
        verbose_name = "데이터 업로드"
        verbose_name_plural = "데이터 업로드"