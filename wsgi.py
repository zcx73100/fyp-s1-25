# wsgi.py
from FYP25S109 import create_app
from apscheduler.schedulers.background import BackgroundScheduler
from main import send_assignment_notification

app = create_app()

# Start your background job in each Gunicorn worker
scheduler = BackgroundScheduler()
scheduler.add_job(send_assignment_notification, 'cron', hour=0, minute=0)
scheduler.start()
