"""
실행 방법:
(my_venv) C:\Users\Admin\travel-main> python setup_test_data.py
"""

import os
import django
from datetime import date

# Django 환경 설정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "travelAgent.settings")
django.setup()

# 모델 import
from django.contrib.auth import get_user_model
from travel.models import TravelPlan, ChatRoom

# 1. 기존 DB 초기화 (주의: 실제 데이터 삭제됨)
DB_FILE = "db.sqlite3"
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    print("✅ 기존 DB 삭제 완료")

# 2. 마이그레이션 적용
print("🛠 마이그레이션 적용 중...")
os.system("python manage.py makemigrations")
os.system("python manage.py migrate")
print("✅ 마이그레이션 완료")

# 3. 테스트용 사용자 생성
User = get_user_model()

user1 = User.objects.create_user(username='user1', password='1234', email='user1@example.com')
user2 = User.objects.create_user(username='user2', password='1234', email='user2@example.com')
print(f"✅ 테스트 사용자 생성 완료: {user1.username}, {user2.username}")

# 4. TravelPlan 생성 (매칭용)
tp1 = TravelPlan.objects.create(user=user1, location_city='서울', start_date=date.today(), end_date=date.today(), is_seeking_partner=True)
tp2 = TravelPlan.objects.create(user=user2, location_city='서울', start_date=date.today(), end_date=date.today(), is_seeking_partner=True)
print("✅ 테스트용 TravelPlan 생성 완료")

# 5. ChatRoom 생성 및 두 사용자 추가
chat = ChatRoom.objects.create(room_name=f'{user1.username}_{user2.username}')
chat.users.add(user1, user2)
print(f"✅ ChatRoom 생성 완료: {chat.room_name}")

print("🎉 테스트 환경 세팅 완료!")