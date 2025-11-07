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


4. git 명령어
- Git 원격 저장소를 추가
git remote add origin https://github.com/vwvv00700/travel.git

- 원격 최신 내용 가져오기
git fetch origin [브랜치 명]

- 파일 당겨오기
git pull origin [브랜치 명]

- 작업 커밋하기
git add .
git commit -m "내용"

- 브랜치로 올리기
git push -u origin [브랜치 명]

- 해당 브랜치 clone
git clone --branch dev_ds --single-branch https://github.com/vwww00700/travel.git

-- 이전 상황으로 돌리기
git reflog
git reset --hard HEAD@{26}


5. 데이터 베이스 백업하기
python manage.py dumpdata travel.Place travel.Placeanalysis travel.Review --database=default --indent 4 > place_backup.json
python manage.py dumpdata travel.Placeanalysis --database=default --indent 4 > placeanalysis_backup.json
python manage.py dumpdata travel.Review --database=default --indent 4 > place_review_backup.json

python manage.py dumpdata travel.diaryentry travel.travel --database=diary_db --indent 4 > diary_core_backup.json


- .sqlite3 파일 모두 지우기
- migrations 폴더안에 .py 파일 모두 지우기 (__init__.py 제외)

- python manage.py makemigrations travel
- python manage.py migrate --database=default
- python manage.py migrate travel --database=diary_db
- python manage.py migrate travel --database=chat_db

python manage.py createsuperuser


데이터 베이스 복구
python manage.py loaddata place_backup.json --database=default
python manage.py loaddata place_review_backup.json --database=default
python manage.py loaddata placeanalysis_backup.json --database=default

python manage.py loaddata diary_core_backup.json --database=diary_db
