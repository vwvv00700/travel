from django.core.management.base import BaseCommand
from travel.models import ChatRoom

class Command(BaseCommand):
    help = "테스트용 채팅방 생성"

    def handle(self, *args, **kwargs):
        room_name = "test_room"
        room, created = ChatRoom.objects.get_or_create(room_name=room_name)
        if created:
            self.stdout.write(self.style.SUCCESS(f"테스트 채팅방 '{room_name}' 생성 완료!"))
        else:
            self.stdout.write(self.style.WARNING(f"테스트 채팅방 '{room_name}' 이미 존재함."))