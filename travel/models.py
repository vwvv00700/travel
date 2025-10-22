from django.db import models
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

class Travel(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class DiaryEntry(models.Model):
    travel = models.ForeignKey(Travel, on_delete=models.CASCADE, related_name='diary_entries') # Added ForeignKey
    photo = models.ImageField(upload_to='diary_photos/%Y/%m/%d/')
    location = models.CharField(max_length=200, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    comment = models.TextField(blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.travel.name} - {self.author.username}의 {self.created_at.strftime("%Y-%m-%d")} 기록'

    def save(self, *args, **kwargs):
        if self.photo and not self.pk: # Only process new images
            try:
                # Read the image data from the InMemoryUploadedFile
                image_bytes = self.photo.read()
                exif_data = get_exif_data(image_bytes)

                logger.debug(f"Extracted EXIF Data: {exif_data}") # Debug print

                lat, lon = get_gps_coordinates(exif_data)
                timestamp = get_timestamp(exif_data)

                logger.debug(f"Extracted Lat: {lat}, Lon: {lon}, Timestamp: {timestamp}") # Debug print

                if lat is not None:
                    self.latitude = lat
                if lon is not None:
                    self.longitude = lon
                    # Populate location name using reverse geocoding
                    try:
                        self.location = get_location_name(self.latitude, self.longitude)
                    except Exception as e:
                        logger.error(f"Reverse geocoding 중 오류 발생: {e}")
                        self.location = f"위도: {self.latitude:.4f}, 경도: {self.longitude:.4f}" # Fallback
                if timestamp is not None:
                    self.timestamp = timestamp
            except Exception as e:
                logger.error(f"DiaryEntry save() - 이미지 처리 중 오류 발생: {e}")
                # Optionally, you might want to raise a ValidationError here
                # or set a default value for fields that failed to process.

        super().save(*args, **kwargs)
