from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, current_app
import requests
from datetime import datetime
from flask_pymongo import PyMongo
import os
from . import mongo
from bson import ObjectId
from .controller import GenerateVideoController
from bson.errors import InvalidId


# Configuration for the chatbot API
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "deepseek/deepseek-chat-v3-0324:free"

# Define the Blueprint for the chatbot routes
chatbot = Blueprint('chatbot', __name__)

# Boundary Layer (routes)
class ChatbotBoundary:
    @chatbot.route("/chatbot")
    def chatbot_page():
        username = session.get("username")
        if not username:
            return redirect("/login")

        user_info = mongo.db.useraccount.find_one({"username": username})
        assistant_avatar_id = ""
        assistant_tts_voice = "female_en"  # default value in case missing

        if user_info and "assistant" in user_info:
            avatar_id = user_info["assistant"].get("avatar_id")
            if avatar_id:
                assistant_avatar_id = str(avatar_id)
            assistant_tts_voice = user_info["assistant"].get("tts_voice", "female_en")

        chatbot_chats = list(mongo.db.chatbot_chats.find({"username": username}))

        return render_template(
            "chatbot_page.html",
            user_info=user_info,
            chatbot_chats=chatbot_chats,
            assistant_avatar_id=assistant_avatar_id,
            assistant_tts_voice=assistant_tts_voice
        )
    
    @chatbot.route("/chatbot/process", methods=["POST"])
    def chatbot_process():
        username = session.get("username")
        if not username:
            return redirect(url_for("boundary.login"))

        text = request.form.get("text", "").strip()
        lang = request.form.get("lang", "en")
        gender = request.form.get("gender", "female")

        if not text:
            return "❌ No text provided", 400

        # ✅ Generate voice
        controller = GenerateVideoController()
        audio_id = controller.generate_voice(text, lang, gender)
        if not audio_id:
            return "❌ Voice generation failed", 500

        # ✅ Redirect to SadTalker-compatible route with audio_id
        return redirect(url_for("boundary.generate_video_from_session_post", audio_id=audio_id, text=text))


    @chatbot.route('/select_avatar/assign', methods=['POST'])
    def assign_avatar():
        username = session.get("username")
        if not username:
            return redirect(url_for("chatbot.chatbot_page"))

        avatar_id = request.form.get("avatar_id")
        tts_voice = request.form.get("tts_voice")

        if not avatar_id or not tts_voice:
            return "Missing avatar or TTS voice", 400

        try:
            avatar_obj_id = ObjectId(avatar_id)
        except InvalidId:
            print("[Error] Invalid avatar_id format:", avatar_id)
            return "Invalid avatar ID", 400

        # Save to user account
        try:
            mongo.db.useraccount.update_one(
                {"username": username},
                {"$set": {
                    "assistant": {
                        "avatar_id": avatar_obj_id,
                        "tts_voice": tts_voice
                    }
                }}
            )
        except Exception as e:
            print("[Error] Failed to update user account:", e)
            return "Database update failed", 500

        return redirect(url_for("chatbot.chatbot_page"))


    @chatbot.route('/select_avatar')
    def select_avatar():
        admin_users = mongo.db.useraccount.find({"role": "Admin"}, {"username": 1})
        admin_usernames = [u["username"] for u in admin_users]

        # Step 2: Get avatars uploaded by those admin users
        avatars = list(mongo.db.avatar.find({"username": {"$in": admin_usernames}}))        
        tts_options = ["male_en", "female_en", "neutral_en",
        "male_es", "female_es",
        "female_fr", "neutral_fr",
        "neutral_de",
        "neutral_it",
        "neutral_ja",
        "neutral_ko",
        "neutral_id"]  # adjust based on your supported voices
        
        return render_template("select_avatar.html", avatars=avatars, tts_options=tts_options)

    @chatbot.route('/api/chat', methods=['POST'])
    def handle_chat():
        # Check if user is authenticated
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401

        user_message = request.json.get("message") if request.is_json else request.form.get("message")
        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        # Controller Layer
        reply = ChatbotController.process_chat(session['username'], user_message)
        return jsonify({"reply": reply})
    
    @chatbot.route('/api/chat/new', methods=['POST'])
    def new_chat():
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401

        title = request.json.get("title", "New Chat")
        chat_id = ChatbotController.create_chat(session['username'], title)

        if chat_id:
            return jsonify({"chat_id": chat_id, "title": title})
        return jsonify({"error": "Failed to create chat"}), 500

    
    @chatbot.route('/api/chat/<chat_id>/update_title', methods=['POST'])
    def update_title(chat_id):
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401

        new_title = request.json.get("title")
        if not new_title:
            return jsonify({"error": "Title is required"}), 400

        success = ChatbotController.update_chat_title(chat_id, session['username'], new_title)

        if success:
            return jsonify({"success": True})
        return jsonify({"error": "Failed to update title"}), 500
    
    @chatbot.route('/api/chat/<chat_id>/delete', methods=['DELETE'])
    def delete_chat(chat_id):
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401

        try:
       # validate chat_id format
            oid = ObjectId(chat_id)
        except InvalidId:
            return jsonify({"error": "Invalid chat ID"}), 400

        try:
            deleted = ChatbotController.delete_chat(str(oid), session['username'])
            if deleted:
                return "", 204
            # nothing deleted → not found or no permission
            return jsonify({"error": "Chat not found or access denied"}), 404
        except Exception as e:
            current_app.logger.exception(f"Error deleting chat {chat_id}")
            return jsonify({"error": "Server error during delete"}), 500
    
    @chatbot.route('/api/chat/search', methods=['GET'])
    def search_chats():
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401

        keyword = request.args.get("keyword")
        if not keyword:
            return jsonify({"error": "Keyword is required"}), 400

        chats = ChatbotController.search_chats(session['username'], keyword)

        return jsonify({"chats": chats})
    
    @chatbot.route('/api/chat/<chat_id>/messages', methods=['GET'])
    def get_chat_messages(chat_id):
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        
        try:
            chat = mongo.db.chatbot_chats.find_one(
                {"_id": ObjectId(chat_id), "username": session['username']},
                {"messages": 1}
            )
            
            if not chat:
                return jsonify({"error": "Chat not found"}), 404
                
            return jsonify({"messages": chat.get("messages", [])})
        except Exception as e:
            print(f"[Error] {e}")
            return jsonify({"error": "Server error"}), 500

    @chatbot.route('/api/chat/<chat_id>/send', methods=['POST'])
    def send_message(chat_id):
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        
        message = request.json.get("message")
        if not message:
            return jsonify({"error": "Message is required"}), 400
        
        try:
            # Get chatbot response
            response = ChatAPI.get_chat_response(message)
            
            # Update chat with new messages
            result = mongo.db.chatbot_chats.update_one(
                {"_id": ObjectId(chat_id), "username": session['username']},
                {
                    "$push": {
                        "messages": {
                            "user": message,
                            "bot": response,
                            "timestamp": datetime.utcnow()
                        }
                    },
                    "$set": {
                        "last_updated": datetime.utcnow(),
                        "description": message[:50]  # Update description with first 50 chars of last message
                    }
                }
            )
            
            if result.modified_count == 0:
                return jsonify({"error": "Chat not found or not updated"}), 404
                
            return jsonify({
                "reply": response,
                "chat_id": chat_id
            })
        except Exception as e:
            print(f"[Error] {e}")
            return jsonify({"error": "Server error"}), 500


