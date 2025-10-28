from django.utils import timezone
from travel.models import TravelPlan, ChatRoom
from django.contrib.auth import get_user_model

User = get_user_model()

def find_matching_travel_plans(new_plan):
    """
    new_plan: 방금 생성된 TravelPlan
    조건:
      1. is_seeking_partner=True
      2. 다른 사용자
      3. 여행 기간 겹침
      4. 위치(city) 동일
    """
    matches = TravelPlan.objects.filter(
        is_seeking_partner=True,
        location_city=new_plan.location_city,
        start_date__lte=new_plan.end_date,
        end_date__gte=new_plan.start_date
    ).exclude(user=new_plan.user)
    return matches

def create_chatroom_for_plan(new_plan):
    matches = find_matching_travel_plans(new_plan)
    chatrooms_created = []
    
    for match_plan in matches:
        # 이미 같은 계획끼리 채팅방 있는지 확인
        exists = ChatRoom.objects.filter(
            travel_plan1=new_plan, travel_plan2=match_plan
        ).exists() or ChatRoom.objects.filter(
            travel_plan1=match_plan, travel_plan2=new_plan
        ).exists()
        
        if not exists:
            room_name = f"{new_plan.user.username}_{match_plan.user.username}_{timezone.now().timestamp()}"
            room = ChatRoom.objects.create(
                room_name=room_name,
                travel_plan1=new_plan,
                travel_plan2=match_plan
            )
            room.participants.add(new_plan.user, match_plan.user)
            chatrooms_created.append(room)
    
    return chatrooms_created