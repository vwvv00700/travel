# travel/models.py
from django.db import models
from sqlmodel import SQLModel, Field, create_engine, Session
from typing import Optional, List


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

    engine = create_engine("sqlite:///database.db")

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    intro: str
    interests: Optional[str] = ""  # 배지 저장 (콤마 구분)

def init_db():
    SQLModel.metadata.create_all(engine)