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
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    
    # 1. 매칭 조건
    location_city = models.CharField(max_length=100)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    is_seeking_partner = models.BooleanField(default=True)
    
    # 2. 동선 정보
    route_data = models.JSONField(default=list) 

    regdate = models.DateTimeField(auto_now_add=True)
    chgdate = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "여행 계획"
        verbose_name_plural = "여행 계획"

    def __str__(self):
        return f"{self.user.username}의 {self.location_city} 계획"

# =======================================================
# 3. 채팅 모델 (Channels용 필수 추가)
# =======================================================

class ChatRoom(models.Model):
    # ChatRoom의 고유 이름 (웹소켓 room_name으로 사용: 예: chat_1_5)
    room_name = models.CharField(max_length=255, unique=True, db_index=True)
    
    # 두 사용자 관계
    user1 = models.ForeignKey(User, related_name='chatrooms_as_user1', on_delete=models.CASCADE)
    user2 = models.ForeignKey(User, related_name='chatrooms_as_user2', on_delete=models.CASCADE)
    
    regdate = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chat between {self.user1.username} and {self.user2.username}"


class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['timestamp']
        verbose_name = "채팅 메시지"
        verbose_name_plural = "채팅 메시지"
        
    def __str__(self):
        return f"[{self.timestamp.strftime('%H:%M')}] {self.sender.username}: {self.content[:20]}..."

class UploadEntry(Place):
    """
    Place 모델을 상속받는 프록시 모델입니다.
    데이터 업로드/관리 목적으로 사용된 것으로 추정됩니다.
    """
    class Meta:
        proxy = True
        verbose_name = "데이터 업로드"
        verbose_name_plural = "데이터 업로드"

    # engine = create_engine("sqlite:///database.db") 
    # ❌ Django ORM 사용 시 이 코드는 제거해야 합니다!
    pass # 기존 코드에서 create_engine을 제거한 뒤 pass로 대체
    
