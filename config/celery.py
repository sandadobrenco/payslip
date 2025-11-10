import os
from celery import Celery


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

@app.on_after_finalize.connect
def _force_import_tasks(sender, **kwargs):
    try:
        from core.services.email_service import task_send_csv_to_manager
    except ImportError:
        pass