# Control Layer (business logic)
class ChatbotController:
    @staticmethod
    def process_chat(username, message):
        # Call the service to get the API response
        response = ChatAPI.get_chat_response(message)
        # Save the message and response to the database (Entity Layer)
        Chat.save_message(username, message, response)
        return response
    
    @staticmethod
    def create_chat(username, title="New Chat"):
        return Chat.create_chat(username, title)

    @staticmethod
    def update_chat_title(chat_id, username, new_title):
        return Chat.update_chat_title(chat_id, username, new_title)

    @staticmethod
    def delete_chat(chat_id, username):
        return Chat.delete_chat(chat_id, username)

    @staticmethod
    def search_chats(username, keyword):
        return Chat.search_chats(username, keyword)
    

# Service Layer (API Communication)
class ChatAPI:
    @staticmethod
    def get_chat_response(user_message):
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": """
You are EduMate, the built-in virtual assistant for an AI-powered Learning Management System (LMS).
This LMS is designed to enhance education through interactive face animation technology.
Your job is to guide users—students and teachers—through the platform and help them make the most of its features.

The LMS offers:
- Animated AI avatars to make learning more engaging.
- Teachers can create and deliver lessons through animated characters.
- Students can access tutorials, take quizzes, and track their learning progress.
- Built-in discussion boards for collaborative learning.
- Face animation tech that mimics human expressions for more immersive online learning.
                 
