from django.apps import AppConfig


class CommentairesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'commentaires'

    def ready(self):
        import commentaires.signals  

