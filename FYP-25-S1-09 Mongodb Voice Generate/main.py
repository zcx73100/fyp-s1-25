from datetime import datetime, timedelta
from bson.objectid import ObjectId
from apscheduler.schedulers.background import BackgroundScheduler
from FYP25S109 import create_app
from flask_pymongo import PyMongo
from flask_cors import CORS
import logging
import os

app = create_app()
CORS(app, supports_credentials=True)
# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Assuming you're using Flask-PyMongo to interact with MongoDB
mongo = PyMongo(app)


@app.template_filter('format_datetime')
def format_datetime(value):
    if value is None:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%b %d, %Y at %I:%M %p")


def send_assignment_notification():
    logger.debug("Starting the send_assignment_notification function.")
    
    today = datetime.now()
    day_after = today + timedelta(days=1)
    two_days_after = today + timedelta(days=2)
    
    logger.debug(f"Looking for assignments due between {today} and {two_days_after}.")

    # Query to find assignments due in the next 1 or 2 days
    query = {
        "due_date": {
            "$gte": today,
            "$lte": two_days_after
        }
    }

    # Fetch assignments and count
    assignments_cursor = mongo.db.assignments.find(query)
    assignment_count = mongo.db.assignments.count_documents(query)

    logger.debug(f"Found {assignment_count} assignments in the date range.")

    for assignment in assignments_cursor:
        due_date = assignment.get('due_date')
        title = assignment.get('title', 'Untitled')

        if not due_date:
            logger.warning(f"Assignment '{title}' has no due date, skipping.")
            continue

        days_until_due = (due_date - today).days
        logger.debug(f"Assignment '{title}' is due in {days_until_due} day(s).")

        if days_until_due not in [1, 2]:
            logger.debug(f"Skipping assignment '{title}' as it's not due in 1 or 2 days.")
            continue

        message = f"Reminder: Assignment '{title}' is due in {days_until_due} day(s)!"
        priority = 2 if days_until_due == 1 else 1

        classroom_id = assignment.get('classroom_id')
        if not classroom_id:
            logger.warning(f"Assignment '{title}' has no classroom_id, skipping.")
            continue

        classroom = mongo.db.classrooms.find_one({"_id": ObjectId(classroom_id)})
        if not classroom or 'student_list' not in classroom:
            logger.warning(f"Classroom '{classroom_id}' is missing or has no students.")
            continue

        logger.debug(f"Classroom '{classroom_id}' has {len(classroom['student_list'])} students.")

        for user_id in classroom['student_list']:
            notification = {
                "user_id": ObjectId(user_id),
                "message": message,
                "is_read": False,
                "priority": priority,
                "timestamp": datetime.now()
            }
            logger.debug(f"Inserting notification for user {user_id}: {message}")
            mongo.db.notifications.insert_one(notification)

    logger.debug("Finished sending assignment notifications.")



if __name__ == '__main__':
    logger.info("Starting the Flask app...")
    # Initialize APScheduler to schedule tasks in the background
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=send_assignment_notification, trigger="cron", hour=0, minute=0)  
    logger.debug("Scheduler job for sending notifications has been added.")
    scheduler.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
