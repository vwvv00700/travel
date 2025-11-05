# ----- 장소 테이블 ------------------------------------------
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import logging
import io
from datetime import datetime
import requests # Added for reverse geocoding
import os # Added to get API key from environment variables

logger = logging.getLogger(__name__)


def get_exif_data(image_bytes):
    exif_data = {}
    try:
        img_file = io.BytesIO(image_bytes)
        with Image.open(img_file) as img:
            info = img._getexif()
            if info:
                for tag, value in info.items():
                    decoded = TAGS.get(tag, tag)
                    if decoded == "GPSInfo":
                        gps_data = {}
                        for t in value:
                            sub_decoded = GPSTAGS.get(t, t)
                            gps_data[sub_decoded] = value[t]
                        exif_data[decoded] = gps_data
                    else:
                        exif_data[decoded] = value
    except Exception as e:
        logger.error(f"EXIF 데이터를 읽는 중 오류 발생: {e}")
    return exif_data

def _convert_to_degrees(value):
    d = float(value[0])
    m = float(value[1])
    s = float(value[2])

    return d + (m / 60.0) + (s / 3600.0)

def get_gps_coordinates(exif_data):
    lat = None
    lon = None

    if "GPSInfo" in exif_data:
        gps_info = exif_data["GPSInfo"]

        gps_latitude = gps_info.get("GPSLatitude")
        gps_latitude_ref = gps_info.get('GPSLatitudeRef')
        gps_longitude = gps_info.get('GPSLongitude')
        gps_longitude_ref = gps_info.get('GPSLongitudeRef')

        if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
            lat = _convert_to_degrees(gps_latitude)
            if gps_latitude_ref != "N":
                lat = -lat

            lon = _convert_to_degrees(gps_longitude)
            if gps_longitude_ref != "E":
                lon = -lon
    return lat, lon

def get_timestamp(exif_data):
    if "DateTimeOriginal" in exif_data:
        dt_str = exif_data["DateTimeOriginal"]
        try:
            # EXIF DateTimeOriginal format is "YYYY:MM:DD HH:MM:SS"
            return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
        except ValueError: # Handle cases where format might be slightly different
            pass
    return None

def get_location_name(latitude, longitude):
    KAKAO_API_KEY = os.environ.get('KAKAO_LOCAL_API_KEY') # Get API key from environment variable
    if not KAKAO_API_KEY:
        logger.warning("KAKAO_LOCAL_API_KEY 환경 변수가 설정되지 않았습니다. Nominatim을 사용합니다.")
        # Fallback to Nominatim if Kakao API key is not set
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={latitude}&lon={longitude}&accept-language=ko"
            headers = {'User-Agent': 'TravelDiaryApp/1.0'}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get('display_name', f"위도: {latitude:.4f}, 경도: {longitude:.4f}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Nominatim Reverse geocoding 오류: {e}")
            return f"위도: {latitude:.4f}, 경도: {longitude:.4f}"
        except Exception as e:
            logger.error(f"Nominatim 위치 이름 가져오는 중 오류: {e}")
            return f"위도: {latitude:.4f}, 경도: {longitude:.4f}"

    try:
        # Using Kakao Local API for reverse geocoding
        url = "https://dapi.kakao.com/v2/local/geo/coord2address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"x": longitude, "y": latitude, "input_coord": "WGS84"}
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if data and data.get('documents'):
            address_info = data['documents'][0]['address']
            road_address_info = data['documents'][0]['road_address']

            if road_address_info and road_address_info['address_name']:
                return road_address_info['address_name']
            elif address_info and address_info['address_name']:
                return address_info['address_name']
        return f"위도: {latitude:.4f}, 경도: {longitude:.4f}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Kakao Reverse geocoding 오류: {e}")
        return f"위도: {latitude:.4f}, 경도: {longitude:.4f}"
    except Exception as e:
        logger.error(f"Kakao 위치 이름 가져오는 중 오류: {e}")
        return f"위도: {latitude:.4f}, 경도: {longitude:.4f}"



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

