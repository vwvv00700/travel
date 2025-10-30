class DiaryRouter:
    """
    Routes all operations for the 'travel' app to the 'diary_db' database.
    """
    def _is_travel_app(self, model):
        return model._meta.app_label == 'travel'

    def db_for_read(self, model, **hints):
        if self._is_travel_app(model):
            return 'diary_db'
        return None

    def db_for_write(self, model, **hints):
        if self._is_travel_app(model):
            return 'diary_db'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow any relation involving the auth app
        if obj1._meta.app_label == 'auth' or obj2._meta.app_label == 'auth':
            return True
        # Allow relations if both models are in the travel app
        if obj1._meta.app_label == 'travel' and obj2._meta.app_label == 'travel':
            return True
        # Otherwise, default to Django's behavior
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'travel':
            return db == 'diary_db'
        if db == 'diary_db':
            return False
        return None