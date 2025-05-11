from flask import session
from . import mongo
import os
import logging
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
import io, requests
from pymongo.errors import DuplicateKeyError
from io import BytesIO
from bson import ObjectId
import pyttsx3
from gradio_client import Client
from flask import flash, session, redirect, url_for
import wave
import subprocess
import shutil
from PIL import Image
import base64
import mimetypes
from gtts import gTTS
from gridfs import GridFS


def get_fs():
    return GridFS(mongo.db)

import uuid
import tempfile
import time
from gridfs import GridFS

def get_fs():
    return GridFS(mongo.db)

# Separate Upload Folders
UPLOAD_FOLDER_VIDEO = 'FYP25S109/static/uploads/videos/'
UPLOAD_FOLDER_AVATAR = 'FYP25S109/static/uploads/avatar/'
GENERATE_FOLDER_AUDIOS = 'FYP25S109/static/generated_audios'
GENERATE_FOLDER_VIDEOS = 'FYP25S109/static/generated_videos'

# Allowed Extensions
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

# Ensure Directories Exist
os.makedirs(UPLOAD_FOLDER_VIDEO, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_AVATAR, exist_ok=True)
os.makedirs(GENERATE_FOLDER_AUDIOS, exist_ok=True)
os.makedirs(GENERATE_FOLDER_VIDEOS, exist_ok=True)


def setup_indexes():
    #This index will prevent users to create another account with a username taken by other user 
    mongo.db.useraccount.create_index("username", unique=True)
    print("Unique index on 'username' field created.")

class UserAccount:
    def __init__(self, username, password, name, surname, email, date_of_birth,
             role, status='active', profile_pic=None):
        self.username = username
        self.password = password
        self.name = name
        self.surname = surname
        self.email = email
        self.date_of_birth = date_of_birth
        self.role = role
        self.status = status
        self.profile_pic = profile_pic

    def create_user_acc(self):
        try:
            # 1. Check for duplicate username
            if mongo.db.useraccount.find_one({"username": self.username}):
                logging.warning(f"Username '{self.username}' already exists.")
                return False

            # 2. Hash password
            hashed_password = generate_password_hash(self.password)

            # 3. Handle profile_pic (can be ObjectId or file object)
            profile_pic_id = None

            if isinstance(self.profile_pic, ObjectId):
                profile_pic_id = self.profile_pic

            elif self.profile_pic and hasattr(self.profile_pic, 'content_type'):
                fs = GridFS(mongo.db)
                profile_pic_id = get_fs().put(
                    self.profile_pic,
                    filename=f"{self.username}_profile_pic",
                    content_type=self.profile_pic.content_type
                )

            # 4. Prepare user document
            user_doc = {
                "username": self.username,
                "password": hashed_password,
                "name": self.name,
                "surname": self.surname,
                "email": self.email,
                "date_of_birth": self.date_of_birth,
                "role": self.role,
                "status": self.status,
                "first_time_login": True,
                "profile_pic": profile_pic_id,
                "assistant": ""
            }

            # 5. Insert into MongoDB
            mongo.db.useraccount.insert_one(user_doc)
            logging.info(f"User '{self.username}' created successfully.")
            return True

        except Exception as e:
            logging.error(f"Error creating user: {e}")
            print(f"⚠️ Account creation error: {e}")
            return False


    # All static methods remain unchanged:
    @staticmethod
    def login(username, password):
        try:
            user = mongo.db.useraccount.find_one({"username": username})
            if user and check_password_hash(user["password"], password):
                return user["username"], user["role"]
            return None
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return None

    @staticmethod
    def update_account_detail(username, updated_data):
        try:
            if not updated_data:
                logging.warning(f"No update data provided for {username}.")
                return False

            update_result = mongo.db.useraccount.update_one({"username": username}, {"$set": updated_data})
            if update_result.modified_count > 0:
                logging.debug(f"User Update: Username={username} | Updated Fields={updated_data}")
                return True
            logging.warning(f"No changes made for {username}.")
            return False
        except Exception as e:
            logging.error(f"Failed to update user info: {str(e)}")
            return False

    @staticmethod
    def find_by_username(username):
        try:
            logging.debug(f"Finding user by username: {username}")
            return mongo.db.useraccount.find_one({"username": username},{})
        except Exception as e:
            logging.error(f"Failed to find user by username: {str(e)}")
            return None

    @staticmethod
    def search_account(query):
        try:
            return list(mongo.db.useraccount.find({
                "$or": [
                    {"username": {"$regex": query, "$options": "i"}},
                    {"email": {"$regex": query, "$options": "i"}}
                ]
            }, {"_id": 0}))
        except Exception as e:
            logging.error(f"Error searching users: {e}")
            return []

    @staticmethod
    def suspend_user(username):
        try:
            result = mongo.db.useraccount.update_one(
                {"username": username},
                {"$set": {"status": "suspended"}}
            )
            if result.modified_count == 0:
                logging.warning("No user found to suspend.")
                return False
            logging.info(f"User {username} suspended successfully.")
            return True
        except Exception as e:
            logging.error(f"Error suspending user: {e}")
            return False

    @staticmethod
    def delete_user(username):
        try:
            result = mongo.db.useraccount.update_one(
                {"username": username},
                {"$set": {"status": "deleted"}}
            )
            if result.modified_count == 0:
                logging.warning("No user found to delete.")
                return False
            logging.info(f"User {username} marked as deleted.")
            return True
        except Exception as e:
            logging.error(f"Error deleting user: {e}")
            return False

