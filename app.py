"""Small web front end for the AlgoLevel video renderer."""
import json
import os
from pathlib import Path
import threading
import uuid

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from agent import ai_plan, local_plan, render, validate, ROLES

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 400 * 1024 * 1024
BASE = Path(os.environ.get("ALGOLEVEL_DATA", "data")).resolve()
BASE.mkdir(parents=True, exist_ok=True)
JOBS = {}
LOCK = threading.Lock()
EXTENSIONS = {".mp4", ".mov", ".mkv"}


def set_job(job_id, **values):
    with LOCK:
        JOBS[job_id].update(values)


@app.errorhandler(RequestEntityTooLarge)
def too_large(_error):
    return jsonify(error="Files exceed the 400 MB upload limit."), 413


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/plan")
def plan_route():
    topic = str((request.get_json(silent=True) or {}).get("topic", "manual levels")).strip()[:120]
    if not topic:
        return jsonify(error="Enter a topic."), 400
    return jsonify(local_plan(topic))


def create_video(job_id, plan, sources, folder):
    try:
        render(plan, sources, folder, False, None)
        set_job(job_id, status="done")
    except Exception as exc:
        app.logger.exception("Render failed for %s", job_id)
        set_job(job_id, status="error", error=str(exc)[:300])


@app.post("/api/jobs")
def submit():
    topic = request.form.get("topic", "").strip()[:120]
    if not topic:
        return jsonify(error="Enter a topic."), 400
    for role in ROLES:
        file = request.files.get(role)
        if not file or not file.filename or Path(file.filename).suffix.lower() not in EXTENSIONS:
            return jsonify(error=f"Upload an MP4, MOV, or MKV clip for {role}."), 400
    job_id = uuid.uuid4().hex
    folder = BASE / job_id
    folder.mkdir(mode=0o700)
    try:
        sources = []
        for role in ROLES:
            upload = request.files[role]
            path = folder / (role + Path(upload.filename).suffix.lower())
            upload.save(path)
            sources.append(path)
        plan = ai_plan(topic) if request.form.get("ai_script") == "true" else local_plan(topic)
        validate(plan)
        with LOCK:
            JOBS[job_id] = {"status": "rendering", "plan": plan}
        thread = threading.Thread(target=create_video, args=(job_id, plan, sources, folder), daemon=True)
        thread.start()
        return jsonify(id=job_id, plan=plan), 202
    except Exception as exc:
        app.logger.exception("Submission failed")
        return jsonify(error=str(exc)[:300]), 400


@app.get("/api/jobs/<job_id>")
def status(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify(error="Job not found. It may have expired after a restart."), 404
        return jsonify(job)


@app.get("/api/jobs/<job_id>/<artifact>")
def download(job_id, artifact):
    names = {"video": "video.mp4", "thumbnail": "thumbnail.png", "plan": "plan.json", "script": "script.txt", "caption": "caption.txt"}
    if artifact not in names:
        return jsonify(error="Unknown file"), 404
    with LOCK:
        if JOBS.get(job_id, {}).get("status") != "done":
            return jsonify(error="Video is not ready"), 404
    path = BASE / job_id / names[artifact]
    return send_file(path, as_attachment=True, download_name=f"AlgoLevel_{job_id[:8]}_{names[artifact]}")


@app.get("/health")
def health():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
