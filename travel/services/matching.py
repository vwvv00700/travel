from datetime import date
from travel.models import TravelPlan, ChatRoom, UserSelectedPlan
from django.db.models import Q

def dates_overlap(start1, end1, start2, end2):
    """날짜 범위가 겹치는지 체크"""
    return max(start1, start2) <= min(end1, end2)

def auto_match_and_create_room(new_plan: UserSelectedPlan):
    """자동 매칭: 목적지 + 날짜 겹침 + 방 없는 사용자"""
    
    # 1. 매칭 후보군 검색 (자신 제외, 같은 목적지)
    candidates = UserSelectedPlan.objects.filter(
        location_city=new_plan.location_city # models.py에서 location_city 필드 사용
    ).exclude(user=new_plan.user) # 같은 사용자 제외

    created_rooms = []
    
    for candidate_plan in candidates:
        # 2. 날짜 겹치는지 확인
        if dates_overlap(
            new_plan.start_date, new_plan.end_date,
            candidate_plan.start_date, candidate_plan.end_date
        ):
            user1 = new_plan.user
            user2 = candidate_plan.user

            # 3. 중복 채팅방 확인 (이미 두 사용자 간 채팅방이 있는지 체크)
            # participants 필드에 user1과 user2가 모두 포함된 방을 찾음
            if ChatRoom.objects.filter(
                Q(travel_plan1__user=user1, travel_plan2__user=user2) |
                Q(travel_plan1__user=user2, travel_plan2__user=user1)
            ).exists():
                continue # 이미 방이 있으면 다음 후보로 넘어감

            # 4. 새로운 채팅방 생성 및 필드 채우기
            room_name = f"Chat_{user1.username}_vs_{user2.username}"
            
            # ChatRoom 생성 시 travel_plan1, travel_plan2를 모두 지정
            room = ChatRoom.objects.create(
                room_name=room_name,
                travel_plan1=new_plan,
                travel_plan2=candidate_plan 
            )
            
            # participants ManyToManyField 에 사용자 추가
            room.participants.add(user1, user2)
            created_rooms.append(room)

    return created_rooms # 생성된 방 목록을 반환하도록 변경