class TutorialVideo:
    def __init__(self, title=None, video_file=None, username=None, description=None):
        self.title = title
        self.video_file = video_file
        self.username = username
        self.description = description

    def save_video(self):
        try:
            if not self.video_file or '.' not in self.video_file.filename:
                raise ValueError("Invalid or missing video file.")

            filename = secure_filename(self.video_file.filename)
            file_ext = filename.rsplit('.', 1)[1].lower()

            if file_ext not in ALLOWED_VIDEO_EXTENSIONS:
                raise ValueError("Invalid video format.")

            # Save video to GridFS
            file_id = get_fs().put(self.video_file, filename=filename, content_type=self.video_file.content_type)

            # Save metadata
            mongo.db.tutorialvideo.insert_one({
                'title': self.title,
                'video_name': filename,
                'file_id': file_id,
                'username': self.username,
                'upload_date': datetime.now(),
                'description': self.description
            })

            return {"success": True, "message": "Video uploaded to database successfully."}

        except Exception as e:
            logging.error(f"Error saving video: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def delete_video(video_id):
        try:
            video = mongo.db.tutorialvideo.find_one({"_id": ObjectId(video_id)})
            if video:
                # Delete from GridFS
                get_fs().delete(video['file_id'])
                # Delete metadata
                mongo.db.tutorialvideo.delete_one({"_id": ObjectId(video_id)})
                return {"success": True, "message": "Video deleted successfully."}
            return {"success": False, "message": "Video not found."}

        except Exception as e:
            logging.error(f"Error deleting video: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def search_video(search_query):
        try:
            videos = mongo.db.tutorialvideo.find({
                "title": {"$regex": search_query, "$options": "i"}
            })
            return list(videos)
        except Exception as e:
            logging.error(f"Failed to search videos: {str(e)}")
            return []


class GenerateVideoEntity:
    def __init__(self, text, avatar_path=None, audio_path=None):
        self.text = text
        self.avatar_path = avatar_path
        self.audio_path = audio_path

    @staticmethod
    def save_audio_to_gridfs(audio_bytes, filename="audio.mp3", content_type="audio/mpeg"):
        audio_io = BytesIO(audio_bytes)
        file_id = get_fs().put(audio_io, filename=filename, content_type=content_type)
        return file_id
    
    def generate_voice(self, lang, gender):
        try:
            if not self.text.strip():
                raise ValueError("Text input is empty.")

            # Enhanced voice configuration
            voice_config = {
                "en": {
                    "male": {"tld": "com", "lang": "en", "slow": False, "gender_enforced": True},
                    "female": {"tld": "com.au", "lang": "en", "slow": False, "gender_enforced": True},
                    "neutral": {"tld": "co.uk", "lang": "en", "slow": False, "gender_enforced": False}
                },
                "es": {
                    "male": {"tld": "com.mx", "lang": "es", "slow": False, "gender_enforced": True},
                    "female": {"tld": "es", "lang": "es", "slow": False, "gender_enforced": True}
                },
                "fr": {
                    "female": {"tld": "fr", "lang": "fr", "slow": False, "gender_enforced": True},
                    "neutral": {"tld": "fr", "lang": "fr", "slow": False, "gender_enforced": False}
                },
                "de": {
                    "neutral": {"tld": "de", "lang": "de", "slow": False, "gender_enforced": False}
                },
                "it": {
                    "neutral": {"tld": "it", "lang": "it", "slow": False, "gender_enforced": False}
                },
                "ja": {
                    "neutral": {"tld": "co.jp", "lang": "ja", "slow": False, "gender_enforced": False}
                },
                "ko": {
                    "neutral": {"tld": "co.kr", "lang": "ko", "slow": False, "gender_enforced": False}
                },
                "id": {
                    "neutral": {"tld": "co.id", "lang": "id", "slow": False, "gender_enforced": False}
                }
            }

            # Get settings for requested language and gender
            lang_config = voice_config.get(lang)
            gender_config = lang_config.get(gender)
            
            mp3_buffer = BytesIO()
            tts = gTTS(
                text=self.text,
                lang=lang,
                tld=gender_config["tld"],
                slow=gender_config["slow"]
            )
            tts.write_to_fp(mp3_buffer)
            mp3_buffer.seek(0)

            audio_id = get_fs().put(
                mp3_buffer,
                filename=f"voice_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.mp3",
                content_type="audio/mpeg"
            )

            voice_data = {
                "audio_id": audio_id,
                "text": self.text,
                "lang": lang,
                "gender": gender,
                "created_at": datetime.now(),
                "status": "generated",
                "username": session.get("username")
            }

            mongo.db.voice_records.insert_one(voice_data)
            return audio_id

        except Exception as e:
            print(f"❌ Error generating voice: {e}")
            return None
    
    def save_recording_to_gridfs(self, audio_bytes, filename="audio.wav"):
        try:
            audio_io = BytesIO(audio_bytes)
            file_id = get_fs().put(audio_io, filename=filename, content_type="audio/wav")
            return file_id
        except Exception as e:
            print(f"❌ Error saving recording to GridFS: {e}")
            return None

    def generate_video(self, avatar_id, audio_id,video_title="Generated Video"):
        try:
            SADTALKER_API = "http://127.0.0.1:7860/generate_video_fastapi"

            avatar_file = get_fs().get(ObjectId(avatar_id))
            audio_file = get_fs().get(ObjectId(audio_id))

            avatar_bytes = BytesIO(avatar_file.read())
            audio_bytes = BytesIO(audio_file.read())

            files = {
                "image_file": ("avatar.png", avatar_bytes, "image/png"),
                "audio_file": ("audio.wav", audio_bytes, "audio/wav")
            }
            data = {
                "preprocess_type": "crop",
                "is_still_mode": "false",
                "enhancer": "false",
                "batch_size": "2",
                "size_of_image": "256",
                "pose_style": "0"
            }

            response = requests.post(SADTALKER_API, files=files, data=data)

            if response.status_code != 200:
                print("❌ SadTalker failed:", response.text)
                return None

            result = response.json()
            video_path = result.get("video_path")
            safe_video_path = os.path.normpath(video_path.strip())

            for i in range(5):
                if os.path.exists(safe_video_path):
                    break
                print(f"[WAIT] Video not found yet, retrying ({i+1}/5)...")
                time.sleep(0.2)
            else:
                print(f"❌ ERROR: video does not exist at {safe_video_path}")
                return None

            with open(safe_video_path, "rb") as vf:
                video_bytes = BytesIO(vf.read())

            video_id = get_fs().put(
                video_bytes,
                filename=os.path.basename(safe_video_path),
                content_type="video/mp4",
                metadata={"username": session.get("username")}
            )

            mongo.db.generated_videos.insert_one({
                "video_id": video_id,
                "avatar_id": ObjectId(avatar_id),
                "audio_id": ObjectId(audio_id),
                "title": video_title,  # Store the title
                "created_at": datetime.now(),
                "status": "generated",
                "username": session.get("username"),
                "is_published": False
            })

            # Remove the generated video file if needed
            os.remove(safe_video_path)

            return str(video_id)

        except Exception as e:
            print(f"❌ Error during video generation: {e}")
            return None

    @staticmethod    
    def get_videos(username):
        try:
            videos = mongo.db.generated_videos.find({"username": username}).sort("created_at", -1)
            video_list = []
            for video in videos:
                video_list.append({
                    "_id": video["_id"],
                    "video_id": str(video["video_id"]),
                    "title": video.get("title", "Untitled"),  # Include title
                    "created_at": video["created_at"],
                    "status": video["status"]
                })
            return video_list
        except Exception as e:
            print(f"❌ Error fetching videos: {e}")
            return []




    
class Avatar:
    def __init__(self, image_file, avatarname=None, username=None, upload_date=None):
        self.image_file = image_file
        self.avatarname = avatarname
        self.username = username
        self.upload_date = upload_date

    def allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

    def save_image(self):
        try:
            if not self.image_file:
                raise ValueError("No file selected for upload.")

            filename = secure_filename(self.image_file.filename)
            if not self.allowed_file(filename):
                raise ValueError("Invalid image format.")

            # Step 1: Load image
            image_binary = self.image_file.read()
            image = Image.open(io.BytesIO(image_binary)).convert("RGBA")

            # Step 2: Pad image to square
            width, height = image.size
            if width != height:
                delta = abs(width - height)
                padding = (0, 0, 0, 0)
                if width > height:
                    padding = (0, delta // 2, 0, delta - delta // 2)
                else:
                    padding = (delta // 2, 0, delta - delta // 2, 0)
                image = ImageOps.expand(image, padding, fill=(0, 0, 0, 0))

            # Step 3: Resize to 512x512
            try:
                resample = Image.Resampling.BICUBIC
            except AttributeError:
                resample = Image.BICUBIC
            image = image.resize((512, 512), resample)

            # Step 4: Save image to buffer (no rembg)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)
            image_data = buffer.getvalue()

            # Step 5: Save to GridFS
            gridfs_id = get_fs().put(image_data, filename=filename, content_type="image/png")

            # Step 6: Store as base64 preview
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # Step 7: Insert into DB
            avatar_record = {
                'avatarname': self.avatarname,
                'username': self.username,
                'image_data': image_base64,
                'file_id': gridfs_id,
                'upload_date': datetime.utcnow()
            }

            result = mongo.db.avatar.insert_one(avatar_record)
            logging.info(f"[Avatar] Inserted for user '{self.username}', ID: {result.inserted_id}")

            return {"success": True, "message": "Avatar uploaded successfully."}

        except Exception as e:
            logging.error(f"[Avatar Upload Error] {str(e)}")
            return {"success": False, "message": f"Failed to upload avatar: {str(e)}"}


    def add_avatar(self, avatarname, username, image_data, file_path):
        try:
            mongo.db.avatar.insert_one({
                'avatarname': avatarname,
                'username': username,
                'image_data': image_data,  # Base64 for previews or API
                'file_path': file_path,    # Relative file path for video generation
                'upload_date': datetime.now()
            })
            return True
        except Exception as e:
            logging.error(f"Error adding avatar to database: {str(e)}")
            return False

    @staticmethod
    def search_avatar(search_query):
        try:
            avatars = mongo.db.avatar.find({
                "$or": [
                    {"avatarname": {"$regex": search_query, "$options": "i"}},
                    {"username": {"$regex": search_query, "$options": "i"}}
                ]
            })
            return list(avatars)
        except Exception as e:
            logging.error(f"Failed to search avatars: {str(e)}")
            return []

    @staticmethod
    def find_by_id(avatar_id):
        try:
            avatar = mongo.db.avatar.find_one({"_id": ObjectId(avatar_id)})
            return avatar
        except Exception as e:
            logging.error(f"Failed to find avatar by ID: {str(e)}")
            return None

    @staticmethod
    def delete_avatar(avatar_id):
        try:
            mongo.db.avatar.delete_one({"_id": ObjectId(avatar_id)})
            return True
        except Exception as e:
            logging.error(f"Error deleting avatar: {str(e)}")
            return False


class Classroom:
    def __init__(self, classroom_name=None, teacher=None, student_list=None, capacity=None, description=None):
        self.classroom_name = classroom_name
        self.teacher = teacher
        self.description = description
        self.student_list = student_list or []
        self.capacity = capacity
    
    @staticmethod
    def create_classroom(classroom_name, teacher, classroom_description, classroom_capacity,student_list=[]):
        """ Inserts classroom into the database """
        try:
            result = mongo.db.classroom.insert_one({
                'classroom_name': classroom_name,
                'teacher': teacher,
                'student_list': student_list,
                'capacity': int(classroom_capacity),
                'description': classroom_description,
                'upload_date': datetime.now()
            })
            if result.inserted_id:
                return {"success": True, "message": f"Classroom '{classroom_name}' added successfully."}
        except Exception as e:
            logging.error(f"Error creating classroom: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def search_classroom(search_query):
        """ Searches for classrooms matching the query """
        try:
            classrooms = mongo.db.classroom.find({
                "classroom_name": {"$regex": search_query, "$options": "i"}
            })
            return list(classrooms)
        except Exception as e:
            logging.error(f"Failed to search classrooms: {str(e)}")
            return []

    @staticmethod
    def delete_classroom(classroom_id):
        """ Deletes a classroom by ID """
        try:
            classroom = mongo.db.classroom.find_one({"_id": ObjectId(classroom_id)})
            if classroom:
                mongo.db.classroom.delete_one({"_id": ObjectId(classroom_id)})
                return True
        except Exception as e:
            logging.error(f"Error deleting classroom: {str(e)}")
            return False
    @staticmethod
    def update_classroom(classroom_id, updated_data):
        """ Updates a classroom by _id """
        try:
            result = mongo.db.classroom.update_one(
                {"_id": ObjectId(classroom_id)},  # Convert string ID to ObjectId
                {"$set": updated_data}
            )
            if result.modified_count > 0:
                return {"success": True, "message": "Classroom updated successfully."}
            else:
                return {"success": False, "message": "No changes made or classroom not found."}
        except Exception as e:
            logging.error(f"Error updating classroom: {str(e)}")
            return {"success": False, "message": str(e)}
    
    @staticmethod
    def find_by_teacher(teacher):
        """ Finds classrooms by teacher """
        try:
            classrooms = mongo.db.classroom.find({"teacher": teacher})
            return list(classrooms)
        except Exception as e:
            logging.error(f"Failed to find classrooms by teacher: {str(e)}")
            return []
    
    @staticmethod
    def find_by_student(student):
        """ Finds classrooms by student """
        try:
            student = mongo.db.useraccount.find({"username": student, "role": "Student"})
            return student
        except Exception as e:
            logging.error(f"Failed to find classrooms by student: {str(e)}")
            return []
    
    @staticmethod
    def enroll_student(classroom_id, student_username):
        """Enrolls a student into a classroom, avoiding duplicates."""
        try:
            # Check if the student exists and has the "Student" role
            student_info = mongo.db.useraccount.find_one({"username": student_username, "role": "Student"})
            if not student_info:
                return {"success": False, "message": f"Student '{student_username}' not found or not a student."}

            # Check if the classroom exists
            classroom = mongo.db.classroom.find_one({"_id": ObjectId(classroom_id)})
            if not classroom:
                return {"success": False, "message": "Classroom not found."}

            # Check for duplicate enrollment
            if student_username in classroom.get("student_list", []):
                return {"success": False, "message": "Student is already enrolled in this classroom."}

            # Enroll the student using $addToSet to avoid duplicates
            result = mongo.db.classroom.update_one(
                {"_id": ObjectId(classroom_id)},
                {"$addToSet": {"student_list": student_username}}
            )
            if result.modified_count > 0:
                return {"success": True, "message": f"Successfully enrolled {student_username}."}
            else:
                return {"success": False, "message": "Failed to enroll the student."}
        except Exception as e:
            logging.error(f"Error enrolling student: {str(e)}")
            return {"success": False, "message": str(e)}
    
    @staticmethod
    def remove_student(classroom_id, student_username):
        """Removes a student from a classroom."""
        try:
            result = mongo.db.classroom.update_one(
                {"_id": ObjectId(classroom_id)},
                {"$pull": {"student_list": student_username}}
            )
            if result.modified_count > 0:
                return {"success": True, "message": f"Successfully removed {student_username}."}
            else:
                return {"success": False, "message": "Failed to remove the student."}
        except Exception as e:
            logging.error(f"Error removing student: {str(e)}")
            return {"success": False, "message": str(e)}

    
    @staticmethod
    def find_by_name(classroom_name):
        """Finds a classroom by name and returns its details."""
        try:
            return mongo.db.classroom.find_one({"classroom_name": classroom_name})
        except Exception as e:
            logging.error(f"Error finding classroom by name: {str(e)}")
            return None
    @staticmethod
    def suspend_student(username):
        """Suspend a student by updating their status to 'suspended'."""
        try:
            result = mongo.db.useraccount.update_one(
                {"username": username},
                {"$set": {"status": "suspended"}}
            )
            if result.modified_count > 0:
                logging.info(f"User {username} suspended successfully.")
                return True
            logging.warning(f"User {username} not found or already suspended.")
            return False
        except Exception as e:
            logging.error(f"Error suspending user: {e}")
            return False
    def unsuspend_student(username):
        """Unsuspend a student by updating their status to 'active'."""
        try:
            result = mongo.db.useraccount.update_one(
                {"username": username},
                {"$set": {"status": "active"}}
            )
            if result.modified_count > 0:
                logging.info(f"User {username} unsuspended successfully.")
                return True
            logging.warning(f"User {username} not found or already active.")
            return False
        except Exception as e:
            logging.error(f"Error unsuspending user: {e}")
            return False
    def search_student(search_query):
        """Search for students by username or email."""
        try:
            students = mongo.db.useraccount.find({
                "$or": [
                    {"username": {"$regex": search_query, "$options": "i"}},
                    {"email": {"$regex": search_query, "$options": "i"}}
                ]
            })
            return list(students)
        except Exception as e:
            logging.error(f"Error searching students: {e}")
            return []
    
class Material:
    ALLOWED_MATERIAL_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'zip'}

    def __init__(self, title, file, username, description,classroom_id):
        self.title = title
        self.file = file
        self.username = username
        self.description = description
        self.classroom_id = ObjectId(classroom_id)  # Ensure classroom_id is an ObjectId

    def save_material(self):
        try:
            # Validate file type
            if not self.file or '.' not in self.file.filename:
                raise ValueError("Invalid file or missing filename.")

            file_extension = self.file.filename.rsplit('.', 1)[1].lower()
            if file_extension not in self.ALLOWED_MATERIAL_EXTENSIONS:
                raise ValueError("Invalid material format.")

            # Secure the file name
            filename = secure_filename(self.file.filename)

            # Save file to GridFS
            file_id = get_fs().put(self.file, filename=filename, content_type=self.file.content_type)

            # Store material metadata in MongoDB
            mongo.db.materials.insert_one({
                'title': self.title,
                'file_id': file_id,
                'file_name': filename,
                'username': self.username,
                'upload_date': datetime.now(),
                'description': self.description,
                'classroom_id': self.classroom_id  # Ensure classroom_id is saved
            })

            return {"success": True, "message": "Material uploaded to database successfully."}

        except Exception as e:
            logging.error(f"Error saving material: {str(e)}")
            return {"success": False, "message": str(e)}
    @staticmethod
    def get_material_by_id(material_id):
        # Fetch material metadata from MongoDB
        material = mongo.db.materials.find_one({"_id": ObjectId(material_id)})

        if not material:
            return None
            
        file_data = get_fs().get(material['file_id'])
        return material, file_data

class Assignment:
    def __init__(self, title=None, file=None, classroom_id=None, description=None,
                 due_date=None, filename=None, video_path=None):
        self.title = title
        self.file = file
        self.classroom_id = classroom_id
        self.description = description
        self.due_date = due_date
        self.filename = filename
        self.video_path = video_path

    def save_assignment(self):
        try:
            file_id = None

            # ✅ Handle optional file upload
            if self.file:
                # Ensure the filename is secure
                safe_name = secure_filename(self.filename or self.file.filename)
                file_id = get_fs().put(self.file, filename=safe_name, content_type=self.file.content_type)

            # ✅ Prepare assignment data
            assignment_data = {
                "title": self.title,
                "description": self.description,
                "due_date": self.due_date,
                "file_id": file_id,
                "file_name": self.filename,         # Save the original or secure name
                "classroom_id": ObjectId(self.classroom_id),
                "video_path": self.video_path,
                "created_at": datetime.now()
            }

            # ✅ Insert into MongoDB
            result = mongo.db.assignments.insert_one(assignment_data)

            return {
                "success": True,
                "message": "Assignment saved.",
                "assignment_id": str(result.inserted_id)  # Return the new ID
            }

        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    @staticmethod
    def search_assignment(search_query):
        try:
            assignments = mongo.db.assignments.find({
                "title": {"$regex": search_query, "$options": "i"}
            })
            return list(assignments)
        except Exception as e:
            logging.error(f"❌ Failed to search assignments: {str(e)}")
            return []

    @staticmethod
    def delete_assignment(assignment_id):
        try:
            assignment = mongo.db.assignments.find_one({"_id": ObjectId(assignment_id)})
            if assignment and assignment.get("file_id"):
                get_fs().delete(ObjectId(assignment["file_id"]))
                mongo.db.assignments.delete_one({"_id": ObjectId(assignment_id)})
                return {"success": True, "message": "Assignment deleted."}
        except Exception as e:
            logging.error(f"❌ Error deleting assignment: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def get_assignment(assignment_id):
        try:
            return mongo.db.assignments.find_one({"_id": ObjectId(assignment_id)})
        except Exception as e:
            logging.error(f"❌ Failed to get assignment: {str(e)}")
            return None

    @staticmethod
    def get_assignment_file(file_id):
        try:
            file = get_fs().get(ObjectId(file_id))
            return file.read()
        except Exception as e:
            logging.error(f"❌ Failed to retrieve file: {str(e)}")
            return None
        
class Quiz:
    def __init__(self, title=None, description=None, questions=None, classroom_id=None):
        self.title = title
        self.description = description
        self.questions = questions or []
        self.classroom_id = classroom_id

    def save_quiz(self):
        try:
            quiz_data = {
                'title': self.title,
                'description': self.description,
                'questions': self.questions,
                'classroom_id': ObjectId(self.classroom_id),
                'upload_date': datetime.now()
            }

            mongo.db.quizzes.insert_one(quiz_data)
            return {"success": True, "message": "Quiz uploaded successfully."}

        except Exception as e:
            logging.error(f"Error saving quiz: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def search_quiz(search_query):
        try:
            # Use case-insensitive and partial matching
            quizzes = mongo.db.quizzes.find({
                "title": {"$regex": search_query, "$options": "i"}
            })
            return list(quizzes)
        except Exception as e:
            logging.error(f"Failed to search quizzes: {str(e)}")
            return []

    @staticmethod
    def add_question(quiz_id, question_data):
        try:
            result = mongo.db.quizzes.update_one(
                {"_id": ObjectId(quiz_id)},
                {"$push": {"questions": question_data}}
            )
            if result.modified_count > 0:
                return {"success": True, "message": "Question added successfully."}
            else:
                return {"success": False, "message": "Quiz not found or no changes made."}
        except Exception as e:
            logging.error(f"Error adding question: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def delete_question(quiz_id, question_index):
        try:
            quiz = mongo.db.quizzes.find_one({"_id": ObjectId(quiz_id)})
            if not quiz:
                return {"success": False, "message": "Quiz not found."}

            # Check if the question index is valid
            if question_index < 0 or question_index >= len(quiz.get('questions', [])):
                return {"success": False, "message": "Invalid question index."}

            # Remove the question at the specified index
            result = mongo.db.quizzes.update_one(
                {"_id": ObjectId(quiz_id)},
                {"$pull": {"questions": {"$slice": [question_index, 1]}}}
            )

            if result.modified_count > 0:
                return {"success": True, "message": "Question deleted successfully."}
            else:
                return {"success": False, "message": "Failed to delete the question."}
        except Exception as e:
            logging.error(f"Error deleting question: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def find_by_id(quiz_id):
        try:
            quiz = mongo.db.quizzes.find_one({"_id": ObjectId(quiz_id)})
            return quiz
        except Exception as e:
            logging.error(f"Failed to find quiz by ID: {str(e)}")
            return None

    @staticmethod
    def update_quiz(quiz_id, new_details):
        try:
            result = mongo.db.quizzes.update_one(
                {"_id": ObjectId(quiz_id)},
                {"$set": new_details}
            )
            if result.modified_count > 0:
                return {"success": True, "message": "Quiz updated successfully."}
            else:
                return {"success": False, "message": "No changes made or quiz not found."}
        except Exception as e:
            logging.error(f"Error updating quiz: {str(e)}")
            return {"success": False, "message": str(e)}

        
class Submission:
    def __init__(self, assignment_id, student, file, submission_date=None):
        self.assignment_id = assignment_id
        self.student = student
        self.file = file
        self.filename = file.filename  # Keep the original filename
        self.submission_date = submission_date or datetime.now()

    def save_submission(self):
        """Saves the file directly into MongoDB using GridFS."""
        try:
            if not self.file:
                raise ValueError("No file selected for upload.")

            # Connect to MongoDB and GridFS
                        # Store file in GridFS
            file_id = get_fs().put(self.file, filename=self.filename, student=self.student)

            # Create submission record
            submission_data = {
                'assignment_id': ObjectId(self.assignment_id),
                'student': self.student,
                'file_id': file_id,  # Reference to GridFS
                'file_name': self.filename,
                'submission_date': self.submission_date,
                'grade': None,  # Initially set to None
                'feedback': ''
            }

            # Insert submission record into MongoDB
            mongo.db.submissions.insert_one(submission_data)

            # Update assignment with submission reference
            mongo.db.assignments.update_one(
                {"_id": ObjectId(self.assignment_id)},
                {"$push": {"submissions": submission_data}}
            )

            return {"success": True, "message": "Submission uploaded successfully."}

        except Exception as e:
            logging.error(f"Error saving submission: {str(e)}")
            return {"success": False, "message": str(e)}
    
    @staticmethod
    def get_submission_by_student_and_assignment(student_username, assignment_id):
        """
        Check if the student has already submitted the assignment.
        Returns submission details if found, otherwise returns None.
        """
        submission = mongo.db.submissions.find_one({
            'student': student_username,
            'assignment_id': ObjectId(assignment_id)
        })
        return submission

    def get_submission_by_student_and_id(student_username, submission_id):
        """
        Check if the student has already submitted the assignment.
        Returns submission details if found, otherwise returns None.
        """
        submission = mongo.db.submissions.find_one({
            'student': student_username,
            '_id': ObjectId(submission_id)
        })
        return submission
    
    def get_submission_file(file_id):
        """
        Retrieve the file from GridFS using the file_id.
        Returns the file content.
        """
        try:
            file_data = get_fs().get(ObjectId(file_id))
            return file_data.read()  # Return file content
        except Exception as e:
                logging.error(f"Failed to retrieve file from GridFS: {str(e)}")
        return None
            
    def delete_submission(submission_id):
        """
        Deletes the submission from the database and GridFS.
        """
        try:
            # Find the submission to delete
            submission = mongo.db.submissions.find_one({"_id": ObjectId(submission_id)})
            if submission:
                # Delete the file from GridFS
                get_fs().delete(submission['file_id'])
                # Delete the submission record from MongoDB
                mongo.db.submissions.delete_one({"_id": ObjectId(submission_id)})
                return {"success": True, "message": "Submission deleted successfully."}
            return {"success": False, "message": "Submission not found."}
        except Exception as e:
            logging.error(f"Error deleting submission: {str(e)}")
            return {"success": False, "message": str(e)}
    @staticmethod
    def update_feedback(submission_id, student_username, feedback):
        """
        Update the feedback of a submission.
        """
        try:
            result = mongo.db.submissions.update_one(
                {"_id": ObjectId(submission_id)},
                {"$set": {"feedback": feedback}}
            )
            if result.matched_count:
                return {"success": True, "message": "Feedback updated successfully."}
            return {"success": False, "message": "Submission not found."}
        except Exception as e:
            logging.error(f"Error updating feedback: {str(e)}")
            return {"success": False, "message": str(e)}
      
class DiscussionRoom:
    def __init__(self, classroom_id=None, discussion_room_name=None,discussion_room_description=None, created_by =None):
        self.classroom_id = classroom_id
        self.discussion_room_name = discussion_room_name
        self.discussion_room_description = discussion_room_description
        self.created_by = created_by

    @staticmethod
    def create_discussion_room(classroom_id, discussion_room_name, discussion_room_description,created_by):
        try:
            room_data = {
                "classroom_id": ObjectId(classroom_id),
                "discussion_room_name": discussion_room_name,
                "discussion_room_description": discussion_room_description,
                "created_at": datetime.now(),
                "created_by": created_by

            }
            mongo.db.discussion_rooms.insert_one(room_data)
            return True
        except Exception as e:
            print(f"Error creating discussion room: {e}")
            return False

    @staticmethod
    def delete_discussion_room(discussion_room_id):
        try:
            mongo.db.discussion_rooms.delete_one({"_id": ObjectId(discussion_room_id)})
            return True
        except Exception as e:
            print(f"Error deleting discussion room: {e}")
            return False

    @staticmethod
    def update_discussion_room(discussion_room_id, new_details):
        try:
            mongo.db.discussion_rooms.update_one(
                {"_id": ObjectId(discussion_room_id)},
                {"$set": new_details}
            )
            return True
        except Exception as e:
            print(f"Error updating discussion room: {e}")
            return False

    @staticmethod
    def search_discussion_room(search_query):
        try:
            query = {"discussion_room_name": {"$regex": search_query, "$options": "i"}}
            rooms = list(mongo.db.discussion_rooms.find(query))
            return rooms
        except Exception as e:
            print(f"Error searching discussion rooms: {e}")
            return []

    @staticmethod
    def get_all_discussion_rooms_by_classroom_id(classroom_id):
        try:
            rooms = list(mongo.db.discussion_rooms.find({"classroom_id":ObjectId(classroom_id)}))
            print(rooms)
            return rooms
        except Exception as e:
            print(f"Error retrieving discussion rooms: {e}")
            return []
    @staticmethod
    def find_by_id(discussion_room_id):
        try:
            room = mongo.db.discussion_rooms.find_one({"_id": ObjectId(discussion_room_id)})
            return room
        except Exception as e:
            print(f"Error finding discussion room by ID: {e}")
            return None
    def get_id(discussion_room_id):
        try:
            result = mongo.db.discussion_rooms.find_one({"_id": ObjectId(discussion_room_id)})
            if result:
                print(result['_id'])
                return str(result["_id"])  # Convert to string to avoid ObjectId type issues
            return None
        except Exception as e:
            print(f"Error finding discussion room by ID: {e}")
            return None

class Message:
    def __init__(self, discussion_room_id=None, sender=None, message=None):
        self.discussion_room_id = discussion_room_id
        self.sender = sender
        self.message = message

    def send_message(discussion_room_id, sender, message):
        try:
            message_data = {
                "discussion_room_id": discussion_room_id,
                "sender": sender,
                "message": message,
                "sent_at": datetime.now()
            }
            mongo.db.messages.insert_one(message_data)
            return True
        except Exception as e:
            print(f"Error saving message: {e}")
            return False

    @staticmethod
    def get_all_messages(discussion_room_id):
        try:
            messages = list(mongo.db.messages.find({"discussion_room_id": discussion_room_id}))
            print(messages)
            return messages
        except Exception as e:
            print(f"Error getting messages: {e}")
            return []

    @staticmethod
    def delete_message(message_id):
        try:
            mongo.db.messages.delete_one({"_id": ObjectId(message_id)})
            return True
        except Exception as e:
            print(f"Error deleting message: {e}")
            return False

    @staticmethod
    def delete_messages(discussion_room_id):
        try:
            mongo.db.messages.delete_many({"discussion_room_id": discussion_room_id})
            return True
        except Exception as e:
            print(f"Error deleting messages: {e}")
            return False

    @staticmethod
    def search_messages(search_query):
        try:
            query = {"message": {"$regex": search_query, "$options": "i"}}
            messages = list(mongo.db.messages.find(query))
            return messages
        except Exception as e:
            print(f"Error searching messages: {e}")
            return []
        
    @staticmethod
    def update_message(message_id, new_details):
        try:
            mongo.db.messages.update_one(
                {"_id": ObjectId(message_id)},
                {"$set": new_details}
            )
            return True
        except Exception as e:
            print(f"Error updating message: {e}")
            return False


class Notification:

    @staticmethod
    def get_student_classroom_ids(username):
        classrooms = mongo.db.classroom.find({"student_list": username})
        return [classroom["_id"] for classroom in classrooms]

    @staticmethod
    def get_notification_by_username(username):
        if session['role'] == 'Teacher':
            return mongo.db.notifications.find({"username": username}).sort("timestamp", -1)
        elif session['role'] == 'Student':
            classroom_ids = Notification.get_student_classroom_ids(username)
            if classroom_ids:
                return mongo.db.notifications.find({
                    "classroom_id": {"$in": classroom_ids}
                }).sort("timestamp", -1)
            else:
                return None

    @staticmethod
    def search_notification(search_query):
        return mongo.db.notifications.find({
            "$or": [
                {"title": {"$regex": search_query, "$options": "i"}},
                {"description": {"$regex": search_query, "$options": "i"}}
            ]
        }).sort("timestamp", -1)

    @staticmethod
    def insert_notification(username, classroom_id, title, description, priority):
        classroom = mongo.db.classroom.find_one(
            {"_id": ObjectId(classroom_id)},
            {"classroom_name": 1, "_id": 0}
        )
        classroom_name = classroom.get('classroom_name') if classroom else None
        mongo.db.notifications.insert_one({
            "username": username,
            "classroom_id": ObjectId(classroom_id),
            "classroom_name": classroom_name,
            "title": title.strip(),
            "description": description.strip(),
            "is_read": False,
            "priority": int(priority),
            "timestamp": datetime.now()
        })

    @staticmethod
    def delete_notification(notification_id):
        mongo.db.notifications.delete_one({"_id": ObjectId(notification_id)})

    @staticmethod
    def get_notification_by_id(notification_id):
        return mongo.db.notifications.find_one({"_id": ObjectId(notification_id)})

    @staticmethod
    def update_notification(notification_id, title, description, priority):
        mongo.db.notifications.update_one(
            {"_id": ObjectId(notification_id)},
            {"$set": {
                "title": title.strip(),
                "description": description.strip(),
                "priority": int(priority)
            }}
        )

    @staticmethod
    def mark_as_read(username):
        if session['role'] == 'Teacher':
            mongo.db.notifications.update_many(
                {"username": username},
                {"$set": {"is_read": True}}
            )
        elif session['role'] == 'Student':
            classroom_ids = Notification.get_student_classroom_ids(username)
            if classroom_ids:
                mongo.db.notifications.update_many(
                    {"classroom_id": {"$in": classroom_ids}},
                    {"$set": {"is_read": True}}
                )

    @staticmethod
    def get_unread_notifications(username):
        if session['role'] == 'Teacher':
            return mongo.db.notifications.find({
                "username": username,
                "is_read": False
            }).sort("timestamp", -1)
        elif session['role'] == 'Student':
            classroom_ids = Notification.get_student_classroom_ids(username)
            if classroom_ids:
                return mongo.db.notifications.find({
                    "classroom_id": {"$in": classroom_ids},
                    "is_read": False
                }).sort("timestamp", -1)
            else:
                return []  # ✅ SAFER: return empty list instead of None
