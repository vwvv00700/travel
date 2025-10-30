class DiaryRouter:
    """
    A router to control all database operations on models in the
    travel application.
    """
    diary_models = {'travel', 'diaryentry', 'diarylist', 'diarydetail'} # Explicitly list models that go to diary_db

    def db_for_read(self, model, **hints):
        """
        Attempts to read models that are part of the diary functionality go to diary_db.
        Other travel app models go to default.
        """
        if model._meta.model_name in self.diary_models:
            return 'diary_db'
        elif model._meta.app_label == 'travel': # Other travel app models go to default
            return 'default'
        return None

    def db_for_write(self, model, **hints):
        """
        Attempts to write models that are part of the diary functionality go to diary_db.
        Other travel app models go to default.
        """
        if model._meta.model_name in self.diary_models:
            return 'diary_db'
        elif model._meta.app_label == 'travel': # Other travel app models go to default
            return 'default'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations if both objects are in the same database, or if they are
        between diary models and other travel models (which are in default).
        """
        if obj1._meta.app_label == 'travel' and obj2._meta.app_label == 'travel':
            # If both are diary models, or both are non-diary models, or one is diary and other is non-diary
            return True
        # Allow relations between auth app and any other app
        if obj1._meta.app_label == 'auth' or obj2._meta.app_label == 'auth':
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        - Diary models ('travel', 'diaryentry') migrate only to 'diary_db'.
        - All other models (including other 'travel' models and framework apps
          like 'auth') migrate only to the 'default' database.
        """
        is_diary_model = app_label == 'travel' and model_name in self.diary_models

        if db == 'diary_db':
            return is_diary_model
        else: # db == 'default' or any other db
            return not is_diary_model