For Students:
- Help them navigate the LMS, find resources, and understand features.
- Provide tips on how to use the animated avatars effectively.
- Answer questions about assignments, deadlines, and course materials.
- Remind them of they still need to study well and not rely solely on you.

When responding:
- Speak like a friendly, clear, and helpful digital assistant.
- Offer real guidance or suggestions like you would in a live LMS dashboard.
- If you don’t know the answer, recommend the user contacts support or checks the help section.
- Avoid technical jargon or complex terms; keep it simple and user-friendly.
- Be concise and to the point, but also friendly and engaging.
- Use a conversational tone, as if you were chatting with a friend.
- Give users warning if they are asking for something inappropriate or against the LMS policy.
- Avoid discussing sensitive topics like politics, religion, or personal opinions.
- Warn users if they are speaking in deregatory or inappropriate language.
- Do not provide medical, legal, or financial advice.
- Do not ask for personal information like passwords or credit card numbers.
- Do not engage in any form of harassment, bullying, or hate speech.
- Do not promote or endorse any illegal activities or substances.
- Do not provide any explicit or adult content.
- Do not impersonate any real person or entity.
- Do not make any false or misleading claims about the LMS or its features.
- Do not provide any information that could harm the LMS or its users.
- Do not provide any information that could violate the privacy or security of the LMS or its users.
- Do not provide any information that could violate the terms of service or policies of the LMS or its partners.
- Do not provide any information that could violate the laws or regulations of the country or region where the LMS operates.
- Do not include emojis, bold text, italics, or any other formatting in your responses.

Stay professional, informative, and approachable — like a feature users would love to interact with every day.
"""},
                {"role": "user", "content": user_message}
            ]
        }

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[ChatAPI Error] {e}")
            return "Sorry, I’m having trouble responding right now. Please try again later."

# Entity Layer (Database interaction)
class Chat:
    # Save a message to the chatbot's message collection
    @staticmethod
    def save_message(username, message, response):
        try:
            mongo.db.chatbot_chat.insert_one({
                'username': username,
                'message': message,
                'response': response,
                'timestamp': datetime.utcnow()
            })
        except Exception as e:
            print(f"[Mongo Error] {e}")

    # Create a new chat in the chatbot_chats collection
    @staticmethod
    def create_chat(username, title="New Chat"):
        try:
            chat_id = mongo.db.chatbot_chats.insert_one({
                "username": username,
                "title": title,
                "description": "",
                "messages": [],
                "timestamp": datetime.utcnow()
            }).inserted_id
            return str(chat_id)  # Return the chat ID as a string
        except Exception as e:
            print(f"[Mongo Error] {e}")
            return None

    # Update the title of an existing chat
    @staticmethod
    def update_chat_title(chat_id, username, new_title):
        try:
            result = mongo.db.chatbot_chats.update_one(
                {"_id": ObjectId(chat_id), "username": username},
                {"$set": {"title": new_title}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"[Mongo Error] {e}")
            return False

    # Delete an existing chat
    @staticmethod
    def delete_chat(chat_id, username):
        try:
            result = mongo.db.chatbot_chats.delete_one({"_id": ObjectId(chat_id), "username": username})
            return result.deleted_count > 0
        except Exception as e:
            print(f"[Mongo Error] {e}")
            return False

    # Search for chats by title for a given user
    @staticmethod
    def search_chats(username, keyword):
        try:
            chats = list(mongo.db.chatbot_chats.find({
                "username": username,
                "title": {"$regex": keyword, "$options": "i"}
            }).sort("timestamp", -1))

            for chat in chats:
                chat['_id'] = str(chat['_id'])  # convert ObjectId to string for JSON

            return chats
        except Exception as e:
            print(f"[Mongo Error] {e}")
            return []
