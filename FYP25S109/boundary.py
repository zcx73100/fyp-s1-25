from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session, jsonify, send_from_directory, make_response, send_file, abort
from . import mongo
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from bson import ObjectId, Binary, errors
from markupsafe import Markup
import base64
import mimetypes
import threading
import time
import datetime
from datetime import timedelta,datetime
from flask import Flask, send_file, Response
from gradio_client import Client
from FYP25S109.controller import *
from FYP25S109.entity import * 
from bson.errors import InvalidId
from io import BytesIO
import re
import ffmpeg
from FYP25S109.entity import get_fs
from gtts import gTTS

boundary = Blueprint('boundary', __name__)
UPLOAD_FOLDER = 'FYP25S109/static/uploads/materials'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ASSIGNMENT_UPLOAD_FOLDER = 'FYP25S109/static/uploads/assignments'
os.makedirs(ASSIGNMENT_UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'txt'}

YOUR_DOMAIN = "http://localhost:5000"

GENERATE_FOLDER_AUDIOS = 'FYP25S109/static/generated_audios'
GENERATE_FOLDER_VIDEOS = 'FYP25S109/static/generated_videos'
os.makedirs(GENERATE_FOLDER_AUDIOS, exist_ok=True)
os.makedirs(GENERATE_FOLDER_VIDEOS, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Homepage
class HomePage:
    @boundary.route('/')
    def home():
        username = session.get("username")
        role = session.get("role")

        user_info = mongo.db.useraccount.find_one({"username": username}) if username else None

        # Fetch teacher + admin users
        teacher_users = [u["username"] for u in mongo.db.useraccount.find({"role": "Teacher"}, {"username": 1})]
        admin_users = [u["username"] for u in mongo.db.useraccount.find({"role": "Admin"}, {"username": 1})]

        # Fetch all tutorial videos (for main video section)
        teacher_videos = list(mongo.db.tutorialvideo.find({"username": {"$in": teacher_users}}))
        admin_videos = list(mongo.db.tutorialvideo.find({"username": {"$in": admin_users}}))

        # Fetch avatars uploaded by Admins
        avatar = list(mongo.db.avatar.find({"username": {"$in": admin_users}}))

        avatar_showcase = []
        for avatar_doc in avatar:
            avatar_id = avatar_doc["_id"]

            avatar_data = {
                "avatarname": avatar_doc.get("avatarname"),
                "image_data": avatar_doc.get("image_data"),
            }

            # Force ObjectId just in case something changed in type
            if not isinstance(avatar_id, ObjectId):
                avatar_id = ObjectId(avatar_id)

            print(f"🔍 Looking for video with avatar_id={avatar_id} (type: {type(avatar_id)})")

            video = mongo.db.generated_videos.find_one({
                "avatar_id": avatar_id,
                "is_published": True
            }, sort=[("published_at", -1)])


            if video:
                print(f"✅ Found video for {avatar_data['avatarname']}: {video.get('_id')}")
                avatar_data["video_id"] = video.get("video_id")
                print(f"Video ID: {avatar_data['video_id']}")
            else:
                print(f"❌ No video found for avatar {avatar_data['avatarname']} with ID {avatar_id}")
                avatar_data["video_id"] = None

            avatar_showcase.append(avatar_data)
                    
        # Classrooms by role
        if role == "Teacher":
            classrooms = list(mongo.db.classroom.find({"teacher": username}, {"_id": 1, "classroom_name": 1, "description": 1}))
        elif role == "Student":
            classrooms = list(mongo.db.classroom.find({"student_list": username}, {"_id": 1, "classroom_name": 1, "description": 1}))
        else:
            classrooms = list(mongo.db.classroom.find({}, {"_id": 1, "classroom_name": 1, "description": 1}))

        classroom_ids = [c["_id"] for c in classrooms]

        # Class-related collections
        announcements = {
            cid: list(mongo.db.announcements.find({"classroom_id": cid}, {"_id": 1, "title": 1, "content": 1}))
            for cid in classroom_ids
        }

        materials = {
            cid: list(mongo.db.materials.find({"classroom_id": cid}, {"_id": 1, "title": 1}))
            for cid in classroom_ids
        }

        assignments = {
            cid: list(mongo.db.assignments.find({"classroom_id": cid}, {"_id": 1, "title": 1}))
            for cid in classroom_ids
        }

        quizzes = {
            str(cid): list(mongo.db.quizzes.find({"classroom_id": ObjectId(cid)}, {"_id": 1, "title": 1}))
            for cid in classroom_ids
        }

        return render_template(
            "homepage.html",
            user_info=user_info,
            username=username,
            role=role,
            videos=admin_videos + teacher_videos,
            avatar_showcase=avatar_showcase,
            classrooms=classrooms,
            announcements=announcements,
            materials=materials,
            assignments=assignments,
            quizzes=quizzes
        )


class AvatarVideoBoundary:
    @boundary.route('/my_videos')
    def my_videos():
        username = session.get("username")
        if not username:
            return redirect(url_for('boundary.login'))

        role = session.get("role")
        search_query = request.args.get("search", "").strip().lower()

        # Get all videos for the user
        draft_videos = list(mongo.db.tempvideo.find({ "username": username }))
        published_videos = list(mongo.db.generated_videos.find({ "username": username }))

        # 🔧 Convert ObjectId to string for template
        for video in draft_videos:
            video["_id"] = str(video["_id"])
            # ✅ Corrected key
            if "video_id" in video:
                video["video_id"] = str(video["video_id"])
            else:
                video["video_id"] = None

        # Filter if search provided
        if search_query:
            draft_videos = [v for v in draft_videos if search_query in v.get("title", "").lower()]
            published_videos = [v for v in published_videos if search_query in v.get("title", "").lower()]

        return render_template("myVideos.html",
                            username=username,
                            drafts=draft_videos,
                            videos=published_videos,
                            role=role)



        
    # Route: Generate Voice
    @boundary.route("/generate_voice", methods=["POST"])
    def generate_voice():
        data = request.get_json()
        text = data.get("text", "").strip()

        if not text:
            return jsonify(success=False, error="Text is required.")

        try:
            from gtts import gTTS
            import os, uuid
            from datetime import datetime
            from FYP25S109.entity import get_fs
            from flask import session

            filename = f"gtts_{uuid.uuid4().hex}.mp3"
            filepath = os.path.join("temp_audio", filename)
            os.makedirs("temp_audio", exist_ok=True)

            # Generate voice
            gtts = gTTS(text=text, lang="en")
            gtts.save(filepath)

            # Save to GridFS
            with open(filepath, "rb") as f:
                file_id = get_fs().put(f, filename=filename, content_type="audio/mpeg")

            os.remove(filepath)

            # Save metadata
            mongo.db.voice_records.insert_one({
                "audio_id": file_id,
                "text": text,
                "source": "gtts",
                "created_at": datetime.utcnow(),
                "username": session.get("username")
            })

            return jsonify(success=True, audio_id=str(file_id))
        except Exception as e:
            return jsonify(success=False, error=str(e))

    # Route: Stream audio from GridFS
    @boundary.route("/stream_audio/<audio_id>")
    def stream_audio(audio_id):
        try:
            file = get_fs().get(ObjectId(audio_id))
            file_size = file.length

            # Determine content type based on filename
            filename = getattr(file, 'filename', 'audio.webm')
            content_type = mimetypes.guess_type(filename)[0]
            if not content_type:
                # fallback if guessing fails
                content_type = "audio/mpeg"

            # Check for Range header (for partial streaming)
            range_header = request.headers.get('Range', None)
            if range_header:
                byte1, byte2 = 0, None
                m = re.search(r'bytes=(\d+)-(\d*)', range_header)
                if m:
                    byte1 = int(m.group(1))
                    if m.group(2):
                        byte2 = int(m.group(2))
                
                byte2 = byte2 if byte2 is not None else file_size - 1
                length = byte2 - byte1 + 1

                file.seek(byte1)
                data = file.read(length)

                rv = Response(data, 206, mimetype=content_type, direct_passthrough=True)
                rv.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
                rv.headers.add('Accept-Ranges', 'bytes')
                rv.headers.add('Content-Length', str(length))
                return rv
            else:
                # Full file
                data = file.read()
                rv = Response(data, 200, mimetype=content_type)
                rv.headers.add('Content-Length', str(file_size))
                rv.headers.add('Accept-Ranges', 'bytes')
                return rv

        except Exception as e:
            print(f"Error streaming audio {audio_id}: {str(e)}")
            return jsonify(success=False, error=f"Audio not found: {str(e)}"), 404
    
    @boundary.route("/generate_voice_form", methods=["POST"])
    def generate_voice_form():
        text   = request.form.get("text", "").strip()
        lang   = request.form.get("lang",  "en")
        gender = request.form.get("gender", "female")
        source = request.form.get("source", "manual") 

        if not text:
            return jsonify(success=False, error="No text provided."), 400

        try:
            controller = GenerateVideoController()
            audio_id   = controller.generate_voice(text, lang, gender, source)

            if not audio_id:
                return jsonify(success=False, error="Voice generation failed."), 500

            return jsonify(success=True, audio_id=str(audio_id))
        except Exception as e:
            return jsonify(success=False, error=str(e)), 500



    @boundary.route("/generate_video/<avatar_id>/<audio_id>", methods=["POST"])
    def generate_video(avatar_id, audio_id):
        username = session.get("username")
        video_title = request.form.get("video_title", "Untitled")
        task_id = str(uuid.uuid4())
    
        avatar_doc = mongo.db.avatar.find_one({"_id": ObjectId(avatar_id)})
        if not avatar_doc:
            return jsonify(success=False, error="Avatar not found"), 404
    
        def background_video_generation():
            try:
                fs = get_fs()
                img = fs.get(ObjectId(avatar_doc["file_id"]))
                aud = fs.get(ObjectId(audio_id))
    
                files = {
                    "image_file": (img.filename, img.read(), img.content_type),
                    "audio_file": (aud.filename, aud.read(), aud.content_type)
                }
                SADTALKER_API = os.getenv("SADTALKER_API_URL")
                resp = requests.post(SADTALKER_API, files=files, stream=True, timeout=300)
                resp.raise_for_status()
    
                buf = io.BytesIO()
                for chunk in resp.iter_content(8192):
                    buf.write(chunk)
                buf.seek(0)
    
                gridfs_id = fs.put(buf, filename=f"{video_title}.mp4", content_type="video/mp4")
    
                mongo.db.tempvideo.insert_one({
                       "task_id": task_id,
                        "username": username,
                        "video_id": gridfs_id,
                        "title": video_title,
                        "avatar_id": ObjectId(avatar_id),   # ✅ Add this
                        "audio_id": ObjectId(audio_id),     # ✅ Add this
                        "created_at": datetime.utcnow(),
                        "is_published": False
                })
            except Exception as err:
                mongo.db.tempvideo.insert_one({
                    "task_id": task_id,
                    "username": username,
                    "title": video_title, 
                    "error": str(err),
                    "created_at": datetime.utcnow()
                })
    
        threading.Thread(target=background_video_generation, daemon=True).start()
        return jsonify(success=True, task_id=task_id)  # ✅ This was missing!


        
    @boundary.route("/stream_avatar/<avatar_id>")
    def stream_avatar(avatar_id):
        try:
            avatar = mongo.db.avatar.find_one({"_id": ObjectId(avatar_id)})
            if not avatar:
                return "Avatar not found", 404

            fs = get_fs()  # ✅ define fs before using it
            file_id = avatar["file_id"]
            file = fs.get(file_id)
            return Response(file.read(), mimetype="image/png")
        except Exception as e:
            print("❌ Error streaming avatar:", e)
            return "Error", 500

    
    # Generate Video for Chatbot
    @boundary.route("/generate_video_for_chatbot/<avatar_id>/<audio_id>", methods=["POST"])
    def generate_video_for_chatbot(avatar_id, audio_id):
        from bson import ObjectId
        import threading, io, os, requests
        from datetime import datetime

        username = session.get("username")
        if not username:
            return jsonify({"success": False, "error": "Not logged in"}), 401

        try:
            avatar_doc = mongo.db.avatar.find_one({"_id": ObjectId(avatar_id)})
            if not avatar_doc:
                return jsonify({"success": False, "error": "Avatar not found"}), 404

            file_id = avatar_doc.get("file_id")
            if not file_id:
                return jsonify({"success": False, "error": "Avatar missing file_id"}), 400

            task_id = str(uuid.uuid4())

            def background_video_generation():
                try:
                    fs = get_fs()

                    # Retrieve avatar image and audio from GridFS
                    img = fs.get(ObjectId(file_id))
                    aud = fs.get(ObjectId(audio_id))

                    files = {
                        "image_file": (img.filename, img.read(), img.content_type),
                        "audio_file": (aud.filename, aud.read(), aud.content_type)
                    }

                    SADTALKER_API = os.getenv("SADTALKER_API_URL")
                    if not SADTALKER_API:
                        raise RuntimeError("SADTALKER_API_URL is not set.")

                    resp = requests.post(SADTALKER_API, files=files, stream=True, timeout=300)
                    resp.raise_for_status()

                    # Write the streamed response to memory buffer
                    buf = io.BytesIO()
                    for chunk in resp.iter_content(chunk_size=8192):
                        buf.write(chunk)
                    buf.seek(0)

                    # Save video to GridFS
                    gridfs_id = fs.put(buf, filename="Chatbot Reply.mp4", content_type="video/mp4")

                    # Save metadata
                    mongo.db.tempvideo.insert_one({
                        "task_id": task_id,
                        "username": username,
                        "video_id": gridfs_id,
                        "created_at": datetime.utcnow(),
                        "source": "chatbot",
                        "is_published": False
                    })

                except Exception as err:
                    print(f"[Chatbot Video] ❌ Error: {err}")
                    mongo.db.tempvideo.insert_one({
                        "task_id": task_id,
                        "username": username,
                        "error": str(err),
                        "created_at": datetime.utcnow(),
                        "source": "chatbot",
                        "status": "failed"
                    })

            threading.Thread(target=background_video_generation, daemon=True).start()

            return jsonify({
                "success": True,
                "task_id": task_id
            })

        except Exception as e:
            print("❌ Error in generate_video_for_chatbot:", e)
            return jsonify({"success": False, "error": str(e)}), 500



    @boundary.route("/check_video/<task_id>", methods=["GET"])
    def check_video(task_id):
        result = mongo.db.tempvideo.find_one({"task_id": task_id})
        if not result:
            return jsonify(ready=False)

        if "error" in result:
            return jsonify(ready=True, error=result["error"])

        video_id = result.get("video_id")  # ✅ Works for both chatbot and manual
        if not video_id:
            return jsonify(ready=False)

        return jsonify(ready=True, video_id=str(video_id))



    
    @boundary.route("/stream_video/<video_id>")
    def stream_video(video_id):
        try:
            # ✅ Remove ".mp4" suffix if present
            if video_id.endswith(".mp4"):
                video_id = video_id[:-4]
            file = get_fs().get(ObjectId(video_id))
            return send_file(file, mimetype="video/mp4", as_attachment=False)
        except Exception as e:
            print(f"❌ Error streaming video {video_id}: {e}")
            return f"Video not found: {e}", 404

    @boundary.route("/generate_video_page", methods=["GET"])
    def generate_video_page():
        username = session.get("username")
        if not username:
            flash("Login required", "error")
            return redirect(url_for("boundary.login"))

        # Clean up old temp videos…
        cutoff = datetime.utcnow() - timedelta(hours=24)
        mongo.db.tempvideo.delete_many({
            "username": username,
            "is_published": False,
            "created_at": {"$lt": cutoff}
        })

        avatars      = list(mongo.db.avatar.find({"username": username}))
        voices       = list(mongo.db.voice_records.find({"username": username, "source": { "$ne": "chatbot" }}))
        classroom_id = request.args.get("classroom_id")   # only this one
        show_publish = bool(classroom_id)                  # show if present

        return render_template(
            "generateVideo.html",
            avatars=avatars,
            voice_records=voices,
            show_publish=show_publish,
            classroom_id=classroom_id,
            debug_mode=False
        )


    @boundary.route("/save_generated_video", methods=["POST"])
    def save_generated_video():
        try:
            data     = request.get_json()
            username = session.get("username")
            role     = session.get("role")

            # Pull the title (not “text”) from the JSON
            title    = data.get("title", "").strip() or "Untitled"
            audio_id = data.get("audio_id")
            avatar_id= data.get("avatar_id")
            video_id = data.get("video_id")

            if not all([audio_id, avatar_id, video_id]):
                return jsonify(success=False, error="Missing required fields."), 400

            # Insert into permanent collection
            saved = mongo.db.generated_videos.insert_one({
                "username":     username,
                "role":         role,
                "title":        title,
                "audio_id":     ObjectId(audio_id),
                "avatar_id":    ObjectId(avatar_id),
                "video_id":     ObjectId(video_id),
                "created_at":   datetime.utcnow(),
                "is_published": False
            })

            # Remove from temp collection
            mongo.db.tempvideo.delete_many({
                "username": username,
                "video_id": ObjectId(video_id)
            })

            session["stashed_video_id"] = str(saved.inserted_id)
            return jsonify(success=True, saved_id=str(saved.inserted_id))

        except Exception as e:
            current_app.logger.exception("Error saving generated video")
            return jsonify(success=False, error=str(e)), 500

    @boundary.route("/upload_recorded_voice", methods=["POST"])
    def upload_recorded_voice():
        if "audio" not in request.files:
            return jsonify(success=False, error="No audio file uploaded.")
        
        audio_file = request.files["audio"]
        if audio_file.filename == "":
            return jsonify(success=False, error="No selected file.")
        
        # Save the uploaded webm temporarily
        filename = secure_filename(str(uuid.uuid4()) + ".webm")
        temp_path = os.path.join("temp_audio", filename)
        os.makedirs("temp_audio", exist_ok=True)
        audio_file.save(temp_path)
        
        # Convert WebM to MP3
        mp3_filename = filename.rsplit(".", 1)[0] + ".mp3"
        mp3_path = os.path.join("saved_audios", mp3_filename)
        os.makedirs("saved_audios", exist_ok=True)
        
        try:
            # ffmpeg must be installed on the server!
            subprocess.run([
                "ffmpeg", "-i", temp_path, "-q:a", "0", "-map", "a", mp3_path
            ], check=True)
        except subprocess.CalledProcessError:
            return jsonify(success=False, error="Audio conversion failed.")
        
        # Remove temp webm
        os.remove(temp_path)
        
        # Save MP3 file to GridFS
        with open(mp3_path, "rb") as f:
            file_id = get_fs().put(f, filename=mp3_filename)
        
        # Remove the local mp3 file after storing it in GridFS
        os.remove(mp3_path)

        # Save metadata about the audio file to a separate collection (optional)
        audio_record = {
            "filename": mp3_filename,
            "audio_id": file_id,
            "created_at": datetime.now(),
            "username": session.get("username")
        }
        audio_id = mongo.db.voice_records.insert_one(audio_record)
        
        return jsonify(success=True, audio_id=str(audio_id.inserted_id))

    @boundary.route('/get_voice_records', methods=['GET'])
    def get_voice_records():
        try:
            username = session.get("username")
            if not username:
                return jsonify(success=False, error="Not logged in"), 401
                
            records = list(mongo.db.voice_records.find(
                {"username": username},
                {}
            ).sort("created_at", -1))
            
            for record in records:
                record["audio_id"] = str(record["audio_id"])
                
            return jsonify(success=True, records=records)
            
        except Exception as e:
            print(f"Error fetching voice records: {str(e)}")
            return jsonify(success=False, error=str(e)), 500

    @boundary.route("/publish_to_homepage", methods=["POST"])
    def publish_to_homepage():
        try:
            username = session.get("username")
            role = session.get("role")

            if role != "Admin":
                return jsonify({"success": False, "error": "Unauthorized"}), 403

            data = request.get_json()
            video_id = data.get("video_id")

            if not video_id:
                return jsonify({"success": False, "error": "Missing video_id"}), 400

            result = mongo.db.generated_videos.update_one(
                {"video_id": ObjectId(video_id), "username": username},
                {"$set": {"is_published": True, "published_at": datetime.utcnow()}}  # Include timestamp!
            )

            if result.modified_count == 0:
                return jsonify({"success": False, "error": "Video not found or already published"}), 404

            return jsonify(success=True)

        except Exception as e:
            print("❌ Publish Error:", e)
            return jsonify(success=False, error=str(e)), 500

    
    @boundary.route("/upload_synthesized_voice", methods=["POST"])
    def upload_synthesized_voice():
        if 'audio' not in request.files and not request.form.get('text'):
            return jsonify(success=False, error="No audio file or text provided"), 400

        try:
            text = request.form.get('text', '')
            lang = request.form.get('lang', 'en')
            gender = request.form.get('gender', 'female')

            # 👉 Use Controller
            audio_id = GenerateVideoController.generate_voice(text=text, lang=lang, gender=gender)
            
            if not audio_id:
                return jsonify(success=False, error="Failed to generate voice"), 500

            return jsonify(success=True, audio_id=str(audio_id))

        except Exception as e:
            print(f"Error uploading synthesized voice: {str(e)}")
            return jsonify(success=False, error=str(e)), 500
    
    @boundary.route("/delete_generated_video/<video_id>", methods=["POST"])
    def delete_generated_video(video_id):
        try:
            username = session.get("username")
            if not username:
                return jsonify(success=False, error="Unauthorized"), 401

            fs = get_fs()

            # First try to delete from generated_videos
            video = mongo.db.generated_videos.find_one({
                "video_id": ObjectId(video_id),
                "username": username
            })
            if video:
                fs.delete(ObjectId(video["video_id"]))
                mongo.db.generated_videos.delete_one({
                    "video_id": ObjectId(video_id),
                    "username": username
                })
                flash("Published video deleted.", "success")
                return redirect(url_for('boundary.my_videos'))

            # If not found, try tempvideo (draft)
            draft = mongo.db.tempvideo.find_one({
                "video_id": ObjectId(video_id),
                "username": username
            })
            if draft:
                fs.delete(ObjectId(draft["video_id"]))
                mongo.db.tempvideo.delete_one({
                    "video_id": ObjectId(video_id),
                    "username": username
                })
                flash("Draft video deleted.", "success")
                return redirect(url_for('boundary.my_videos'))

            flash("Video not found.", "danger")
            return redirect(url_for('boundary.my_videos'))

        except Exception as e:
            print(f"Error deleting video: {str(e)}")
            flash("An error occurred while deleting the video.", "danger")
            return redirect(url_for('boundary.my_videos'))


    @boundary.route('/generated_video/<video_id>')
    def serve_generated_video(video_id):
        try:
            grid_out = get_fs().get(ObjectId(video_id))
            file_size = grid_out.length
            range_header = request.headers.get('Range')

            if range_header:
                start, end = range_header.replace('bytes=', '').split('-')
                start = int(start)
                end = int(end) if end else file_size - 1
                length = end - start + 1

                grid_out.seek(start)
                data = grid_out.read(length)

                response = Response(data, status=206, mimetype=grid_out.content_type)
                response.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
                response.headers.add('Accept-Ranges', 'bytes')
                response.headers.add('Content-Length', str(length))
                return response

            return Response(grid_out.read(), mimetype=grid_out.content_type)

        except Exception as e:
            logging.error(f"Failed to serve video: {str(e)}")
            return "Video not found", 404

    

    @boundary.route("/get_voice/<audio_id>")
    def get_voice(audio_id):
        """Stream a specific voice recording from GridFS"""
        try:
            username = session.get("username")
            if not username:
                return jsonify(success=False, error="Not logged in"), 401
                
            # Verify the voice belongs to the user
            voice_record = mongo.db.voice_records.find_one({
                "audio_id": ObjectId(audio_id),
                "username": username
            })
            
            if not voice_record:
                return jsonify(success=False, error="Voice not found"), 404

            file = get_fs().get(ObjectId(audio_id))
            file_size = file.length

            # Determine content type based on filename
            filename = getattr(file, 'filename', 'audio.mp3')
            content_type = mimetypes.guess_type(filename)[0] or "audio/mpeg"

            # Handle range requests for partial content
            range_header = request.headers.get('Range', None)
            if range_header:
                byte1, byte2 = 0, None
                m = re.search(r'bytes=(\d+)-(\d*)', range_header)
                if m:
                    byte1 = int(m.group(1))
                    if m.group(2):
                        byte2 = int(m.group(2))
                
                byte2 = byte2 if byte2 is not None else file_size - 1
                length = byte2 - byte1 + 1

                file.seek(byte1)
                data = file.read(length)

                rv = Response(data, 206, mimetype=content_type, direct_passthrough=True)
                rv.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
                rv.headers.add('Accept-Ranges', 'bytes')
                rv.headers.add('Content-Length', str(length))
                return rv
            else:
                # Full file response
                data = file.read()
                rv = Response(data, 200, mimetype=content_type)
                rv.headers.add('Content-Length', str(file_size))
                rv.headers.add('Accept-Ranges', 'bytes')
                return rv

        except Exception as e:
            print(f"Error streaming voice {audio_id}: {str(e)}")
            return jsonify(success=False, error=f"Voice not found: {str(e)}"), 404


    @boundary.route("/update_voice_name/<audio_id>", methods=["POST"])
    def update_voice_name(audio_id):
        """Update the name/title of a voice recording"""
        try:
            username = session.get("username")
            if not username:
                return jsonify(success=False, error="Not logged in"), 401

            data = request.get_json()
            new_name = data.get("new_name", "").strip()

            if not new_name:
                return jsonify(success=False, error="New name cannot be empty"), 400

            # Verify the voice belongs to the user before updating
            result = mongo.db.voice_records.update_one(
                {
                    "audio_id": ObjectId(audio_id),
                    "username": username
                },
                {
                    "$set": {"text": new_name}
                }
            )

            if result.modified_count == 0:
                return jsonify(success=False, error="Voice not found or no changes made"), 404

            return jsonify(success=True, message="Voice name updated")

        except Exception as e:
            print(f"Error updating voice name {audio_id}: {str(e)}")
            return jsonify(success=False, error=str(e)), 500


    @boundary.route("/delete_voice/<audio_id>", methods=["DELETE"])
    def delete_voice(audio_id):
        """Delete a voice recording and its metadata"""
        try:
            username = session.get("username")
            if not username:
                return jsonify(success=False, error="Not logged in"), 401

            # First verify the voice belongs to the user
            voice_record = mongo.db.voice_records.find_one({
                "audio_id": ObjectId(audio_id),
                "username": username
            })
            
            if not voice_record:
                return jsonify(success=False, error="Voice not found"), 404

            # ✅ Delete from GridFS
            fs = get_fs()
            fs.delete(ObjectId(audio_id))

            # ✅ Delete metadata
            result = mongo.db.voice_records.delete_one({
                "audio_id": ObjectId(audio_id),
                "username": username
            })

            if result.deleted_count == 1:
                return jsonify(success=True, message="Voice deleted")
            else:
                return jsonify(success=False, error="Failed to delete voice record"), 500

        except Exception as e:
            print(f"Error deleting voice {audio_id}: {str(e)}")
            return jsonify(success=False, error=str(e)), 500


    @boundary.route("/upload_mp3_voice", methods=["POST"])
    def upload_mp3_voice():
        """Handle MP3 file uploads for avatar voices"""
        try:
            username = session.get("username")
            if not username:
                return jsonify(success=False, error="Not logged in"), 401
                
            if 'audio' not in request.files:
                return jsonify(success=False, error="No audio file uploaded"), 400
                
            audio_file = request.files['audio']
            if audio_file.filename == '':
                return jsonify(success=False, error="No selected file"), 400
                
            # Validate file extension
            if not audio_file.filename.lower().endswith('.mp3'):
                return jsonify(success=False, error="Only MP3 files are allowed"), 400
                
            # Get optional name from form
            voice_name = request.form.get('name', '').strip() or f"Uploaded Voice {datetime.now().strftime('%Y-%m-%d')}"
            
            # Save to GridFS
            file_id = get_fs().put(
                audio_file,
                filename=secure_filename(audio_file.filename),
                content_type='audio/mpeg'
            )
            
            # Create voice record
            voice_record = {
                "username": username,
                "audio_id": file_id,
                "text": voice_name,
                "source": "upload",
                "created_at": datetime.utcnow()
            }
            
            inserted_id = mongo.db.voice_records.insert_one(voice_record).inserted_id
            
            return jsonify(
                success=True,
                audio_id=str(file_id),
                record_id=str(inserted_id),
                name=voice_name
            )
            
        except Exception as e:
            print(f"Error uploading MP3 voice: {str(e)}")
            return jsonify(success=False, error=str(e)), 500
        
    @boundary.route("/serve_published_video/<file_id>")
    def serve_published_video(file_id):
        try:
            print(f"🔍 Streaming GridFS file directly: {file_id}")
            file = get_fs().get(ObjectId(file_id))
            return send_file(file, mimetype="video/mp4", as_attachment=False)
        except Exception as e:
            print(f"Error streaming video: {e}")
            return jsonify(success=False, error=str(e)), 404

    
    #This function is used to publish the video to the homepage (1 video 1 avatar)
    @boundary.route("/publish_video/<video_id>", methods=["POST"])
    def publish_video(video_id):
        try:
            username = session.get("username")
            if not username:
                flash("You must be logged in.", "danger")
                return redirect(url_for("boundary.login"))

            video_oid = ObjectId(video_id)  # 🔧 Always treat as ObjectId for GridFS keys

            # First: Try finding the video in tempvideo (drafts use 'video_id' field)
            temp_video = mongo.db.tempvideo.find_one({"video_id": video_oid, "username": username})

            if temp_video:
                avatar_id = temp_video.get("avatar_id")

                # ✅ Prevent duplicate publishes for same avatar
                existing = mongo.db.generated_videos.find_one({
                    "username": username,
                    "avatar_id": avatar_id,
                    "is_published": True
                })

                if existing:
                    flash("You already have a published video using this avatar.", "warning")
                    return redirect(url_for("boundary.my_videos"))

                # ✅ Move from temp to generated
                new_video = dict(temp_video)
                new_video.pop("_id", None)
                new_video["is_published"] = True
                new_video["published_at"] = datetime.utcnow()

                mongo.db.generated_videos.insert_one(new_video)
                mongo.db.tempvideo.delete_one({"video_id": video_oid, "username": username})

                flash("Draft video published successfully!", "success")
                return redirect(url_for("boundary.my_videos"))

            # Second: Try updating directly in generated_videos (already published once)
            video = mongo.db.generated_videos.find_one({"_id": video_oid, "username": username})
            if video:
                avatar_id = video.get("avatar_id")

                existing = mongo.db.generated_videos.find_one({
                    "username": username,
                    "avatar_id": avatar_id,
                    "is_published": True,
                    "_id": {"$ne": video_oid}
                })

                if existing:
                    flash("You already have a published video using this avatar.", "warning")
                    return redirect(url_for("boundary.my_videos"))

                mongo.db.generated_videos.update_one(
                    {"_id": video_oid},
                    {"$set": {"is_published": True}}
                )
                flash("Video published successfully!", "success")
            else:
                flash("Video not found.", "danger")

        except Exception as e:
            print("[Publish Error]", e)
            flash("An error occurred while publishing the video.", "danger")

        return redirect(url_for("boundary.my_videos"))


        
    @boundary.route("/unpublish_video/<video_id>", methods=["POST"])
    def unpublish_video(video_id):
        try:
            username = session.get("username")
            if not username:
                flash("You must be logged in to perform this action.", "danger")
                return redirect(url_for("boundary.login"))

            result = mongo.db.generated_videos.update_one(
                {"_id": ObjectId(video_id), "username": username},
                {"$set": {"is_published": False}}
            )

            if result.modified_count == 0:
                flash("Video not found or already unpublished.", "warning")
            else:
                flash("Video unpublished successfully!", "success")

        except Exception as e:
            logging.error(f"Unpublish Error: {e}")
            flash(f"Failed to unpublish video: {str(e)}", "danger")

        return redirect(url_for("boundary.my_videos"))

    @boundary.route('/download_video/<video_id>')
    def download_video(video_id):
        try:
            fs = GridFS(mongo.db)  # ✅ Use the whole database, not a collection
            file = get_fs().get(ObjectId(video_id))  # This must be the GridFS file's _id
            return send_file(
                io.BytesIO(file.read()),
                download_name=f"{file.filename or 'video'}.mp4",
                mimetype='video/mp4',
                as_attachment=True
            )
        except Exception as e:
            logging.error(f"Download error: {e}")
            abort(500)



        
    @boundary.route("/search_video", methods=["POST"])
    def search_video():
        search_query = request.form.get("search_query", "").strip()
        username = session.get("username")

        if not search_query:
            return redirect(url_for("boundary.my_videos"))

        # Search in the video collection
        videos = list(mongo.db.generated_videos.find({
            "$or": [
                {"text": {"$regex": search_query, "$options": "i"}},
                {"username": username}
            ]
        }))

        return render_template("myVideos.html", videos=videos, search_query=search_query, username=username)
    
    @boundary.route('/update_video_title/<video_id>', methods=['POST'])
    def update_video_title(video_id):
        if 'username' not in session:
            flash('Please login to update videos', 'error')
            return redirect(url_for('auth.login'))
        
        new_title = request.form.get('new_title')
        if not new_title:
            flash('Title cannot be empty', 'error')
            return redirect(url_for('boundary.my_videos'))
        
        try:
            print(f"🔍  Looking for video with _id={video_id} (type: {type(video_id)})")
            # Update only if video belongs to current user
            result = mongo.db.generated_videos.update_one(
                {
                    "video_id": ObjectId(video_id),  # Changed from _id to video_id
                    "username": session['username']
                },
                {"$set": {"title": request.form.get('new_title')}}
            )
            
            if result.modified_count == 1:
                flash('Title updated successfully', 'success')
            else:
                flash('Video not found or you do not have permission', 'error')
        except Exception as e:
            flash('Error updating title', 'error')
            print(f"Error: {str(e)}")
        
        return redirect(url_for('boundary.my_videos'))
 
# Log In
class LoginBoundary:
    @boundary.route('/login', methods=['GET', 'POST'])
    def login():
        if session.get('user_authenticated'):
            flash('You are already logged in.', category='info')
            return redirect(url_for('boundary.home'))
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')

            # Fetch user_info from DB
            user_info = mongo.db.useraccount.find_one({"username": username},{})

            if user_info:
                # Check user_info status
                if user_info.get('status') == 'suspended':
                    flash('Your account is suspended. Please contact admin.', category='error')
                    return redirect(url_for('boundary.login'))
                elif user_info.get('status') == 'deleted':
                    flash('This account has been deleted.', category='error')
                    return redirect(url_for('boundary.login'))

                # Validate password
                stored_hashed_password = user_info["password"]
                if check_password_hash(stored_hashed_password, password):
                    # Successful login for active users only
                    session['username'] = username
                    session['role'] = user_info['role']
                    session['user_authenticated'] = True
                    session['profile_pic'] = str(user_info['profile_pic']) if user_info.get('profile_pic') else None
                    flash(f'Login successful! You are logged in as {user_info["role"].capitalize()}.', category='success')
                    if user_info.get('first_time_login') == True:
                        admin_users = [u["username"] for u in mongo.db.useraccount.find({"role": "Admin"}, {"username": 1})]
                        
                        # Get all admin avatars with their associated videos
                        avatars = []
                        for avatar_doc in mongo.db.avatar.find({"username": {"$in": admin_users}}):
                            avatar_data = {
                                "username": avatar_doc.get("username"),
                                "avatarname": avatar_doc.get("avatarname"),
                                "image_data": avatar_doc.get("image_data"),
                                "avatar_id" : str(avatar_doc.get('_id')),
                                "video_id": None
                            }
                            
                            # Find associated published video
                            file_id = avatar_doc.get('file_id')
                            if file_id:
                                
                                video = mongo.db.generated_videos.find_one({
                                    "avatar_id": file_id,
                                    "is_published": True
                                })
                                if video:
                                    avatar_data["video_id"] = str(video.get("_id"))
                            
                            avatars.append(avatar_data)
                            for avatar in avatars:
                                print(f"Avatar: {avatar['avatarname']}, Video ID: {avatar['video_id']} avatar_id: {avatar['avatar_id']}")
                        return render_template("first_time_login.html", username=username,avatars=avatars,video=video)
                    else:
                        return redirect(url_for('boundary.home'))
                else:
                    flash('Wrong password.', category='error')
            else:
                flash('Username does not exist.', category='error')

        return render_template("login.html")
    
    @boundary.route('/select_avatar/<avatar_id>', methods=['POST'])
    def select_avatar(avatar_id):
        username = session.get('username')
        if not username:
            return jsonify(success=False, message='User not logged in'), 401

        tts_voice = request.form.get("tts_voice", "female_en")  # Default fallback

        try:
            session['selected_avatar'] = avatar_id

            result = mongo.db.useraccount.update_one(
                {"username": username},
                {"$set": {
                    "assistant": {
                        "avatar_id": str(avatar_id),
                        "tts_voice": tts_voice
                    }
                }}
            )

            if result.modified_count == 1:
                return redirect(url_for('boundary.home'))
            else:
                return jsonify(success=False, message='Failed to update user record'), 500

        except Exception as e:
            print("[ERROR] Failed to select avatar:", str(e))
            return jsonify(success=False, message='Server error'), 500



    
# Profile Pic    
@boundary.route('/profile_pic/<file_id>')
def get_profile_pic(file_id):
    try:
        file = get_fs().get(ObjectId(file_id))
        return send_file(file, mimetype=file.content_type or 'image/jpeg')
    except Exception as e:
        print(f"Error retrieving profile picture: {e}")
        return "Image not found", 404



# Log Out
class LogoutBoundary:
    @boundary.route('/logout')
    def logout():
        session.clear()
        flash("You have been logged out.", category="info")
        return redirect(url_for('boundary.home'))

# Create Account
class CreateAccountBoundary:
    @boundary.route('/createAccount', methods=['GET', 'POST'])
    def sign_up():
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            name = request.form.get('name')
            surname = request.form.get('surname')
            date_of_birth = request.form.get('date_of_birth')
            password1 = request.form.get('password1')
            password2 = request.form.get('password2')
            role = request.form.get('role')  # May be None
            profile_pic = request.files.get('profile_pic')

            is_admin = session.get("role") == "Admin"
            is_teacher = session.get("role") == "Teacher"

            # Set default role if not selected
            if not role:
                if is_teacher:
                    role = "Student"
                elif is_admin:
                    role = "Admin"
                else:
                    role = "Teacher"  # Self-registered defaults to teacher request

            # Validation
            if mongo.db.useraccount.find_one({"username": username}):
                flash("Username already taken.", "error")
                return redirect(url_for('boundary.sign_up'))
            if mongo.db.useraccount.find_one({"email": email}):
                flash("Email already registered.", "error")
                return redirect(url_for('boundary.sign_up'))
            if password1 != password2:
                flash("Passwords do not match.", "error")
                return redirect(url_for('boundary.sign_up'))
            if len(password1) < 7:
                flash("Password must be at least 7 characters.", "error")
                return redirect(url_for('boundary.sign_up'))

            # Upload profile picture to GridFS
            profile_pic_id = None
            if profile_pic and profile_pic.filename != "":
                try:
                    filename = secure_filename(f"{username}_{profile_pic.filename}")
                    profile_pic_id = get_fs().put(profile_pic, filename=filename, content_type=profile_pic.content_type)
                except Exception as e:
                    flash(f"Failed to upload profile picture: {str(e)}", "error")
                    return redirect(url_for('boundary.sign_up'))

            # Prepare user data
            hashed_pw = generate_password_hash(password1)
            dob_obj = datetime.strptime(date_of_birth, '%Y-%m-%d')

            user_data = {
                "username": username,
                "password": password1,  # Let controller hash
                "email": email,
                "name": name,
                "surname": surname,
                "date_of_birth": dob_obj.strftime('%Y-%m-%d'),
                "role": role,
                "profile_pic": profile_pic_id,
                "registered_by": session.get("role") if session.get("role") else None
            }

            # Delegate to Controller
            success = CreateUserAccController.register_user(user_data)

            if success:
                flash(f"Account created successfully with role: {role}", "success")
                return redirect(url_for('boundary.login'))
            else:
                flash("Failed to create account.", "error")

        is_admin = session.get("role") == "Admin"
        return render_template("createAccount.html", is_admin=is_admin)

    @boundary.route('/accountDetails', methods=['GET'])
    def accDetails():
        if 'username' not in session:
            flash("You must be logged in to view account details.", category='error')
            return redirect(url_for('boundary.login'))
    
        username = session['username']
        user_info = DisplayUserDetailController.get_user_info(username)
    
        current_avatar = None
        if user_info and user_info.get("assistant") and user_info["assistant"].get("avatar_id"):
            try:
                current_avatar = mongo.db.avatar.find_one({"_id": ObjectId(user_info["assistant"]["avatar_id"])})
            except Exception as e:
                print(f"⚠️ Failed to fetch avatar: {e}")
    
        return render_template("accountDetails.html", user_info=user_info, current_avatar=current_avatar)



# Edit Account Details
class UpdateAccountBoundary:
    @boundary.route('/update_account_detail', methods=['GET', 'POST'])
    def update_account_detail():
        if 'username' not in session:
            flash("You must be logged in to update your account.", category='error')
            return redirect(url_for('boundary.login'))

        username = session['username']
        user_info = UpdateAccountDetailController.get_user_by_username(username)

        if not user_info:
            flash("User not found.", category='error')
            return redirect(url_for('boundary.accDetails'))

        if request.method == 'POST':
            update_data = {}

            name = request.form.get("name")
            surname = request.form.get("surname")
            date_of_birth = request.form.get("date_of_birth")
            profile_picture = request.files.get("profile_picture")

            if name:
                update_data["name"] = name
            if surname:
                update_data["surname"] = surname
            if date_of_birth:
                update_data["date_of_birth"] = date_of_birth

            # ✅ Save new profile picture to GridFS if uploaded
            if profile_picture and profile_picture.filename != "":
                try:
                    filename = secure_filename(f"{username}_updated_profile_{profile_picture.filename}")
                    file_id = get_fs().put(profile_picture, filename=filename, content_type=profile_picture.content_type)
                    update_data["profile_pic"] = file_id
                except Exception as e:
                    flash(f"Failed to update profile picture: {str(e)}", category="error")
                    return redirect(url_for('boundary.update_account_detail'))

            if update_data:
                success = UpdateAccountDetailController.update_account_detail(username, update_data)
                if success:
                    flash("Account updated successfully!", category='success')
                else:
                    flash("No changes detected.", category='info')
            else:
                flash("No data provided for update.", category='info')

            return redirect(url_for('boundary.accDetails'))

        current_avatar = None
        if user_info.get("assistant"):
            try:
                current_avatar = mongo.db.avatar.find_one({"_id": ObjectId(user_info["assistant"])})
            except Exception as e:
                print("⚠️ Assistant avatar lookup failed:", e)

        return render_template("updateAccDetail.html", user_info=user_info, current_avatar=current_avatar)

# Change Avatar Assistant 
class ChangeAssistantBoundary:
    @boundary.route('/change_assistant', methods=['GET', 'POST'])
    def change_assistant():
        if 'username' not in session:
            flash("You must be logged in to change your assistant.", category='error')
            return redirect(url_for('boundary.login'))

        username = session['username']
        user_info = mongo.db.useraccount.find_one({"username": username})

        if not user_info:
            flash("User not found.", category='error')
            return redirect(url_for('boundary.accDetails'))

        if request.method == 'POST':
            new_avatar_id = request.form.get("avatar_id")
            tts_voice = request.form.get("tts_voice", "female_en")

            if new_avatar_id:
                assistant_data = {
                    "avatar_id": ObjectId(new_avatar_id),
                    "tts_voice": tts_voice
                }
                update_result = mongo.db.useraccount.update_one(
                    {"username": username},
                    {"$set": {"assistant": assistant_data}}
                )
                if update_result.modified_count > 0:
                    flash("Assistant updated successfully!", category='success')
                else:
                    flash("Failed to update assistant. Try again.", category='error')
            else:
                flash("No avatar selected.", category='error')

            return redirect(url_for('boundary.accDetails'))

        

        # Fetch avatars uploaded by admins and the user
        admin_users = list(mongo.db.useraccount.find({"role": "Admin"}, {"username": 1}))
        admin_usernames = [u['username'] for u in admin_users]

        admin_avatars = list(mongo.db.avatar.find({"username": {"$in": admin_usernames}}))
        user_avatars = list(mongo.db.avatar.find({"username": username}))

        # Merge, filter duplicates and ensure image_data exists
        unique_ids = set()
        avatars = []
        for avatar in admin_avatars + user_avatars:
            if avatar["_id"] not in unique_ids and avatar.get("image_data"):
                avatars.append(avatar)
                unique_ids.add(avatar["_id"])

        tts_options = [
                "female_en",
                "female_es",
                "female_fr",
                "female_id",
                "female_ja"
            ]
        return render_template("changeAssistant.html", avatars=avatars, user_info=user_info, tts_options=tts_options)

    @boundary.route('/set_first_time_login_false', methods=['POST'])
    def set_first_time_login_false():   
        if 'username' not in session:
            flash("You must be logged in to change your assistant.", category='error')
            return redirect(url_for('boundary.login'))

        username = session['username']
        user_info = mongo.db.useraccount.find_one({"username": username})

        if not user_info:
            flash("User not found.", category='error')
            return redirect(url_for('boundary.accDetails'))

        update_result = mongo.db.useraccount.update_one(
            {"username": username},
            {"$set": {"first_time_login": False}}
        )
        if update_result.modified_count > 0:
            flash("First time login status updated successfully!", category='success')
        else:
            flash("Failed to update first time login status. Try again.", category='error')

        return redirect(url_for('boundary.home'))


# Update Password
class UpdatePasswordBoundary:
    @boundary.route('/update_password', methods=['GET', 'POST'])
    def update_password():
        if 'username' not in session:
            flash("You must be logged in to change your password.", category='error')
            return redirect(url_for('boundary.login'))

        username = session['username']
        user_info = mongo.db.useraccount.find_one({"username": username})

        if not user_info:
            flash("User not found.", category='error')
            return redirect(url_for('boundary.accDetails'))

        if request.method == 'POST':
            old_password = request.form.get("old_password")
            new_password = request.form.get("new_password")
            confirm_password = request.form.get("confirm_password")

            stored_hashed_password = user_info.get("password")

            if not check_password_hash(stored_hashed_password, old_password):
                flash("Incorrect current password.", category='error')
                return redirect(url_for('boundary.update_password'))

            if new_password != confirm_password:
                flash("New passwords do not match.", category='error')
                return redirect(url_for('boundary.update_password'))

            if len(new_password) < 7:
                flash("New password must be at least 7 characters long.", category='error')
                return redirect(url_for('boundary.update_password'))

            hashed_new_password = generate_password_hash(new_password)
            update_result = mongo.db.useraccount.update_one(
                {"username": username},
                {"$set": {"password": hashed_new_password}}
            )

            if update_result.modified_count > 0:
                flash("Password updated successfully!", category='success')
                return redirect(url_for('boundary.accDetails'))
            else:
                flash("Failed to update password. Try again.", category='error')

        # 🔥 FIX: Pass user_info to template
        return render_template("updatePassword.html", user_info=user_info)

# Reset Password
class ResetPasswordBoundary:
    @boundary.route('/resetPassword', methods=['GET', 'POST'])
    def reset_password():
        if request.method == 'POST':
            username = request.form.get("username")
            new_password = request.form.get("new_password")
            if len(new_password) < 7:
                flash("Password must be at least 7 characters long.", category="error")
                return redirect(url_for("boundary.reset_password"))
            if ResetPasswordController.reset_password(username, new_password):
                flash(f"Password reset for {username}.", category="success")
            else:
                flash("Failed to reset password. Ensure the username exists.", category="error")
            return redirect(url_for("boundary.reset_password"))
        return render_template("resetPassword.html")

# Search     
class SearchBoundary:
    @boundary.route('/search', methods=['GET'])
    def search():
        search_query = request.args.get('query', '').strip()
        filter_type = request.args.get('filter', 'video').lower()

        print(f"[SEARCH] Received query: '{search_query}' | Filter: '{filter_type}'")

        if not search_query:
            flash("Please enter a search query.", category="error")
            return redirect(url_for('boundary.home'))

        if filter_type == 'video':
            search_results = SearchTutorialController.search_video(search_query)

            for v in search_results:
                v["video_name"] = v.get("video_name", "")
                v["title"] = v.get("title", "Untitled")
                v["description"] = v.get("description", "No description")
                v["username"] = v.get("username", "Unknown")

                # ✅ Safely convert file_id or fallback _id
                raw_file_id = v.get("file_id") or v.get("_id")
                if raw_file_id:
                    v["file_id"] = str(raw_file_id)
                else:
                    print("⚠️ Missing file_id for search result:", v)

                            
        elif filter_type == 'avatar':
            search_results = SearchAvatarController.search_avatar(search_query)
            for a in search_results:
                a["avatarname"] = a.get("avatarname", "Unnamed")
                a["file_path"] = a.get("file_path", "")  # Ensure this is a valid relative static path
        else:
            flash("Invalid filter type.", category="error")
            return redirect(url_for('boundary.home'))

        if not search_results:
            flash(f"No {filter_type} results found.", category="info")
        else:
            print(f"[SEARCH] Found {len(search_results)} {filter_type} results.")

        return render_template(
            "search.html",
            search_results=search_results,
            filter_type=filter_type,
            search_query=search_query
        )



# -------------------------------------------------------------ADMIN-----------------------------------------------
# Admin Confirm Teacher
class ConfirmTeacherBoundary:
    @boundary.route('/confirmTeacher/', methods=['GET', 'POST'])
    def confirm_teacher_page():
        if session.get('role') != "Admin":
            flash("Access Denied! Only Admins can confirm teachers.", category="error")
            return redirect(url_for("boundary.home"))

        # Show users with pending approval
        users = list(mongo.db.useraccount.find(
            {"role": "User"},
            {"_id": 0, "username": 1, "email": 1, "certificate": 1}
        ))
        return render_template("confirmTeacher.html", users=users)

    @boundary.route('/confirmTeacher/<username>', methods=['POST'])
    def confirm_teacher(username):
        if session.get('role') != "Admin":
            flash("Access Denied!", category="error")
            return redirect(url_for("boundary.home"))

        update_result = mongo.db.useraccount.update_one(
            {"username": username, "role": "User"},
            {
                "$set": {"role": "Teacher"}
            }
        )

        if update_result.modified_count > 0:
            flash(f"{username} is now a Teacher!", category="success")
        else:
            flash("Failed to confirm. Ensure the username exists and is pending approval.", category="error")

        return redirect(url_for("boundary.confirm_teacher_page"))


    
# Admin Upload Tutorial Video
class UploadTutorialBoundary:
    UPLOAD_FOLDER_VIDEO = 'FYP25S109/static/uploads/videos/'
    ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in UploadTutorialBoundary.ALLOWED_EXTENSIONS

    @boundary.route('/uploadTutorial', methods=['GET', 'POST'])
    def upload_tutorial():
        if 'username' not in session:
            flash("You must be logged in to upload a tutorial video.", category='error')
            return redirect(url_for('boundary.login'))

        if request.method == 'POST':
            file = request.files.get('file')
            title = request.form.get("title")
            username = session.get("username")
            description = request.form.get("description")

            if not title:
                flash("Please provide a title for the video.", category='error')
                return redirect(url_for('boundary.upload_tutorial'))

            if not file or file.filename == '':
                flash("No file selected. Please upload a video file.", category='error')
                return redirect(url_for('boundary.upload_tutorial'))

            if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() not in UploadTutorialBoundary.ALLOWED_EXTENSIONS:
                flash("Invalid file type. Please upload a valid video file.", category='error')
                return redirect(url_for('boundary.upload_tutorial'))
            
            video = UploadTutorialController.upload_video(file, title, username, description)

            if video['success']:
                flash("Video uploaded successfully!", category='success')
                return redirect(url_for('boundary.view_uploaded_videos'))
            else:
                flash(f"Failed to upload video: {video['message']}", category='error')
                return redirect(url_for('boundary.upload_tutorial'))

        # 👇 Handle GET request (return the upload form)
        return render_template("uploadTutorial.html")

# View Uploaded Videos (Multiple Videos at one time)
class ViewUploadedVideosBoundary:
    @boundary.route('/video/<file_id>', endpoint='serve_video')
    def serve_video(file_id):
        try:
            grid_out = get_fs().get(ObjectId(file_id))
            file_size = grid_out.length
            range_header = request.headers.get('Range')

            if range_header:
                start, end = range_header.replace('bytes=', '').split('-')
                start = int(start)
                end = int(end) if end else file_size - 1
                length = end - start + 1

                grid_out.seek(start)  # Move to the requested byte position
                data = grid_out.read(length)

                response = Response(data, status=206, mimetype=grid_out.content_type)
                response.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
                response.headers.add('Accept-Ranges', 'bytes')
                response.headers.add('Content-Length', str(length))
                return response

            # Full video response (if no Range header)
            return Response(grid_out.read(), mimetype=grid_out.content_type)

        except Exception as e:
            logging.error(f"Failed to serve video: {str(e)}")
            return "Video not found", 404
        
        
    @boundary.route('/uploadedVideos', methods=['GET'])
    def view_uploaded_videos():
        if 'username' not in session:
            flash("You must be logged in to view uploaded videos.", category='error')
            return redirect(url_for('boundary.login'))
        admin_videos = list(mongo.db.tutorialvideo.find(
            {"username": session['username']},
            {}
        ))
        return render_template("manageVideo.html", videos=admin_videos)
    

# View Uploaded Videos (Single Video)
class ViewSingleTutorialBoundary:
    @boundary.route('/viewTutorial/<video_name>', methods=['GET'])
    def view_tutorial(video_name):
        video = mongo.db.tutorialvideo.find_one({"video_name": video_name})
        if not video:
            flash("Video not found.", category='error')
            return redirect(url_for('boundary.home'))
        return render_template("viewTutorial.html", video=video)

#Delete Video
class DeleteUploadedVideosBoundary:
    @boundary.route('/deleteVideo/<video_name>', methods=['POST'])
    def delete_video(video_name):
        if 'username' not in session:
            flash("You must be logged in to delete a video.", category='error')
            return redirect(url_for('boundary.login'))
        video = mongo.db.tutorialvideo.find_one({"video_name": video_name})
        if not video:
            flash("Video not found.", category='error')
            return redirect(url_for('boundary.view_uploaded_videos'))
        try:
            mongo.db.tutorialvideo.delete_one({"video_name": video_name})
            flash("Video deleted successfully.", category='success')
        except Exception as e:
            flash(f"Failed to delete video: {str(e)}", category='error')
        return redirect(url_for('boundary.view_uploaded_videos'))

# Manage Avatar
class ManageAvatarBoundary:
    @boundary.route('/manage_avatars')
    def manage_avatars():
        if 'username' not in session:
            flash("You must be logged in to manage your avatar.", category='error')
            return redirect(url_for('boundary.login'))
        username = session.get('username')
        user_role = session.get('role')
        avatars = ManageAvatarController.get_avatars_by_username(username)
        if not avatars:
            flash("No avatars found for your account.", category='info')
        return render_template(
            "manage_avatars.html",
            username=username,
            user_role=user_role,
            avatars=avatars
        )

# Add Avatar
class AddAvatarBoundary:
    UPLOAD_FOLDER_AVATAR = 'FYP25S109/static/uploads/avatar/'

    @boundary.route('/create_avatar', methods=['GET', 'POST'])
    def create_avatar():
        if 'username' not in session:
            flash("You must be logged in to create an avatar.", category='error')
            return redirect(url_for('boundary.login'))

        if request.method == 'POST':
            username = session.get('username')
            avatar_file = request.files.get('avatar')
            avatarname = request.form.get('avatarname')  # ✅ Capture avatar name

            if not username or not avatar_file or not avatarname:
                flash("Username, avatar name, and avatar file are required.", category='error')
                return redirect(url_for('boundary.create_avatar'))

            result = AddAvatarController.add_avatar(username, avatarname, avatar_file)

            if result['success']:
                flash("Avatar added successfully.", category='success')
            else:
                flash(f"Failed to add avatar: {result['message']}", category='error')

            return redirect(url_for('boundary.create_avatar'))

        return render_template("addAvatar.html")

# Delete Avatar    
class DeleteAvatarBoundary:
    @boundary.route('/admin_delete_avatar/<avatar_id>', methods=['POST'])
    def delete_avatar(avatar_id):
        if 'username' not in session:
            flash("You must be logged in to delete an avatar.", category='error')
            return redirect(url_for('boundary.login'))
        avatar = Avatar.find_by_id(avatar_id)
        if not avatar:
            flash("Avatar not found.", category='error')
            return redirect(url_for('boundary.manage_avatars'))
        if DeleteAvatarController.delete_avatar(avatar_id):
            flash("Avatar deleted successfully.", category='success')
        else:
            flash("Failed to delete avatar.", category='error')
        return redirect(url_for('boundary.manage_avatars'))
    
# Admin Manage User
class ManageUserBoundary:
    @boundary.route('/admin/manageUsers', methods=['GET'])
    def manage_users():
        # Ensure only admins can access this page
        if 'role' not in session or session.get('role') != 'Admin':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        # Fetch all users
        users = list(mongo.db.useraccount.find({}, {"_id": 0, "username": 1, "email": 1, "role": 1, "status": 1}))
        return render_template("manageUsers.html", users=users)

    @boundary.route('/admin/searchUser', methods=['GET'])
    def search_user():
        if 'role' not in session or session.get('role') != 'Admin':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        query = request.args.get('query', '')
        users = SearchAccountController.search_account(query)
        
        return render_template("manageUsers.html", users=users)

    @boundary.route('/admin/suspendUser/<username>', methods=['POST'])
    def suspend_user(username):
        if 'role' not in session or session.get('role') != 'Admin':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        result = mongo.db.useraccount.update_one(
            {"username": username},
            {"$set": {"status": "suspended"}}
        )

        if result.modified_count:
            flash(f"User {username} suspended successfully.", category='success')
        else:
            flash("User not found or already suspended.", category='error')

        return redirect(url_for('boundary.manage_users'))

# Delete User 
    @boundary.route('/admin/deleteUser/<username>', methods=['POST'])
    def delete_user(username):
        if 'role' not in session or session.get('role') != 'Admin':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        # Prevent self-deletion
        if username == session.get('username'):
            flash("You cannot delete your own account.", category='error')
            return redirect(url_for('ManageUserBoundary.manage_users'))

        # Permanently delete user_info from DB
        user = mongo.db.useraccount.find_one({"username": username})
        if not user:
            flash("User not found.", category='error')
            return redirect(url_for('boundary.manage_users'))

        # Delete related avatars
        mongo.db.avatar.delete_many({"username": username})

        # Remove student from all classroom lists
        mongo.db.classroom.update_many(
            {"student_list": username},
            {"$pull": {"student_list": username}}
        )

        # Finally, delete the user
        result = mongo.db.useraccount.delete_one({"username": username})

        if result.deleted_count:
            flash(f"User {username} and their related data deleted.", category='success')
        else:
            flash("Failed to delete user.", category='error')

        return redirect(url_for('boundary.manage_users'))


# Reactivate User
    @boundary.route('/admin/activateUser/<username>', methods=['POST'])
    def activate_user(username):
        if 'role' not in session or session.get('role') != 'Admin':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        result = mongo.db.useraccount.update_one(
            {"username": username},
            {"$set": {"status": "active"}}
        )

        if result.modified_count:
            flash(f"User {username} reactivated successfully.", category='success')
        else:
            flash("Failed to reactivate user_info.", category='error')

        return redirect(url_for('boundary.manage_users'))
    
# -------------------------------------------------------------TEACHER-----------------------------------------------
# Teacher manage classrooms
class TeacherManageClassroomsBoundary:
    @boundary.route('/teacher/manageClassrooms', methods=['GET'])
    def manage_classrooms():
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))
        username = session.get('username')
        classrooms = list(mongo.db.classroom.find({"teacher": username}))
        return render_template("manageClassrooms.html", classrooms=classrooms)

