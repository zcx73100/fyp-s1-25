# FYP25S109/__init__.py

import os
import logging
from flask import Flask, session, url_for
from flask_pymongo import PyMongo

# global PyMongo “factory”
mongo = PyMongo()

def create_app():
    # Create Flask instance
    app = Flask(__name__)

    # Basic logging setup (can be tweaked in your wsgi or main)
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Flask config
    app.config['SECRET_KEY'] = 'fyp25'
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # MongoDB URI from env
    uri = os.environ.get("MONGODB_URI")
    if uri:
        app.config["MONGO_URI"] = uri
        logger.info(f"MONGODB_URI found, initializing PyMongo")
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

    return app
