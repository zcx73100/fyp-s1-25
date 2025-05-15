    @boundary.route("/generate_video/<avatar_id>/<audio_id>", methods=["POST"])
    def generate_video(avatar_id, audio_id):
        username = session.get("username")
        if not username:
            return jsonify({"success": False, "error": "Login required"}), 401

        text = request.form.get("text", "").strip()
        video_title = request.form.get("video_title", "Untitled")

        avatar_doc = mongo.db.avatar.find_one({"_id": ObjectId(avatar_id)})
        if not avatar_doc:
            return jsonify({"success": False, "error": "Avatar not found"}), 404

        def background_video_generation():
            try:
                import requests
                from io import BytesIO

                fs = get_fs()
                image_file = fs.get(ObjectId(avatar_doc["file_id"]))
                audio_file = fs.get(ObjectId(audio_id))

                files = {
                    "image_file": (image_file.filename, image_file.read(), image_file.content_type or "image/png"),
                    "audio_file": (audio_file.filename, audio_file.read(), audio_file.content_type or "audio/mpeg")
                }

                data = {
                    "preprocess_type": "crop",
                    "is_still_mode": "false",
                    "enhancer": "false",
                    "batch_size": 2,
                    "size_of_image": 256,
                    "pose_style": 0
                }

                SADTALKER_API = os.getenv("SADTALKER_API_URL")
                if not SADTALKER_API:
                        raise ValueError("SADTALKER_API_URL environment variable is not set")
                    
                response = requests.post(SADTALKER_API, files=files, data=data, stream=True)
               

                if response.status_code != 200:
                    raise Exception(f"SadTalker generation failed: {response.text}")

                # ✅ Stream content efficiently for large file
                video_stream = BytesIO()
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        video_stream.write(chunk)
                video_stream.seek(0)  # rewind before storing

                fs_id = fs.put(video_stream, filename=f"{video_title}.mp4", content_type="video/mp4")

                mongo.db.tempvideo.insert_one({
                    "username": username,
                    "avatar_id": ObjectId(avatar_id),
                    "audio_id": ObjectId(audio_id),
                    "video_id": fs_id,
                    "created_at": datetime.utcnow(),
                    "is_published": False
                })

            except Exception as e:
                mongo.db.tempvideo.insert_one({
                    "username": username,
                    "avatar_id": ObjectId(avatar_id),
                    "audio_id": ObjectId(audio_id),
                    "error": str(e),
                    "created_at": datetime.utcnow()
                })

        from threading import Thread
        Thread(target=background_video_generation).start()

        return jsonify({
            "success": True,
            "message": "✅ Video generation started. Please wait a few moments."
        })