# Add Classroom
class TeacherAddClassroomBoundary:
    @boundary.route('/teacher/addClassroom', methods=['GET', 'POST'])
    def add_classroom():
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        if request.method == 'POST':
            teacher = session.get('username')
            classroom_name = request.form.get('classroom_name')
            classroom_description = request.form.get('classroom_description')
            classroom_capacity = request.form.get('classroom_capacity')

            if not classroom_name:
                flash("Classroom name is required.", category='error')
                return redirect(url_for('boundary.add_classroom'))

            controller = AddClassroomController()
            result = controller.create_classroom(classroom_name, teacher, classroom_description, classroom_capacity)

            if result['success']:
                flash(result['message'], category='success')
                return redirect(url_for('boundary.manage_classrooms'))
            else:
                flash(result['message'], category='error')

        return render_template("addClassroom.html")

# View Classroom
class ViewClassRoomBoundary:
    @boundary.route('/viewClassroom/<classroom_id>', methods=['GET', 'POST'])
    def view_classroom(classroom_id):
        if 'role' not in session or session.get('role') not in ['Teacher', 'Student']:
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        # Fetch the classroom details
        classroom = mongo.db.classroom.find_one({"_id": ObjectId(classroom_id)})
        if not classroom:
            flash("Classroom not found.", category='error')
            return redirect(url_for('boundary.manage_classrooms'))

        # Role-based access control
        username = session.get('username')
        if session.get('role') == 'Student':
            student_list = classroom.get('student_list', [])
            if username.strip() not in [s.strip() for s in student_list]:
                flash("You are not enrolled in this classroom.", category='error')
                return redirect(url_for('boundary.home'))

        elif session.get('role') == 'Teacher':
            if username.strip() != classroom.get('teacher', '').strip():
                flash("You are not the teacher of this classroom.", category='error')
                return redirect(url_for('boundary.home'))
        # Fetch classroom data
        materials = list(mongo.db.materials.find({"classroom_id": ObjectId(classroom_id)}))
        assignments = list(mongo.db.assignments.find({"classroom_id": ObjectId(classroom_id)}))
        quizzes = list(mongo.db.quizzes.find({"classroom_id": ObjectId(classroom_id)}))

        # ✅ Fetch announcements for this classroom
        announcements = list(mongo.db.announcements.find(
            {"classroom_id": ObjectId(classroom_id)},
            {"_id": 0, "title": 1, "content": 1, "created_at": 1}
        ))

        # Convert due_date to readable format
        for assignment in assignments:
            if "due_date" in assignment and assignment["due_date"]:
                try:
                    assignment["due_date"] = datetime.strptime(assignment["due_date"], "%Y-%m-%dT%H:%M").strftime("%d %b %Y, %I:%M %p")
                except ValueError:
                    pass  # Keep as-is if conversion fails

        return render_template(
            "viewClassroom.html",
            classroom=classroom,
            materials=materials,
            assignments=assignments,
            quizzes=quizzes,
            announcements=announcements
        )


