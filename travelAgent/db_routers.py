# =================================================================================
# DiaryRouter for diary-related models
# =================================================================================
class DiaryRouter:
    """
    A router to control all database operations on models in the
    travel application.
    Routes all operations for the 'travel' app to the 'diary_db' database.
    """
    diary_models = {'travel', 'diaryentry', 'diarylist', 'diarydetail'} # Explicitly list models that go to diary_db
    def _is_travel_app(self, model):
        return model._meta.app_label == 'travel'

    def db_for_read(self, model, **hints):
        """
        Attempts to read models that are part of the diary functionality go to diary_db.
        Other travel app models go to default.
        """
        if model._meta.model_name in self.diary_models:
            return 'diary_db'
        
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
        # Allow relations if both models are in the travel app
        if obj1._meta.app_label == 'travel' and obj2._meta.app_label == 'travel':
            return True
        # Otherwise, default to Django's behavior
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        - Diary models ('travel', 'diaryentry') migrate only to 'diary_db'.
        - All other models (including other 'travel' models and framework apps
          like 'auth') migrate only to the 'default' database.
        """
        # if model_name in self.diary_models:
        #     return db == 'diary_db'

        # if db == 'diary_db':
        #     return False

        # return None
        if app_label == 'travel':
            return db == 'diary_db'
        if db == 'diary_db':
            return False
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

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        채팅 관련 모델은 'chat_db'에만 마이그레이션되도록 보장합니다.
        """
        if model_name in self.chat_models:
            return db == 'chat_db'
        
        if db == 'chat_db':
            return False

        # chat_models에 속하지 않는 모든 모델은 마이그레이션을 허용하지 않음 (다른 라우터에 맡김)
        return None
  
