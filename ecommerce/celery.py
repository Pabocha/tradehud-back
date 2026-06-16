"""
Configuration Celery pour le projet ecommerce.
"""
import os
from celery import Celery
from celery.schedules import crontab

# Définir la variable d'environnement de configuration Django par défaut
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')

# Créer l'instance Celery
app = Celery('ecommerce')

# Charger la configuration depuis Django settings avec préfixe CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscovery des tâches dans tous les apps Django
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    """Task de debug pour tester la configuration Celery."""
    print(f'Request: {self.request!r}')