# Delete Classroom
class TeacherDeleteClassroomBoundary:
    @boundary.route('/teacher/deleteClassroom/<classroom_id>', methods=['POST'])
    def delete_classroom(classroom_id):
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        result = mongo.db.classroom.delete_one({"_id": ObjectId(classroom_id)})

        if result.deleted_count:
            flash(f"Classroom deleted successfully.", category='success')
        else:
            flash("Classroom not found.", category='error')

        return redirect(url_for('boundary.manage_classrooms'))

# Update classroom
class TeacherUpdateClassroomBoundary:
    @boundary.route('/teacher/updateClassroom/<classroom_id>', methods=['GET', 'POST'])
    def update_classroom(classroom_id):
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        classroom = mongo.db.classroom.find_one({"_id": ObjectId(classroom_id)})

        if not classroom:
            flash("Classroom not found.", category='error')
            return redirect(url_for('boundary.manage_classrooms'))

        if request.method == 'POST':
            new_classroom_name = request.form.get('classroom_name')
            new_description = request.form.get('classroom_description')
            new_capacity = request.form.get('classroom_capacity')

            if not new_classroom_name:
                flash("Classroom name is required.", category='error')
                return redirect(url_for('boundary.update_classroom', classroom_id=classroom_id))

            result = UpdateClassroomController.update_classroom(ObjectId(classroom_id), new_details={
                "classroom_name": new_classroom_name,
                "description": new_description,
                "capacity": new_capacity
            })

            return redirect(url_for('boundary.manage_classrooms'))

        return render_template("updateClassroom.html", classroom=classroom)

