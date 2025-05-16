from flask import Flask
from flask import session, url_for

from flask_pymongo import PyMongo
import sys
import os
mongo = PyMongo()


def create_app():
    app = Flask(__name__)

    # Flask Configuration
    app.config['SECRET_KEY'] = 'fyp25'
    app.config["MONGO_URI"] = "mongodb://localhost:27017/fyps12509"
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # Initialize MongoDB
    mongo.init_app(app)

    # Register Blueprints
    from .boundary import boundary
    app.register_blueprint(boundary, url_prefix='/')

    # ✅ Register Chatbot Blueprint
    from .chatbot import chatbot
    app.register_blueprint(chatbot, url_prefix='/')

    @app.context_processor
    def inject_user_info():
        user_info = None
        profile_pic_url = None

        if "username" in session:
            user_info = mongo.db.useraccount.find_one({"username": session["username"]})
        if user_info and user_info.get("profile_pic"):
            profile_pic_url = url_for("boundary.get_profile_pic", file_id=user_info["profile_pic"])

        return dict(user_info=user_info, profile_pic_url=profile_pic_url)
    
    return app
