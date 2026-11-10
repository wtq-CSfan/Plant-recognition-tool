import os
import io
import base64
import sqlite3
import re
from datetime import datetime, timezone

import requests
from PIL import Image, ImageOps
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit
DB_PATH = os.environ.get("PLANT_DB_PATH", os.path.join(app.instance_path, "plant_history.db"))
os.makedirs(app.instance_path, exist_ok=True)

# Set these environment variables on your computer/server. Never put secrets in frontend JS.
BAIDU_API_KEY = "kztmbUM17gXsxrov8mLc9wjW"
BAIDU_SECRET_KEY = "XEdesSlhgu1UNJWYPfQJ1EbaTfROOSGU"
BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_PLANT_URL = "https://aip.baidubce.com/rest/2.0/image-classify/v1/plant"


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recognition_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_name TEXT NOT NULL,
                score REAL,
                description TEXT,
                image_data TEXT,
                created_at TEXT NOT NULL
            )
        """)


init_db()


def translate_to_english(text, fallback=""):
    """Translate Baidu's Chinese plant names/descriptions for the English UI.

    Uses Google's public web translation endpoint. If it is unavailable, return a
    clear English fallback rather than displaying Chinese encyclopedia text.
    """
    text = str(text or "").strip()
    if not text:
        return fallback
    # Keep already-English content as-is and split long descriptions into chunks.
    if not re.search(r"[\u3400-\u9fff]", text):
        return text
    chunks = [text[i:i + 900] for i in range(0, len(text), 900)]
    translated = []
    for chunk in chunks:
        try:
            response = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": chunk},
                timeout=12,
            )
            response.raise_for_status()
            data = response.json()
            translated.append("".join(part[0] for part in data[0] if part and part[0]))
        except (requests.RequestException, ValueError, TypeError, IndexError):
            return fallback
    output = " ".join(translated).strip()
    return output if output and not re.search(r"[\u3400-\u9fff]", output) else fallback


def get_access_token():
    if not BAIDU_API_KEY or not BAIDU_SECRET_KEY:
        raise RuntimeError("Baidu API credentials are not configured. Set the BAIDU_API_KEY and BAIDU_SECRET_KEY environment variables.")
    response = requests.post(
        BAIDU_TOKEN_URL,
        params={
            "grant_type": "client_credentials",
            "client_id": BAIDU_API_KEY,
            "client_secret": BAIDU_SECRET_KEY,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if "access_token" not in payload:
        raise RuntimeError(payload.get("error_description") or payload.get("error") or "Could not obtain a Baidu access token.")
    return payload["access_token"]


def prepare_image(file_storage):
    image = Image.open(file_storage.stream)
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((1200, 1200))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue(), image


def recognize_plant(image_bytes):
    token = get_access_token()
    encoded = base64.b64encode(image_bytes).decode("ascii")
    response = requests.post(
        BAIDU_PLANT_URL,
        params={"access_token": token},
        data={"image": encoded, "baike_num": 1},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error_code"):
        raise RuntimeError(payload.get("error_msg", "The Baidu plant identification API returned an error."))
    return payload


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("img")
    if file is None or not file.filename:
        return jsonify({"error": "Please take or choose an image first."}), 400

    try:
        image_bytes, image = prepare_image(file)
        result = recognize_plant(image_bytes)
        results = result.get("result", [])
        if not results:
            return jsonify({"error": "No plant was identified. Try a clearer photo with the plant as the main subject."}), 422

        # Save the first/best result and a small preview image in SQLite.
        top = results[0]
        name = translate_to_english(top.get("name", ""), "Plant name unavailable in English")[:200]
        score = float(top.get("score", 0) or 0)
        description = translate_to_english((top.get("baike_info") or {}).get("description", ""), "An English description is not available for this plant.")[:4000]
        thumb = image.copy()
        thumb.thumbnail((480, 480))
        thumb_buffer = io.BytesIO()
        thumb.save(thumb_buffer, format="JPEG", quality=70, optimize=True)
        image_data = "data:image/jpeg;base64," + base64.b64encode(thumb_buffer.getvalue()).decode("ascii")
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")

        with db_connect() as conn:
            cursor = conn.execute(
                """INSERT INTO recognition_history
                   (plant_name, score, description, image_data, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, score, description, image_data, created_at),
            )
            record_id = cursor.lastrowid

        # Return translated names and Baidu encyclopedia descriptions to the English UI.
        english_results = []
        for item in results:
            translated_item = dict(item)
            translated_item["name"] = translate_to_english(item.get("name", ""), "Plant name unavailable in English")
            info = dict(item.get("baike_info") or {})
            info["description"] = translate_to_english(info.get("description", ""), "An English description is not available for this plant.")
            translated_item["baike_info"] = info
            english_results.append(translated_item)
        return jsonify({"id": record_id, "result": english_results, "saved": True, "created_at": created_at})
    except (Image.UnidentifiedImageError, OSError):
        return jsonify({"error": "Could not read this image. Please try a JPG, PNG, or WebP file."}), 400
    except requests.RequestException:
        app.logger.exception("Plant recognition API request failed")
        return jsonify({"error": "Could not connect to the recognition service. Check your connection and try again."}), 502
    except Exception as exc:
        app.logger.exception("Plant recognition failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/history", methods=["GET"])
def history():
    with db_connect() as conn:
        rows = conn.execute(
            """SELECT id, plant_name, score, description, image_data, created_at
               FROM recognition_history ORDER BY id DESC LIMIT 100"""
        ).fetchall()
    records = [dict(row) for row in rows]
    for record in records:
        record["plant_name"] = translate_to_english(record.get("plant_name"), "Plant name unavailable in English")
        record["description"] = translate_to_english(record.get("description"), "An English description is not available for this plant.")
    return jsonify({"records": records})


@app.route("/history/<int:record_id>", methods=["DELETE"])
def delete_history(record_id):
    with db_connect() as conn:
        cursor = conn.execute("DELETE FROM recognition_history WHERE id = ?", (record_id,))
    if cursor.rowcount == 0:
        return jsonify({"error": "Record not found or already deleted."}), 404
    return jsonify({"ok": True})


@app.route("/history", methods=["DELETE"])
def clear_history():
    with db_connect() as conn:
        conn.execute("DELETE FROM recognition_history")
    return jsonify({"ok": True})


if __name__ == "__main__":
    # For local development only. Use a production WSGI server when deploying.
    app.run(debug=True)
