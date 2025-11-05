from datetime import date
from travel.models import TravelPlan, ChatRoom, UserSelectedPlan
from django.db.models import Q
from django.db import IntegrityError

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

def matchingRoom(request):
    # if not request.user.is_authenticated:
    #     return redirect('login')
    
    # travel_plans = UserSelectedPlan.objects.all()
    travel_plans = UserSelectedPlan.objects.filter(user=request.user)
    match_refresh = False
    messages = ""

    for travel in travel_plans:
        startDate = travel.start_date
        endDate = travel.end_date

        user_areas = travel.plan.user_query.get("areas")
        # user_plan = travel.plan
        plan_user_1 = travel.user

        areas_str = ",".join(user_areas)    
        list = UserSelectedPlan.objects.filter(start_date=startDate, end_date=endDate)
        for item in list:
            user_list = []
            other_area = item.plan.user_query.get("areas")
            # other_plan = item.plan
            plan_user_2 = item.user

            if travel.id == item.id:
                continue
            
            user_list.append(plan_user_1.username)
            user_list.append(plan_user_2.username)
            users = sorted(user_list)

            room_name = f"Chat_{users[0]}_vs_{users[1]}_{areas_str}_{startDate.strftime('%Y%m%d')}-{endDate.strftime('%Y%m%d')}"

            if sorted(user_areas) == sorted(other_area):
                
                if not ChatRoom.objects.filter(room_name=room_name).exists():
                    try:
                        room, created = ChatRoom.objects.get_or_create(
                            room_name=room_name,
                            defaults={
                                "plan_user_1": str(plan_user_1),
                                "travel_plan1_pk": travel.id,
                                "plan_user_2": str(plan_user_2),
                                "travel_plan2_pk": item.id,
                            }
                        )
                        print(f"ChatRoom 생성 완료")
                        if created:
                            print("ChatRoom created:", room.pk)
                            messages = "새로운 채팅방이 생성되었습니다!"
                            match_refresh = True
                        else:
                            print("ChatRoom already existed (race avoided).")
                            messages = "채팅방이 이미 생성 되었습니다."
                    except IntegrityError as e:
                        print("IntegrityError during ChatRoom create:", e)
                        # 추가 로그: 각각 PK 다시 확인
                        print("user_plan.pk (retry):", getattr(travel, "pk", None))
                        print("other_plan.pk (retry):", getattr(item, "pk", None))
                        messages = "새로운 채팅방 생성중 오류가 발생했습니다."
                else:
                    print("채팅방이 이미 존재합니다.")
                    messages = "채팅방이 이미 존재합니다."
                
    # print("저장됨!")
    # return redirect('match')
    # return render(request, "travel/match_chat.html", context)

    return match_refresh, messages