# =================================================================================
# DiaryRouter for diary-related models
# =================================================================================
class DiaryRouter:
    """
    A router to control all database operations on models in the
    travel application.
    Routes all operations for the 'travel' app to the 'diary_db' database.
    """
    diary_models = {'travel', 'diaryentry', 'tag', 'diarylist', 'diarydetail'} # Explicitly list models that go to diary_db
    def _is_travel_app(self, model):
        return model._meta.app_label == 'travel'

    def db_for_read(self, model, **hints):
        """
        Attempts to read models that are part of the diary functionality go to diary_db.
        Other travel app models go to default.
        """
        if model._meta.model_name in self.diary_models:
            return 'diary_db'
        
        # UserSelectedPlan은 이 목록에 없으므로 None이 리턴되어 default DB를 사용하게 됩니다.
        return None

    def db_for_write(self, model, **hints):
        """
        Attempts to write models that are part of the diary functionality go to diary_db.
        Other travel app models go to default.
        """
        if model._meta.model_name in self.diary_models:
            return 'diary_db'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        
        # Allow relations between auth app and any other app
        if obj1._meta.app_label == 'auth' or obj2._meta.app_label == 'auth':
            return True
        # Allow relations if both mod...
        
        # 1. 채팅 모델(ChatRouter가 처리)과 관계는 허용
        if obj1._meta.model_name in ChatRouter.chat_models or obj2._meta.model_name in ChatRouter.chat_models:
             return True

        # 2. 다이어리 모델과 default 모델(UserSelectedPlan) 간 관계 허용
        is_diary_model_1 = obj1._meta.model_name in self.diary_models
        is_diary_model_2 = obj2._meta.model_name in self.diary_models
        
        # 한쪽이 다이어리 모델(diary_db)이고 다른 한쪽이 default 모델(default DB)일 경우 관계 허용
        if (is_diary_model_1 and not is_diary_model_2) or (not is_diary_model_1 and is_diary_model_2):
            return True
            
        # 두 모델 모두 다이어리 DB 소속이거나, 둘 다 default DB 소속일 경우
        return None 


# =================================================================================
# ChatRouter for chat-related models
# =================================================================================
class ChatRouter:
    """
    'ChatRoom', 'ChatMessage', 'ChatReport' 모델에 대한 데이터베이스 작업을
    'chat_db'로 라우팅합니다.
    """
    
    # 💡 chat_db로 보낼 모델 이름 목록 (소문자로 작성)
    chat_models = {'chatroom', 'chatmessage', 'chatreport'}
    
    def db_for_read(self, model, **hints):
        """채팅 관련 모델 읽기 시 'chat_db'를 사용합니다."""
        if model._meta.model_name in self.chat_models:
            return 'chat_db'
        return None  # None은 다른 라우터나 기본값에 맡깁니다.

    def db_for_write(self, model, **hints):
        """채팅 관련 모델 쓰기 시 'chat_db'를 사용합니다."""
        if model._meta.model_name in self.chat_models:
            return 'chat_db'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        채팅 모델이 다른 모델과 관계를 맺을 수 있도록 허용합니다.
        (예: ChatRoom <-> TravelPlan 관계)
        """
        # 1. 두 객체 중 하나라도 채팅 모델인 경우 (다른 DB와의 관계 허용)
        if obj1._meta.model_name in self.chat_models or obj2._meta.model_name in self.chat_models:
            return True
        
        # 2. 다른 travel 모델 간의 관계는 DiaryRouter나 기본값에 맡깁니다.
        return None
  