# Search Classroom
class TeacherSearchClassroomBoundary:
    @boundary.route('/teacher/searchClassroom', methods=['GET', 'POST'])
    def search_classroom():
        query = request.args.get('query', '').strip() if request.method == 'GET' else request.form.get('query', '').strip()
        classrooms = SearchClassroomController.search_classroom(query)

        return render_template("ClassroomSearchResult.html", classrooms=classrooms, query=query)

# Manage Student
class TeacherManageStudentsBoundary:
    @boundary.route('/teacher/manageStudents/<classroom_id>', methods=['GET', 'POST'])
    def manage_students(classroom_id):
        # Retrieve classroom document using classroom_id
        classroom = mongo.db.classroom.find_one({"_id": ObjectId(classroom_id)})

        if not classroom:
            flash("Classroom not found.", category='error')
            return redirect(url_for('boundary.manage_classrooms'))

        # Extract student usernames from the classroom's 'student_list' array
        enrolled_usernames = classroom.get('student_list', [])

        # Fetch all students from the useraccount collection
        all_students = list(mongo.db.useraccount.find({"role": "Student"}))

        # Separate enrolled and unenrolled students
        enrolled_students = []
        unenrolled_students = []

        for student in all_students:
            student['_id'] = str(student['_id'])  # Ensure _id is a string
            student['status'] = student.get('status', False)  # Ensure key exists
            
            if student['username'] in enrolled_usernames:
                enrolled_students.append(student)
            else:
                unenrolled_students.append(student)

        # Render the template with enrolled and unenrolled students
        return render_template(
            "manageStudents.html",
            classroom=classroom,
            enrolled_students=enrolled_students,
            unenrolled_students=unenrolled_students
        )

    @boundary.route('/teacher/enrollStudent/<classroom_id>', methods=['POST'])
    def enroll_student(classroom_id):
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        if request.method == 'POST':
            student_username = request.form.get('username')

            if not student_username:
                flash("Username cannot be empty.", category='error')
                return redirect(url_for('boundary.manage_students', classroom_id=classroom_id))

            # Call the controller to handle enrollment
            result = EnrollStudentController.enroll_student(classroom_id, student_username)
            if result["success"]:
                flash(result["message"], category='success')
            else:
                flash(result["message"], category='error')

        return redirect(url_for('boundary.manage_students', classroom_id=classroom_id))

    @boundary.route('/teacher/removeStudent/<classroom_id>', methods=['POST'])
    def remove_student(classroom_id):
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        if request.method == 'POST':
            student_username = request.form.get('username')

            if not student_username:
                flash("Username cannot be empty.", category='error')
                return redirect(url_for('boundary.manage_students', classroom_id=classroom_id))

            # Call the controller to handle removal
            result = RemoveStudentController.remove_student(classroom_id, student_username)
            if result["success"]:
                flash(result["message"], category='success')
            else:
                flash(result["message"], category='error')

        return redirect(url_for('boundary.manage_students', classroom_id=classroom_id))

    
    @boundary.route('/teacher/suspendStudent/<classroom_id>', methods=['POST'])
    def suspend_student(classroom_id):
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        student_username = request.form.get('username')
        if not student_username:
            flash("Username cannot be empty.", category='error')
            return redirect(url_for('boundary.manage_students', classroom_id=classroom_id))

        # Call the Controller to handle suspension
        result = SuspendStudentController.suspend_student(classroom_id, student_username)

        flash(result['message'], category='success' if result['success'] else 'error')
        return redirect(url_for('boundary.manage_students', classroom_id=classroom_id))

    @boundary.route('/teacher/unsuspendStudent/<classroom_id>', methods=['POST'])
    def unsuspend_student(classroom_id):
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        student_username = request.form.get('username')
        if not student_username:
            flash("Username cannot be empty.", category='error')
            return redirect(url_for('boundary.manage_students', classroom_id=classroom_id))

        # Call the Controller to handle unsuspension
        result = UnsuspendStudentController.unsuspend_student(classroom_id, student_username)

        flash(result['message'], category='success' if result['success'] else 'error')
        return redirect(url_for('boundary.manage_students', classroom_id=classroom_id))

    @boundary.route('/teacher/searchStudent/<classroom_id>', methods=['GET'])
    def search_student(classroom_id):
        query = request.args.get('query', '').strip()  # Get query from request parameters
        # Retrieve classroom document using classroom_id
        classroom = mongo.db.classroom.find_one({"_id": ObjectId(classroom_id)})
        if not classroom:
            flash("Classroom not found.", category='error')
            return redirect(url_for('boundary.manage_classrooms'))

        # Get enrolled usernames from the classroom
        enrolled_usernames = set(classroom.get('student_list', []))
        unenrolled_usernames = set(user_info['username'] for user_info in mongo.db.useraccount.find({"role": "Student"})) - enrolled_usernames

        # Fetch students that match the search query
        search_results = list(mongo.db.useraccount.find({
            "role": "Student",
            "$or": [
                {"username": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}}
            ]
        }))

        # Separate enrolled and unenrolled students
        enrolled_students = []
        unenrolled_students = []
        for student in search_results:
            student['_id'] = str(student['_id'])
            student['status'] = student.get('status', False)
            if student['username'] in enrolled_usernames:
                enrolled_students.append(student)
            elif student['username'] in unenrolled_usernames:
                unenrolled_students.append(student)

        # Render the search results page
        return render_template(
            "searchResultsStudents.html",
            classroom=classroom,
            enrolled_students=enrolled_students,
            unenrolled_students=unenrolled_students,
            query=query
        )

