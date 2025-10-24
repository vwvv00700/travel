from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
# SQLModel 관련 불필요한 import 및 코드는 모두 제거했습니다.

# Django의 기본 사용자 모델을 가져옵니다.
User = get_user_model() 

# =======================================================
# 1. 기존 모델 (Place, Review)
# =======================================================

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

    # 생성/수정
    regdate = models.DateTimeField(auto_now_add=True)
    chgdate = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Place"
        verbose_name_plural = "Places"
        indexes = [models.Index(fields=["category", "city", "city_gu"])]

    def __str__(self):
        return f"{self.name} ({self.category})"


class Review(models.Model):
    # 리뷰 작성자
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


# =======================================================
# 2. 인증/여행 계획 모델 (문법 오류 수정됨)
# =======================================================

class UserProfile(models.Model):
    # 1:1 관계를 통해 Django의 기본 User와 연결
    user = models.OneToOneField(User, on_delete=models.CASCADE) 
    
    intro = models.CharField(max_length=255, blank=True, null=True)
    interests = models.CharField(max_length=255, blank=True, null=True, default="") # 배지 저장
    
    def __str__(self):
        return f"Profile of {self.user.username}"


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

class UploadEntry(Place):
    """
    Place 모델을 상속받는 프록시 모델입니다.
    데이터 업로드/관리 목적으로 사용된 것으로 추정됩니다.
    """
    class Meta:
        proxy = True
        verbose_name = "데이터 업로드"
        verbose_name_plural = "데이터 업로드"
    pass
    
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    intro = models.CharField(max_length=255, blank=True, null=True)
    interests = models.CharField(max_length=255, blank=True, null=True, default="")
    
    # 추가 필드
    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, blank=True, null=True)  # '남성' / '여성' 등
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)

    def age(self):
        if not self.birth_date:
            return None
        today = timezone.now().date()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

    def __str__(self):
        return f"Profile of {self.user.username}"
    
    # =======================================================
# 🚨 채팅 메시지 신고 기능
# =======================================================
class ChatReport(models.Model):
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')  # 신고한 사람
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='reports')  # 신고 대상 메시지
    reason = models.TextField(blank=True, null=True)  # 신고 사유
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reporter.username} → {self.message.id}"