# class PlaceAnalysis(models.Model):
#     place = models.OneToOneField(
#         'Place',
#         on_delete=models.CASCADE,
#         related_name='analysis'
#     )
#     created_at = models.DateTimeField(auto_now_add=True)
#     place_code = models.CharField(max_length=50)
#     place_title = models.CharField(max_length=200)
#     season_spring = models.IntegerField(null=True, blank=True)
#     season_summer = models.IntegerField(null=True, blank=True)
#     season_autumn = models.IntegerField(null=True, blank=True)
#     season_winter = models.IntegerField(null=True, blank=True)
#     mbti_E = models.IntegerField(null=True, blank=True)
#     mbti_I = models.IntegerField(null=True, blank=True)
#     mbti_S = models.IntegerField(null=True, blank=True)
#     mbti_N = models.IntegerField(null=True, blank=True)
#     mbti_T = models.IntegerField(null=True, blank=True)
#     mbti_F = models.IntegerField(null=True, blank=True)
#     mbti_J = models.IntegerField(null=True, blank=True)
#     mbti_P = models.IntegerField(null=True, blank=True)
#     group_couple = models.IntegerField(null=True, blank=True)
#     group_friends = models.IntegerField(null=True, blank=True)
#     group_family = models.IntegerField(null=True, blank=True)
#     group_solo = models.IntegerField(null=True, blank=True)
#     age_20s = models.IntegerField(null=True, blank=True)
#     age_30s = models.IntegerField(null=True, blank=True)
#     age_40s = models.IntegerField(null=True, blank=True)
#     age_50plus = models.IntegerField(null=True, blank=True)
#     gender_female = models.IntegerField(null=True, blank=True)
#     gender_male = models.IntegerField(null=True, blank=True)
#     keywords_csv = models.TextField()
#     themes_csv = models.TextField()
#     raw_json = models.TextField(null=True, blank=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = 'travel_placeanalysis'
#         verbose_name = "Place Analysis"
#         verbose_name_plural = "Place Analyses"

#     def __str__(self):
#         return f"Analysis for {self.place.name}"


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


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True, db_index=True)

    class Meta:
        verbose_name = "태그"
        verbose_name_plural = "태그"

    def __str__(self):
        return self.name


class Travel(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    author_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '다이어리 목록'
        verbose_name_plural = '다이어리 목록'

    def __str__(self):
        return self.name

class DiaryEntry(models.Model):
    diary = models.ForeignKey(Travel, on_delete=models.CASCADE, related_name='diary_entries') # Renamed from 'travel'
    media_file = models.FileField(upload_to='diary_media/%Y/%m/%d/', null=True)
    media_type = models.CharField(max_length=10, blank=True)
    tags = models.ManyToManyField('Tag', blank=True, related_name='diary_entries')
    location = models.CharField(max_length=200, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    comment = models.TextField(blank=True)
    author_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '다이어리 상세'
        verbose_name_plural = '다이어리 상세'

    def __str__(self):
        return f'{self.diary.name} - Author ID: {self.author_id}의 {self.created_at.strftime("%Y-%m-%d")} 기록'

    def save(self, *args, **kwargs):
        # Process new media file
        if self.media_file and not self.pk:
            content_type = self.media_file.file.content_type
            if 'image' in content_type:
                self.media_type = 'image'
                try:
                    image_bytes = self.media_file.read()
                    exif_data = get_exif_data(image_bytes)
                    logger.debug(f"Extracted EXIF Data: {exif_data}")

                    lat, lon = get_gps_coordinates(exif_data)
                    timestamp = get_timestamp(exif_data)
                    logger.debug(f"Extracted Lat: {lat}, Lon: {lon}, Timestamp: {timestamp}")

                    if lat is not None:
                        self.latitude = lat
                    if lon is not None:
                        self.longitude = lon
                        try:
                            self.location = get_location_name(self.latitude, self.longitude)
                        except Exception as e:
                            logger.error(f"Reverse geocoding 중 오류 발생: {e}")
                            self.location = f"위도: {self.latitude:.4f}, 경도: {self.longitude:.4f}" # Fallback
                    if timestamp is not None:
                        self.timestamp = timestamp
                except Exception as e:
                    logger.error(f"DiaryEntry save() - 이미지 메타데이터(EXIF) 처리 중 오류 발생: {e}. GPS/시간 정보 없이 저장됩니다.")
            
            elif 'video' in content_type:
                self.media_type = 'video'
                # For videos, we might not have EXIF data, so location/timestamp might need to be set manually
                # or from other sources if available.

        super().save(*args, **kwargs)
        
class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    nickname = models.CharField(max_length=30, blank=True)
    bio = models.TextField(blank=True)
    # 예: 선호 여행 타입, 관심 도시 등 자유롭게 확장 가능
    preferred_style = models.CharField(
        max_length=50,
        blank=True,
        help_text="ex) 힐링 위주, 맛집 위주, 액티비티 위주 등"
    )
    mbti = models.CharField(max_length=10, blank=True)

    def __str__(self):
        return self.nickname or self.user.username
    
class TravelPlan(models.Model):
    title = models.CharField(max_length=200)
    data = models.JSONField()  # 전체 플랜 구조 (day_plans, day_waypoints, guide_text 등 저장 가능)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class UserSelectedPlan(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="selected_plans"
    )
    plan = models.ForeignKey(
        TravelPlan,
        on_delete=models.CASCADE,
        related_name="chosen_by"
    )
    selected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "plan")  # 같은 플랜 중복 저장 방지

    def __str__(self):
        return f"{self.user.username} -> {self.plan.title}"