# Manage Material
class TeacherManageMaterialBoundary:
    @boundary.route('/upload_material', methods=['POST'])
    def upload_material():
        classroom_id = request.form.get('classroom_id')
        title = request.form.get('title')
        description = request.form.get('description')
        file = request.files.get('file')
        video_ids = request.form.getlist('video_ids')  # ✅ Fix field name and support list
        if not video_ids:
            single_video_id = request.form.get("video_id")
            if single_video_id:
                video_ids = [single_video_id]
        if not file:
            flash("Please upload a file.")
            return redirect(request.url)

        try:
            material_doc = {
                "classroom_id": ObjectId(classroom_id),
                "title": title,
                "description": description,
                "uploaded_by": session.get("username"),
                "uploaded_at": datetime.utcnow()
            }

            # ✅ File upload to GridFS
            fs = get_fs()
            file_id = fs.put(file, filename=file.filename)
            material_doc["file_id"] = file_id
            material_doc["file_name"] = file.filename

            published_video_ids = []

            for vid in video_ids:
                try:
                    vid_oid = ObjectId(vid)
                    temp = mongo.db.tempvideo.find_one({"video_id": vid_oid})
                    if temp:
                        temp["is_published"] = True
                        temp["published_at"] = datetime.utcnow()
                        temp.pop("_id", None)
                        mongo.db.generated_videos.insert_one(temp)
                        mongo.db.tempvideo.delete_one({"video_id": vid_oid})
                        published_video_ids.append(vid_oid)
                except Exception as e:
                    print(f"❌ Failed to publish video {vid}: {e}")

            if published_video_ids:
                material_doc["video_ids"] = published_video_ids

            mongo.db.materials.insert_one(material_doc)
            flash("Material uploaded successfully!", "success")
            return redirect(url_for('boundary.manage_materials', classroom_id=classroom_id))

        except Exception as e:
            flash(f"Error uploading material: {str(e)}", "danger")
            return redirect(request.url)


    @boundary.route("/upload_material")
    def upload_material_page():
        classroom_id = request.args.get("classroom_id")
        video_id = request.args.get("video_id")
        return render_template("uploadMaterial.html", classroom_id=classroom_id, video_id=video_id)


    
    @boundary.route('/manage_materials/<classroom_id>', methods=['GET'])
    def manage_materials(classroom_id):
        materials = mongo.db.materials.find({"classroom_id": ObjectId(classroom_id)})
        return render_template("manageMaterials.html", materials=materials, classroom_id=classroom_id)

    @boundary.route('/delete_material/<classroom_id>/<filename>', methods=['POST'])
    def delete_material(classroom_id, filename):
        mongo.db.materials.delete_one({"classroom_id": ObjectId(classroom_id), "file_name": filename})
        flash('Material deleted successfully!', 'success')
        return redirect(url_for('boundary.manage_materials', classroom_id=classroom_id))

    @boundary.route('/view_material/<material_id>/<classroom_id>', methods=['GET'])
    def view_material(material_id, classroom_id):
        material_controller = ViewMaterialController()
        material, file_data = material_controller.get_material(material_id)

        if not material:
            flash('Material not found!', 'danger')
            return redirect(url_for('boundary.manage_materials', classroom_id=classroom_id))

        file_content = file_data.read()
        file_extension = material['file_name'].split('.')[-1].lower()
        file_base64 = base64.b64encode(file_content).decode('utf-8')

        # ✅ Fetch attached videos if any
        video_previews = []
        if 'video_ids' in material:
            for vid in material['video_ids']:
                try:
                    video = mongo.db.generated_videos.find_one({'video_id': vid})
                    if video:
                        video_previews.append({
                            "video_id": str(video['video_id']),
                            "title": video.get("title", "Untitled Video")
                        })
                except:
                    pass

        return render_template("viewMaterial.html",
                               material_id=material['_id'],
                               filename=material['file_name'],
                               classroom_id=classroom_id,
                               file_base64=file_base64,
                               file_extension=file_extension,
                               text_content=file_content.decode('utf-8') if file_extension in ['txt', 'md'] else None,
                               video_previews=video_previews)  # ✅

    @boundary.route('/search_materials/<classroom_id>', methods=['GET'])
    def search_materials(classroom_id):
        query = request.args.get('search_query', '').strip()
        q = {"classroom_id": ObjectId(classroom_id)}
        if query:
            q["$or"] = [
                {"title": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}}
            ]
        materials = mongo.db.materials.find(q)
        return render_template('manageMaterials.html', materials=materials, classroom_id=classroom_id)

    @boundary.route('/teacher/download_material/<material_id>')
    def download_material(material_id):
        material = mongo.db.materials.find_one({"_id": ObjectId(material_id)})
        if not material:
            flash("Material not found!", "danger")
            return redirect(url_for("boundary.home"))

        try:
            fs = get_fs()
            file_data = fs.get(material["file_id"])
            return send_file(
                io.BytesIO(file_data.read()),
                mimetype=mimetypes.guess_type(material["file_name"])[0] or "application/octet-stream",
                as_attachment=True,
                download_name=material["file_name"]
            )
        except Exception as e:
            flash(f"Error downloading file: {str(e)}", "danger")
            return redirect(url_for("boundary.home"))

        
