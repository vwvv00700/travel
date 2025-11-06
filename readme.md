# first-repository

1. 채팅방 이용시 필요한 설정
- set DJANGO_SETTINGS_MODULE=travelAgent.settings

2. 채팅방 서비스 실행
- daphne -p 8000 travelAgent.asgi:application

3. 다국어 변환에 필요한 명령어
    1. 다국어 파일 관리
    - python manage.py makemessages -l en
    - python manage.py makemessages -l es

    2. 다국어 컴파일
    - python manage.py compilemessages