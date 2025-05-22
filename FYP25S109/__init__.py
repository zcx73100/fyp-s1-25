import os
import logging
from flask import Flask, session, url_for
from flask_pymongo import PyMongo
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from pymongo import MongoClient
import atexit

# Global PyMongo “factory”
mongo = PyMongo()

def create_app():
    # Create Flask instance
    app = Flask(__name__)

    # Basic logging setup
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Flask config
    app.config['SECRET_KEY'] = 'fyp25'
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # MongoDB URI from env
    uri = os.environ.get("MONGODB_URI")
    if uri:
        app.config["MONGO_URI"] = uri
        logger.info("MONGODB_URI found, initializing PyMongo")
        mongo.init_app(app)
    else:
        logger.error("MONGODB_URI is missing! PyMongo will not be initialized.")

    # Simple health check
    @app.route("/ping")
    def ping():
        return "pong"

    # Register your boundary blueprint
    from .boundary import boundary
    app.register_blueprint(boundary, url_prefix="/")

    # Register your chatbot blueprint
    from .chatbot import chatbot
    app.register_blueprint(chatbot, url_prefix="/")

    # Inject user_info + profile_pic_url into all templates
    @app.context_processor
    def inject_user_info():
        user_info = None
        profile_pic_url = None

        if "username" in session:
            user_info = mongo.db.useraccount.find_one({"username": session["username"]})
            if user_info and user_info.get("profile_pic"):
                profile_pic_url = url_for(
                    "boundary.get_profile_pic",
                    file_id=user_info["profile_pic"]
                )

        return dict(user_info=user_info, profile_pic_url=profile_pic_url)

    # --------------------------
    # APScheduler: Auto-delete temp videos
    # --------------------------
    def delete_old_temp_videos():
        now = datetime.utcnow()
        chatbot_cutoff = now - timedelta(minutes=5)
        general_cutoff = now - timedelta(hours=24)

        client = MongoClient(app.config.get("MONGO_URI"))
        db = client.get_default_database()

        db.tempvideo.delete_many({
            "source": "chatbot",
            "created_at": {"$lt": chatbot_cutoff}
        })

        db.tempvideo.delete_many({
            "source": {"$ne": "chatbot"},
            "is_published": False,
            "created_at": {"$lt": general_cutoff}
        })

        app.logger.info("[Scheduler] Temp videos cleaned up")

    # Start the scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(delete_old_temp_videos, trigger='interval', minutes=5)
    scheduler.start()

    # Cleanly shut down scheduler on app exit
    atexit.register(lambda: scheduler.shutdown())

    return app