# View Quiz        
class TeacherViewQuizBoundary:
    @boundary.route('/teacher/view_quiz/<quiz_id>', methods=['GET'])
    def view_quiz(quiz_id):
        try:
            quiz = mongo.db.quizzes.find_one({"_id": ObjectId(quiz_id)})
        except:
            flash("Invalid quiz ID!", "danger")
            return redirect(url_for('boundary.manage_quizzes'))

        if not quiz:
            flash("Quiz not found!", "danger")
            return redirect(url_for('boundary.manage_quizzes'))

        return render_template("viewQuiz.html", quiz=quiz)

# View User Detail            
class ViewUserDetailsBoundary:
    @boundary.route('/userDetails/<username>', methods=['GET'])
    def view_user_details(username):
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        user_info = mongo.db.useraccount.find_one(
            {"username": username},
            {}
        )

        if not user_info:
            flash("User not found.", category='error')
            return redirect(url_for('boundary.home'))

        current_avatar = None
        if user_info.get("assistant"):
            try:
                current_avatar = mongo.db.avatar.find_one({"_id": ObjectId(user_info["assistant"])})
            except Exception as e:
                print("⚠️ Assistant avatar lookup failed:", e)

        return render_template("userDetails.html", user_info=user_info, current_avatar=current_avatar)
    

# ------------------------------------------------------------------------------------------------------- Upload Assignment
class TeacherAssignmentBoundary:
    @boundary.route('/teacher/upload_assignment/<classroom_id>', methods=['GET', 'POST'])
    def upload_assignment(classroom_id):
        if request.method == 'GET':
            meta_id = session.pop('stashed_video_id', None)
            video_id = None

            if meta_id:
                try:
                    vid_doc = mongo.db.video.find_one({'_id': ObjectId(meta_id)})
                    if vid_doc:
                        raw_video_id = vid_doc.get('video_gridfs_id') or vid_doc.get('file_id')
                        if raw_video_id and ObjectId.is_valid(str(raw_video_id)):
                            video_id = str(raw_video_id)
                except Exception:
                    flash("⚠️ Failed to load video preview.", "warning")

            return render_template("uploadAssignment.html", classroom_id=classroom_id, video_id=video_id)

        
        # POST: process form submission
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        deadline    = request.form.get("deadline")
        upload_file = request.files.get("file")
        video_id    = request.form.get("video_id", "").strip()

        # ✅ Require at least a file or video
        if not title or (not upload_file and not video_id):
            flash("❌ Please enter a title and upload a file or attach a video.", "danger")
            return redirect(request.url)

        filename = secure_filename(upload_file.filename) if upload_file else None
        video_oid = None

        # ✅ Parse video_id only if it's present and looks like an ObjectId
        if video_id:
            if ObjectId.is_valid(video_id):
                video_oid = ObjectId(video_id)
            else:
                flash("Invalid video ID format.", "danger")
                return redirect(request.url)

        # ✅ Upload assignment
        result = UploadAssignmentController.upload_assignment(
            title        = title,
            classroom_id = ObjectId(classroom_id),
            description  = description,
            deadline     = deadline,
            file         = upload_file,
            filename     = filename,
            video_id     = video_oid
        )

        if result.get("success"):
            flash(result["message"], "success")
            return redirect(url_for("boundary.view_classroom", classroom_id=classroom_id))
        else:
            flash(result.get("message", "Something went wrong"), "danger")
            return redirect(request.url)


    @boundary.route("/publish_assignment_video", methods=["POST"])
    def publish_assignment_video():
        data = request.get_json()
        gridfs_id = data.get("video_id")  # GridFS ID
        classroom_id = data.get("classroom_id")

        if not gridfs_id or not classroom_id:
            return jsonify({"success": False, "error": "Missing video ID or classroom ID"}), 400

        try:
            # Try finding it in the permanent collection first
            video_doc = mongo.db.video.find_one({"video_gridfs_id": ObjectId(gridfs_id)})

            if not video_doc:
                # Not found in 'video', try 'tempvideo'
                temp_doc = mongo.db.tempvideo.find_one({"video_id": ObjectId(gridfs_id)})
                if not temp_doc:
                    return jsonify({"success": False, "error": "Video not found"}), 404

                # Move from tempvideo to video collection
                video_doc = {
                    "video_gridfs_id": ObjectId(gridfs_id),
                    "uploaded_by": session.get("username"),
                    "uploaded_at": datetime.utcnow(),
                    "classroom_id": ObjectId(classroom_id),
                    "title": "Assignment Video",
                    "description": "Published from tempvideo"
                }
                mongo.db.video.insert_one(video_doc)

                # Clean up tempvideo
                mongo.db.tempvideo.delete_many({"video_id": ObjectId(gridfs_id)})

            # Store reference for redirect to upload assignment
            video_doc = mongo.db.video.find_one({"video_gridfs_id": ObjectId(gridfs_id)})
            session["stashed_video_id"] = str(video_doc["_id"])

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    
    @boundary.route('/teacher/manage_assignments/<classroom_id>', methods=['GET', 'POST'])
    def manage_assignments(classroom_id):
        """Retrieve all assignments and allow searching."""
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", "error")
            return redirect(url_for('boundary.home'))

        query = request.form.get('search', '').strip()

        # Search logic
        if query:
            assignments = list(mongo.db.assignments.find({
                "classroom_id": ObjectId(classroom_id),
                "title": {"$regex": query, "$options": "i"}  # Case-insensitive search
            }))
        else:
            assignments = list(mongo.db.assignments.find({"classroom_id": ObjectId(classroom_id)}))

        return render_template("manageAssignments.html", assignments=assignments, classroom_id=classroom_id)

    
    @boundary.route('/teacher/download_assignment/<assignment_id>')
    def download_assignment(assignment_id):
        assignment = Assignment.get_assignment(assignment_id)

        if not assignment:
            flash("Assignment not found!", "danger")
            return redirect(url_for("boundary.home"))

        file_data = Assignment.get_assignment_file(assignment["file_id"])
        
        return send_file(
            io.BytesIO(file_data),
            mimetype=mimetypes.guess_type(assignment["file_name"])[0],
            as_attachment=True,
            download_name=assignment["file_name"]
        )

    


    @boundary.route('/delete_submission/<submission_id>')
    def delete_submission(submission_id):
        """Allows a teacher to delete a student's submission."""
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        # Find the submission
        submission = mongo.db.submissions.find_one({"_id": ObjectId(submission_id)})
        if not submission:
            flash("Submission not found!", "danger")
            return redirect(request.referrer)

        # Delete the file from storage
        file_path = submission.get("file_path")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        # Remove submission from database
        mongo.db.submissions.delete_one({"_id": ObjectId(submission_id)})

        flash("Submission deleted successfully!", "success")
        return redirect(request.referrer)



    @boundary.route('/grade_assignment/<classroom_id>/<assignment_id>/<student_username>/<submission_id>', methods=['POST'])
    def grade_assignment(classroom_id, assignment_id, student_username, submission_id):
        """Assigns grades and feedback to student submissions."""
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        grade = request.form.get('grade')

        # Ensure grade is a valid number between 0-100
        try:
            grade = int(grade)
            if grade < 0 or grade > 100:
                raise ValueError
        except ValueError:
            flash("Invalid grade! Must be between 0-100.", "danger")
            return redirect(request.referrer)

        # Update grade in the database
        mongo.db.submissions.update_one(
            {"_id": ObjectId(submission_id)},
            {"$set": {"grade": grade}}
        )

        flash("Grade assigned successfully!", "success")
        return redirect(url_for('boundary.view_submissions', classroom_id=classroom_id, assignment_id=assignment_id))



    
    @boundary.route('/teacher/delete_assignment/<classroom_id>/<assignment_id>')
    def delete_assignment(classroom_id, assignment_id):
        """Deletes an assignment and its associated file."""
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        assignment = mongo.db.assignments.find_one({"_id": ObjectId(assignment_id)})
        if assignment:
            file_path = assignment.get("file_path")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

            mongo.db.assignments.delete_one({"_id": ObjectId(assignment_id)})
            flash('Assignment deleted successfully!', 'success')
        else:
            flash('Assignment not found!', 'danger')

        return redirect(url_for('boundary.manage_assignments', classroom_id=classroom_id))
    
    @boundary.route('/teacher/view_submissions/<classroom_id>/<assignment_id>')
    def view_submissions(classroom_id, assignment_id):
        submissions = list(mongo.db.submissions.find({"assignment_id": ObjectId(assignment_id)}))
        assignment = mongo.db.assignments.find_one({"_id": ObjectId(assignment_id)})
        return render_template(
            "viewSubmissions.html",
            submissions=submissions,
            assignment=assignment,
            classroom_id=classroom_id,
            assignment_id=assignment_id
        )
    
    @boundary.route('/view-student-submission/<submission_id>/<filename>', methods=['GET', 'POST'])
    def view_submitted_assignment(submission_id, filename):
        """Allows a student or teacher to view a single submission."""
        student_doc = mongo.db.submissions.find_one(
            {"_id": ObjectId(submission_id)},
            {"student": 1, "_id": 0, "assignment_id": 1}
        )

        student_username = student_doc.get("student") if student_doc else None
        assignment_id = student_doc.get("assignment_id") if student_doc else None

        assignment_doc = mongo.db.assignments.find_one(
            {"_id": ObjectId(assignment_id)},
            {"classroom_id": 1, "_id": 0}
        )
        classroom_id = assignment_doc.get("classroom_id") if assignment_doc else None

        submission = TeacherViewSubmissionController.get_submission_by_student_and_id(student_username, submission_id)

        if not submission:
            flash("Submission not found.", "danger")
            return redirect(url_for('boundary.home'))

        # Set defaults
        file_base64 = None
        text_content = None
        file_extension = None

        file_name = submission.get("file_name")
        file_id = submission.get("file_id")

        if file_name and "." in file_name and file_id:
            file_extension = file_name.rsplit(".", 1)[-1]
            file_data = Submission.get_submission_file(file_id)

            if file_extension in ["pdf", "txt", "md"]:
                file_base64 = base64.b64encode(file_data).decode("utf-8")
                text_content = file_data.decode("utf-8") if file_extension in ["txt", "md"] else None

        return render_template(
            "viewStudentSubmission.html",
            student_submission=submission,
            file_base64=file_base64,
            text_content=text_content,
            file_extension=file_extension,
            classroom_id=classroom_id,
            assignment_id=assignment_id
        )
    

    @boundary.route('/download-submission/<submission_id>/<filename>', methods=['GET'])
    def download_submitted_assignment(submission_id, filename):
        """Allows a teacher to download a submitted assignment."""
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        fs = get_fs()  # ✅ Use shared GridFS helper

        # Option 1: Find by custom metadata (if stored this way)
        file_data = fs.find_one({"filename": filename})

        if not file_data:
            flash("File not found!", "danger")
            return redirect(request.referrer or url_for("boundary.home"))

        return send_file(
            io.BytesIO(file_data.read()),
            mimetype=mimetypes.guess_type(filename)[0] or "application/octet-stream",
            as_attachment=True,
            download_name=filename
        )

    
    @boundary.route('/add_feedback/<submission_id>', methods=['POST'])
    def add_feedback(submission_id):
        """Adds feedback to a specific submission."""
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        feedback = request.form.get('feedback')
        student_username = request.form.get('student_username')  # This should come from the form

        result = AddFeedbackController.add_feedback(submission_id, student_username, feedback)

        flash(result["message"], category="success" if result["success"] else "danger")
        return redirect(request.referrer)

