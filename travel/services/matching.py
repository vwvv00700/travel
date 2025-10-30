from datetime import date
from travel.models import TravelPlan, ChatRoom

def dates_overlap(start1, end1, start2, end2):
    """날짜 범위가 겹치는지 체크"""
    return max(start1, start2) <= min(end1, end2)

def create_chatroom_for_plan(travel_plan: TravelPlan):
    if hasattr(travel_plan, "chatroom"):
        return travel_plan.chatroom
    return ChatRoom.objects.create(travel_plan=travel_plan)

def auto_match_and_create_room(travel_plan: TravelPlan):
    """자동 매칭: 목적지 + 날짜 겹침 + 방 없는 사용자"""
    candidates = TravelPlan.objects.filter(
        destination=travel_plan.destination
    ).exclude(id=travel_plan.id)

    for candidate in candidates:
        # 날짜 겹치는지 확인
        if dates_overlap(
            travel_plan.start_date, travel_plan.end_date,
            candidate.start_date, candidate.end_date
        ):
            # 이미 채팅방이 없으면 매칭
            if not hasattr(candidate, "chatroom"):
                room = create_chatroom_for_plan(travel_plan)
                create_chatroom_for_plan(candidate)
                return room

    # 매칭 없으면 자기만 방 생성
    return create_chatroom_for_plan(travel_plan)