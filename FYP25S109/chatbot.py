from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
import requests
from datetime import datetime
from flask_pymongo import PyMongo
import os
from . import mongo
from bson import ObjectId

# Configuration for the chatbot API
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "deepseek/deepseek-chat-v3-0324:free"

# Define the Blueprint for the chatbot routes
chatbot = Blueprint('chatbot', __name__)

# Boundary Layer (routes)
class ChatbotBoundary:
    @chatbot.route('/chatbot')
    def chatbot_page():
        if 'username' not in session:
            return redirect(url_for('boundary.login'))  
        
        chatbot_chats = mongo.db.chatbot_chats.find({"username": session['username']}).sort("timestamp", -1).limit(10)
        user = mongo.db.useraccount.find_one({"username": session['username']},{})

        return render_template('chatbot_page.html',chatbot_chats=chatbot_chats,user=user)

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

        success = ChatbotController.delete_chat(chat_id, session['username'])

        if success:
            return jsonify({"success": True})
        return jsonify({"error": "Failed to delete chat"}), 500
    
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