# Manage Quiz
class TeacherManageQuizBoundary:
    UPLOAD_FOLDER_QUIZ = 'FYP25S109/static/uploads/quiz/'

    @boundary.route('/teacher/upload_quiz/<classroom_id>', methods=['GET', 'POST'])
    def upload_quiz(classroom_id):
        if request.method == "POST":
            quiz_title = request.form.get('quiz_title', '').strip()
            quiz_description = request.form.get('quiz_description', '').strip()
            questions = []

            question_count = sum(1 for key in request.form.keys() if key.startswith('question_'))

            for i in range(1, question_count + 1):
                question_text = request.form.get(f'question_{i}', '').strip()
                options = [
                    request.form.get(f'option_{i}_1', '').strip(),
                    request.form.get(f'option_{i}_2', '').strip(),
                    request.form.get(f'option_{i}_3', '').strip(),
                    request.form.get(f'option_{i}_4', '').strip()
                ]
                correct_answer = request.form.get(f'correct_answer_{i}', '').strip()
                image_file = request.files.get(f'image_{i}')

                # Convert image to base64 if uploaded
                image_data = None
                if image_file and image_file.filename:
                    image_data = base64.b64encode(image_file.read()).decode('utf-8')

                questions.append({
                    "index": i,
                    "text": question_text,
                    "options": options,
                    "correct_answer": correct_answer,
                    "image": image_data
                })

            # Call controller function
            result = UploadQuizController.upload_quiz(quiz_title, quiz_description, questions, classroom_id)

            if result.get("success"):
                flash("Quiz created successfully!", "success")
                return redirect(url_for('boundary.manage_quizzes', classroom_id=classroom_id))
            else:
                flash(f"Error: {result.get('message')}", "danger")

        # If GET request, show the quiz creation form
        return render_template("uploadQuiz.html", classroom_id=classroom_id)
    
    
    @boundary.route('/teacher/manage_quizzes/<classroom_id>', methods=['GET'])
    def manage_quizzes(classroom_id):
        quizzes = list(mongo.db.quizzes.find({"classroom_id": ObjectId(classroom_id)}))
        return render_template("manageQuizzes.html", quizzes=quizzes, classroom_id=classroom_id)

    @boundary.route('/teacher/delete_quiz/<quiz_id>', methods=['POST'])
    def delete_quiz(quiz_id):
        mongo.db.quizzes.delete_one({"_id": ObjectId(quiz_id)})
        flash("Quiz deleted successfully!", category='success')
        return redirect(request.referrer)


    @boundary.route('/teacher/update_quiz/<quiz_id>', methods=['GET', 'POST'])
    def update_quiz(quiz_id):
        quiz = mongo.db.quizzes.find_one({"_id": ObjectId(quiz_id)})
        if not quiz:
            flash("Quiz not found!", "danger")
            return redirect(url_for('manage_quizzes'))

        if request.method == "POST":
            # Handle question deletion first
            if 'delete_question' in request.form:
                try:
                    delete_index = int(request.form['delete_question'])
                    questions = quiz.get('questions', [])
                    if 0 <= delete_index < len(questions):
                        questions.pop(delete_index)
                        mongo.db.quizzes.update_one(
                            {"_id": ObjectId(quiz_id)},
                            {"$set": {"questions": questions}}
                        )
                        flash("Question deleted successfully!", "success")
                    else:
                        flash("Invalid question index for deletion!", "danger")
                    return redirect(url_for('boundary.update_quiz', quiz_id=quiz_id))
                except ValueError:
                    flash("Invalid deletion request!", "danger")
                    return redirect(url_for('boundary.update_quiz', quiz_id=quiz_id))

            # Process quiz update
            quiz_title = request.form.get('title', '').strip()
            quiz_description = request.form.get('description', '').strip()
            
            if not quiz_title or not quiz_description:
                flash("Title and description are required!", "danger")
                return redirect(url_for('boundary.update_quiz', quiz_id=quiz_id))

            # Process questions
            updated_questions = []
            question_indices = set()
            
            # Find all question indices in the form
            for key in request.form:
                if key.startswith('questions[') and '][text]' in key:
                    try:
                        idx = int(key.split('[')[1].split(']')[0])
                        question_indices.add(idx)
                    except (IndexError, ValueError):
                        continue

            for i in sorted(question_indices):
                question_text = request.form.get(f'questions[{i}][text]', '').strip()
                if not question_text:
                    flash(f"Question {i+1} text cannot be empty!", "danger")
                    return redirect(url_for('boundary.update_quiz', quiz_id=quiz_id))

                # Get all 4 options using getlist()
                options = request.form.getlist(f'questions[{i}][options][]')
                if len(options) != 4 or any(not opt.strip() for opt in options):
                    flash(f"All 4 options must be provided for Question {i+1}", "danger")
                    return redirect(url_for('boundary.update_quiz', quiz_id=quiz_id))

                # Validate correct answer
                try:
                    correct_answer = int(request.form.get(f'questions[{i}][correct_answer]', -1))
                    if correct_answer not in {1, 2, 3, 4}:
                        raise ValueError
                except (ValueError, TypeError):
                    flash(f"Invalid correct answer for Question {i+1}", "danger")
                    return redirect(url_for('boundary.update_quiz', quiz_id=quiz_id))

                # Handle image
                image_data = None
                image_file = request.files.get(f'questions[{i}][image]')
                
                if image_file and image_file.filename:
                    if not image_file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                        flash("Only PNG, JPG, and JPEG images are allowed!", "danger")
                        return redirect(url_for('boundary.update_quiz', quiz_id=quiz_id))
                    if image_file.content_length > 2 * 1024 * 1024:  # 2MB limit
                        flash("Image size must be less than 2MB", "danger")
                        return redirect(url_for('boundary.update_quiz', quiz_id=quiz_id))
                    image_data = base64.b64encode(image_file.read()).decode('utf-8')
                elif i < len(quiz.get('questions', [])) and 'image' in quiz['questions'][i]:
                    image_data = quiz['questions'][i]['image']

                updated_questions.append({
                    "text": question_text,
                    "options": options,
                    "correct_answer": correct_answer,
                    "image": image_data
                })

            if not updated_questions:
                flash("Quiz must have at least one question!", "danger")
                return redirect(url_for('boundary.update_quiz', quiz_id=quiz_id))

            # Update database
            mongo.db.quizzes.update_one(
                {"_id": ObjectId(quiz_id)},
                {"$set": {
                    "title": quiz_title,
                    "description": quiz_description,
                    "questions": updated_questions,
                    "updated_at": datetime.utcnow()
                }}
            )

            flash("Quiz updated successfully!", "success")
            return redirect(url_for('manage_quizzes', classroom_id=quiz["classroom_id"]))

        

        return render_template("updateQuiz.html", 
                            quiz=quiz, 
                            quiz_id=quiz_id)

    @boundary.route('/delete_question/<quiz_id>/<question_index>', methods=['POST'])
    def delete_question(quiz_id, question_index):
        quiz = mongo.db.quizzes.find_one({"_id": ObjectId(quiz_id)})
        if not quiz:
            flash("Quiz not found!", "danger")
            return redirect(url_for('manage_quizzes'))

        questions = quiz.get("questions", [])
        if 0 <= int(question_index) < len(questions):
            questions.pop(int(question_index))
            mongo.db.quizzes.update_one(
                {"_id": ObjectId(quiz_id)},
                {"$set": {"questions": questions}}
            )
            flash("Question deleted successfully!", "success")
        else:
            flash("Invalid question index!", "danger")

        return redirect(request.referrer)




class StudentQuizBoundary:
    @boundary.route('/attempt_quiz/<quiz_id>', methods=['GET', 'POST'])
    def attempt_quiz(quiz_id):
        student_username = session.get('username')

        if request.method == 'POST':
            answers = {}
            results = []
            score = 0
            total = 0

            quiz = mongo.db.quizzes.find_one({'_id': ObjectId(quiz_id)})
            if not quiz:
                flash("Quiz not found.", "danger")
                return redirect(url_for('boundary.home'))

            for index, question in enumerate(quiz.get("questions", [])):
                qid_str = str(question.get("_id", index))
                submitted_index = request.form.get(qid_str)

                selected_index = -1  # Default for unanswered
                selected_value = "None"

                if submitted_index is not None and submitted_index.isdigit():
                    selected_index = int(submitted_index)
                    options = question.get("options", [])
                    if 0 <= selected_index < len(options):
                        selected_value = options[selected_index]

                try:
                    correct_index = int(question.get("correct_answer", -1)) - 1
                except (ValueError, TypeError):
                    correct_index = -1
                correct_value = question.get("options", [])[correct_index] if 0 <= correct_index < len(question.get("options", [])) else "N/A"

                if selected_index == correct_index:
                    score += 1

                results.append({
                    "text": question.get("text", ""),
                    "correct": correct_value,
                    "selected": selected_value,
                    "image": question.get("image", None)
                })

                # ✅ Save index instead of value here:
                answers[qid_str] = selected_index  
                total += 1
                
            # Store the attempt in the database
            mongo.db.quiz_attempts.insert_one({
                "student_username": student_username,
                "quiz_id": ObjectId(quiz_id),
                "answers": answers,
                "score": score,
                "total": total,
                "timestamp": datetime.utcnow().replace(tzinfo=timezone.utc)
            })

            classroom_id = quiz.get("classroom_id", "")
            return render_template('quiz_result.html', score=score, total=total, results=results, classroom_id=classroom_id)

        # GET Request - Show Quiz Form
        quiz = mongo.db.quizzes.find_one({'_id': ObjectId(quiz_id)})
        if not quiz:
            flash("Quiz not found.", "danger")
            return redirect(url_for('boundary.home'))
        return render_template('attempt_quiz.html', quiz=quiz)


class TeacherAnnouncementBoundary:
    @boundary.route('/teacher/add_announcement/<classroom_id>/<classroom_name>', methods=['GET', 'POST'])
    def add_announcement(classroom_id, classroom_name):
        if 'role' not in session or session.get('role') != 'Teacher':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))

        if request.method == 'POST':
            title = request.form.get('title')
            content = request.form.get('content')

            if not title or not content:
                flash("Title and content cannot be empty.", category='error')
                return redirect(url_for('boundary.add_announcement', classroom_id=classroom_id, classroom_name=classroom_name))

            mongo.db.announcements.insert_one({
                "classroom_id": ObjectId(classroom_id),
                "classroom_name": classroom_name.strip(),
                "title": title.strip(),
                "content": content.strip(),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

            flash("Announcement added successfully!", category='success')
            return redirect(url_for('boundary.view_classroom', classroom_id=classroom_id))

        return render_template("addAnnouncement.html", classroom_name=classroom_name)

    @boundary.route('/teacher/delete_announcement/<classroom_id>/<announcement_id>', methods=['POST'])
    def delete_announcement(classroom_id, announcement_id):
        mongo.db.announcements.delete_one({"_id": ObjectId(announcement_id)})

        flash("Announcement deleted successfully!", category='success')
        return redirect(url_for('boundary.view_classroom', classroom_id=classroom_id))

    
class ViewAssignmentBoundary:
    @boundary.route('/view_assignment/<assignment_id>')
    def view_assignment(assignment_id):
        assignment = Assignment.get_assignment(assignment_id)

        if not assignment:
            flash("Assignment not found!", "danger")
            return redirect(url_for("boundary.home"))

        # ✅ Ensure due_date is datetime
        if isinstance(assignment["due_date"], str):
            try:
                assignment["due_date"] = datetime.fromisoformat(assignment["due_date"])
            except ValueError:
                pass

        # ✅ Get file content
        file_data = Assignment.get_assignment_file(assignment["file_id"])
        file_extension = assignment["file_name"].split(".")[-1]

        if file_extension in ["pdf", "txt", "md"]:
            file_base64 = base64.b64encode(file_data).decode("utf-8")
            text_content = file_data.decode("utf-8") if file_extension in ["txt", "md"] else None
        else:
            file_base64 = None
            text_content = None

        # ✅ Determine current session user
        username = session.get('username')
        role = session.get('role')

        # ✅ Fetch classroom for enrolled students + teacher
        classroom = mongo.db.classroom.find_one({"_id": assignment.get("classroom_id")})
        enrolled_students = classroom.get("student_list", []) if classroom else []
        teacher_username = classroom.get("teacher") if classroom else None

        # ✅ Attach to assignment for Jinja access
        assignment["teacher_username"] = teacher_username

        # ✅ Get student submission if student
        student_submission = None
        if role == "Student":
            student_submission = Submission.get_submission_by_student_and_assignment(username, assignment_id)

        return render_template("viewAssignment.html",
                               assignment=assignment,
                               filename=assignment["file_name"],
                               file_extension=file_extension,
                               file_base64=file_base64,
                               text_content=text_content,
                               student_submission=student_submission,
                               enrolled_students=enrolled_students) 

#This function facilitates student to view the list of classrooms he/she is enrolled in.
class StudentViewClassroomsBoundary:
    
    @boundary.route('/student/viewClassrooms', methods=['GET'])
    def get_list_of_classrooms():
        if 'role' not in session or session.get('role') != 'Student':
            flash("Unauthorized access.", category='error')
            return redirect(url_for('boundary.home'))
        username = session.get('username')
        classrooms = list(mongo.db.classroom.find({"student_list": username}))
        return render_template("manageClassrooms.html", classrooms=classrooms)

# Student Assignment
class StudentAssignmentBoundary:
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}

    
    def allowed_file(filename):
        """
        Checks if the file has an allowed extension.
        """
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in StudentAssignmentBoundary.ALLOWED_EXTENSIONS

    @boundary.route('/student/view_submission/<assignment_id>/<filename>', methods=['GET', 'POST'])
    def submit_assignment(assignment_id, filename):
        """Handles assignment submission and displays the submission form."""
        try:
            student_username = session.get('username')  # Get logged-in student's username

            if request.method == 'POST':
                file = request.files.get('file')
                if not file:
                    flash('No file uploaded!', 'danger')
                    return redirect(url_for('boundary.submit_assignment',
                                            assignment_id=assignment_id,
                                            filename=filename))

                result = StudentSendSubmissionController.submit_assignment_logic(
                    assignment_id, student_username, file
                )

                if result['success']:
                    flash('Assignment submitted successfully!', 'success')
                else:
                    flash(f"Submission failed: {result['message']}", 'danger')

                return redirect(url_for('boundary.submit_assignment',
                                        assignment_id=assignment_id,
                                        filename=filename))

            # GET → check existing submission
            student_submission = StudentSendSubmissionController.get_submission(
                assignment_id, student_username
            )

            return render_template(
                'view_assignment.html',
                assignment_id=assignment_id,
                filename=filename,
                student_submission=student_submission
            )
        except Exception as e:
            logging.error(f"Error in submit_assignment: {e}")
            flash('An error occurred while submitting the assignment.', 'danger')
            return redirect(url_for('boundary.submit_assignment',
                                    assignment_id=assignment_id,
                                    filename=filename))


    @boundary.route('/student/submit_assignment_video', methods=['POST'])
    def submit_assignment_video():
        try:
            data = request.get_json()
            assignment_id = data.get("assignment_id")
            video_id = data.get("video_id")
            username = session.get("username")

            if not all([assignment_id, video_id, username]):
                return jsonify(success=False, error="Missing required data")

            mongo.db.assignment_submissions.insert_one({
                "assignment_id": ObjectId(assignment_id),
                "student_username": username,
                "video_id": ObjectId(video_id),
                "submitted_at": datetime.utcnow(),
                "type": "video"
            })

            return jsonify(success=True)
        except Exception as e:
            return jsonify(success=False, error=str(e)), 500


    @boundary.route('/student/download_submission/<file_id>')
    def student_download_submission(file_id):
        """Serves the student's submitted file."""
        try:
            file = StudentSendSubmissionController.get_submission_file(file_id)
            if file:
                return send_file(
                    io.BytesIO(file.read()),
                    attachment_filename=file.filename,
                    as_attachment=True
                )
            else:
                flash("File not found!", "danger")
                return redirect(request.referrer)
        except Exception as e:
            logging.error(f"Error in download_submission: {e}")
            flash("An error occurred while downloading the file.", "danger")
            return redirect(request.referrer)

    @boundary.route('/student/view_submission/<submission_id>', methods=['GET'])
    def student_view_submission(submission_id):
        """Allows a student to view their own submission."""
        student_username = session.get('username')
        if not student_username:
            flash("You need to be logged in to view your submission.", "danger")
            return redirect(url_for('boundary.login'))

        submission = StudentViewSubmissionController.get_submission_by_student_and_id(
            student_username, submission_id
        )
        if not submission:
            flash("Submission not found.", "danger")
            return redirect(url_for('boundary.home'))

        file_name = submission.get("file_name")
        file_id = submission.get("file_id")
        video_id = submission.get("video_id")
        file_extension = file_name.rsplit('.', 1)[-1].lower() if file_name else None

        file_base64 = text_content = None
        if file_id and file_extension in ["pdf", "txt", "md"]:
            file_data = Submission.get_submission_file(file_id)
            file_base64 = base64.b64encode(file_data).decode("utf-8")
            if file_extension in ["txt", "md"]:
                text_content = file_data.decode("utf-8")

        return render_template(
            "reviewSubmission.html",
            submission=submission,
            file_base64=file_base64,
            text_content=text_content,
            file_extension=file_extension,
            filename=file_name,
            video_id = video_id
        )

    @boundary.route('/student/edit_submission/<submission_id>', methods=['GET', 'POST'])
    def student_edit_submission(submission_id):
        """Allows a student to edit their submission."""
        student_username = session.get('username')
        if not student_username:
            flash("Please log in to edit your submission.", "danger")
            return redirect(url_for("boundary.login"))

        submission = StudentViewSubmissionController.get_submission_by_student_and_id(
            student_username, submission_id
        )
        if not submission:
            flash("Submission not found.", "danger")
            return redirect(url_for("boundary.home"))

        file_name = submission.get("file_name")
        file_extension = file_name.rsplit('.', 1)[-1].lower() if file_name else None

        file_base64 = text_content = None
        if submission.get("file_id") and file_extension in ["pdf", "txt", "md"]:
            file_data = Submission.get_submission_file(submission["file_id"])
            file_base64 = base64.b64encode(file_data).decode("utf-8")
            if file_extension in ["txt", "md"]:
                text_content = file_data.decode("utf-8")

        return render_template(
            "editSubmission.html",
            submission=submission,
            file_extension=file_extension,
            file_base64=file_base64,
            text_content=text_content,
            filename=file_name,
            video_id = submission.get("video_id")
        )

    @boundary.route('/student/delete_submission/<submission_id>/<assignment_id>', methods=['POST'])
    def student_delete_submission(submission_id, assignment_id):
        """Allows a student to delete their own submission."""
        student_username = session.get('username')
        if not student_username:
            flash("Unauthorized action.", "danger")
            return redirect(url_for('boundary.submit_assignment',
                                    assignment_id=assignment_id,
                                    filename=""))

        result = StudentDeleteSubmissionController.delete_submission(submission_id)
        if result.get("success"):
            flash("Submission deleted successfully!", "success")
        else:
            flash("Error deleting submission.", "danger")

        return redirect(url_for('boundary.view_assignment',
                                assignment_id=assignment_id,
                                filename=""))

    @boundary.route('/submit_video_assignment/<assignment_id>', methods=['POST'])
    def submit_video_assignment_json(assignment_id):
        if 'username' not in session or session.get('role') != "Student":
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        student_username = session.get("username")
        data = request.get_json()
        video_id = data.get("video_id")

        if not video_id or not assignment_id:
            return jsonify({"success": False, "message": "Missing required data."}), 400

        try:
            result = StudentSendSubmissionController.submit_video_assignment_logic(
                assignment_id, student_username, video_id
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
      
# Access Forum
class AccessForumBoundary:
    @boundary.route('/forum/<classroom_id>', methods=['GET','POST'])
    def access_forum(classroom_id):
        return render_template("forum.html", classroom_id=classroom_id, discussion_rooms=RetrieveDiscussionRoomController.get_all_discussion_rooms_by_classroom_id(classroom_id))

# Discussion Room
class DiscussionRoomBoundary:
    @boundary.route('/forum/<classroom_id>/create', methods=['POST'])
    def create_discussion_room(classroom_id):
        discussion_room_name = request.form.get('discussion_room_name')
        discussion_room_description = request.form.get('discussion_room_description')
        created_by = session.get('username')
        
        if AddDiscussionRoomController.add_discussion_room(classroom_id, discussion_room_name, discussion_room_description, created_by):
            flash("Discussion room created successfully!", "success")
        else:
            flash("Failed to create discussion room.", "danger")

        # Redirecting back to the forum page
        return redirect(url_for('boundary.access_forum', classroom_id=classroom_id))

    
    @boundary.route('/forum/<classroom_id>/<discussion_room_id>/delete', methods=['GET', 'POST'])
    def delete_discussion_room(classroom_id, discussion_room_id):
        if DeleteDiscussionRoomController.delete_discussion_room(discussion_room_id):
            flash("Discussion room deleted successfully!", "success")
        else:
            flash("Failed to delete discussion room.", "danger")

        return redirect(url_for('boundary.access_forum', classroom_id=classroom_id))

    
    @boundary.route('/forum/<classroom_id>', methods=['GET'])
    def view_discussion_room_list(classroom_id):
        rooms = RetrieveDiscussionRoomController.get_all_discussion_rooms_by_classroom_id(classroom_id)
        return render_template('forum.html', discussion_rooms=rooms, classroom_id=classroom_id)

    
    @boundary.route('/forum/search', methods=['GET'])
    def search_discussion_room():
        search_query = request.args.get('query')
        rooms = SearchDiscussionRoomController.search_discussion_room(search_query)
        return render_template('forum.html', discussion_rooms=rooms)

    
    @boundary.route('/discussion_room/<discussion_room_id>', methods=['GET', 'POST'])
    def access_room(discussion_room_id):
        # Fetch messages using the controller
        messages = RetrieveMessageController.get_all_messages(discussion_room_id)
        room = RetrieveDiscussionRoomController.get_discussion_room_id(discussion_room_id)

        # Check if the discussion room exists
        if not room:
            flash("Discussion room not found.", "danger")
            return redirect(url_for('boundary.view_discussion_room_list'))

        # Render the template with messages and room data
        return render_template('discussionRoom.html', room=room, messages=messages, discussion_room_id=discussion_room_id)

    
    @boundary.route('/discussion_room/update/<discussion_room_id>', methods=['GET', 'POST'])
    def update_discussion_room(discussion_room_id):

        if request.method == 'GET':
            # Fetch existing details from the database
            discussion_room = UpdateDiscussionRoomController.get_discussion_room_by_id(discussion_room_id)

            if not discussion_room:
                flash("Discussion room not found.", "danger")
                return redirect(url_for('boundary.view_discussion_room_list'))

            # Show the update form
            return render_template('update_discussion_room.html', discussion_room=discussion_room)

        elif request.method == 'POST':
            classroom_id = request.form.get('classroom_id') or discussion_room.get('classroom_id')
            discussion_room_name = request.form.get('discussion_room_name')
            discussion_room_description = request.form.get('discussion_room_description')
            print(f"Discussion Room Name: {discussion_room_name}")
            print(f"Discussion Room Description: {discussion_room_description}")
            
            new_details = {
                "discussion_room_name": discussion_room_name,
                "discussion_room_description": discussion_room_description
            }

            if UpdateDiscussionRoomController.update_discussion_room(discussion_room_id, new_details):
                flash("Discussion room updated successfully!", "success")
            else:
                flash("Failed to update discussion room.", "danger")

            return redirect(url_for('boundary.access_forum', classroom_id=classroom_id))

# Message 
class MessageBoundary:
    
    @boundary.route('/discussion_room/<discussion_room_id>/message', methods=['POST'])
    def send_message(discussion_room_id):
        message_content = request.form.get('message_content')
        message_author = session.get('username')
        if AddMessageController.send_message(discussion_room_id, message_author, message_content):
            flash("Message sent successfully!", "success")
        else:
            flash("Failed to send message.", "danger")
        return redirect(url_for('boundary.access_room', discussion_room_id=discussion_room_id))

    
    
    @boundary.route('/message/<message_id>/delete', methods=['POST'])
    def unsend_message(message_id):
        if DeleteMessageController.delete_message(message_id):
            flash("Message deleted successfully!", "success")
        else:
            flash("Failed to delete message.", "danger")
        return redirect(request.referrer)
    
    
    @boundary.route('/message/<message_id>/update', methods=['POST'])
    def edit_message(message_id):
        message_content = request.form.get('message_content')
        if UpdateMessageController.update_message(message_id, message_content):
            flash("Message updated successfully!", "success")
        else:
            flash("Failed to update message.", "danger")
        return redirect(request.referrer)
    
# Notification 
class NotificationBoundary:
    @boundary.route('/notifications', methods=['GET'])
    def view_notifications():
        query = request.args.get('q', '').strip()
        username = session.get('username')
        role = session.get('role')
        classroom = list(mongo.db.classroom.find({"teacher": username}))  # Corrected access

        notifications = None

        if role == "Teacher" or role == "Student":
            if query:
                notifications = SearchNotificationController.search_notification(query)
            else:
                notifications = ViewNotificationsController.view_notifications(username)

        return render_template('viewNotifications.html', notifications=notifications, classroom=classroom)

    @boundary.route('/send_notification', methods=['GET', 'POST'])
    def send_notification():
        if request.method == 'POST':
            username = session.get('username')
            title = request.form.get('title')
            description = request.form.get('description')
            priority = request.form.get('priority')
            classroom_id = request.form.get('classroom_id')

            if not title or not description:
                flash("Title and description cannot be empty.", category='error')
                return redirect(request.referrer)

            # Call the insert_notification method from the Notification entity
            Notification.insert_notification(username, classroom_id, title, description, priority)

            flash("Notification sent successfully!", category='success')
            return redirect(request.referrer)

    @boundary.route('/delete_notification/<notification_id>', methods=['POST'])
    def delete_notification(notification_id):
        # Call the delete_notification method from the Notification entity
        DeleteNotificationController.delete_notification(notification_id)

        flash("Notification deleted successfully!", category='success')
        return redirect(request.referrer)

    @boundary.route('/edit_notification/<notification_id>', methods=['GET', 'POST'])
    def edit_notification(notification_id):
        notification = Notification.get_notification_by_id(notification_id)
        
        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            priority = request.form.get('priority')

            if not title or not description:
                flash("Title and description cannot be empty.", category='error')
                return redirect(request.referrer)

            # Call the method to update the notification (you can add update method in Notification entity)
            Notification.update_notification(notification_id, title, description, priority)

            flash("Notification updated successfully!", category='success')
            return redirect(request.referrer)

        return render_template('editNotification.html', notification=notification)
    
    @boundary.route('/get_notifications', methods=['GET'])
    def get_notifications():
            username = session.get('username')
            if not username:
                return jsonify([])

            notifications = ViewNotificationsController.view_notifications(username)

            notif_list = [{
                "title": n.get("title"),
                "description": n.get("description"),
                "priority": n.get("priority"),
                "timestamp": n.get("timestamp").strftime("%Y-%m-%d %H:%M:%S")
            } for n in notifications]

            return jsonify(notif_list)
 
        
    @boundary.route('/get_notifications_count', methods=['GET'])
    def get_notifications_count():
        username = session.get("username")
        if not username:
            return jsonify({"count": 0})
        count = GetUnreadNotificationsController.get_unread_notifications(username)

        return jsonify({"count": count})
    
    @boundary.route('/get_unread_notifications', methods=['GET'])
    def get_unread_notifications():
        username = session.get("username")
        if not username:
            return jsonify([])

        notifications = GetUnreadNotificationsController.get_unread_notifications(username) or []

        notif_list = [{
            "title": n.get("title"),
            "description": n.get("description"),
            "priority": n.get("priority"),
            "timestamp": n.get("timestamp").strftime("%Y-%m-%d %H:%M:%S")
        } for n in notifications]

        return jsonify(notif_list)


    @boundary.route("/mark_notifications_read", methods=["POST"])
    def mark_notifications_read():
        username = session.get("username")
        if username:
            ReadNotificationController.mark_as_read(username)
            return jsonify({"status": "success"})
        return jsonify({"status": "not_logged_in"})