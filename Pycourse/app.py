# -*- coding: utf-8 -*-
"""
Pycourse backend — Flask + SQLAlchemy, без flask_login.

Аутентификация сделана вручную:
- пароли хранятся как хэш (werkzeug.security.generate_password_hash);
- после успешного входа id пользователя кладётся в подписанную
  cookie-сессию Flask: session['user_id'] = user.id;
- декоратор login_required(role=...) в начале каждого защищённого
  маршрута проверяет session и роль пользователя.

Запуск:
    pip install -r requirements.txt
    python app.py
Сайт будет на http://127.0.0.1:5000
"""

import os
import random
import uuid
from datetime import datetime
from functools import wraps

from flask import Flask, request, session, jsonify, send_from_directory, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from models import db, User, Lesson, Test, Task, CompletedLesson, WatchedVideo, TestResult, ChatMessage

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "videos")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_VIDEO_EXT = {"mp4", "webm", "ogg", "ogv", "mov", "mkv", "avi"}
POINTS_FOR_LESSON = 10
POINTS_FOR_TEST = 15


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "pycourse-dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "pycourse.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 2048 * 2048  # до 1024 МБ на видео

    db.init_app(app)

    with app.app_context():
        db.create_all()
        seed_defaults()

    register_routes(app)
    return app


# ------------------------------------------------------------------ #
#  Начальные данные (создаются один раз, если база пустая)
# ------------------------------------------------------------------ #
def seed_defaults():
    if User.query.count() == 0:
        admin = User(
            role="admin",
            name="Далер Раҳимов",
            email="admin@pycourse.tj",
            password_hash=generate_password_hash("admin123"),
            avatar_color="#eab454",
        )
        pupil = User(
            role="pupil",
            name="Азиз Каримов",
            email="pupil@pycourse.tj",
            password_hash=generate_password_hash("pupil123"),
            avatar_color="#34d399",
            points=0,
        )
        db.session.add_all([admin, pupil])
        db.session.commit()

    if Lesson.query.count() == 0:
        l1 = Lesson(
            title="Урок 1. Введение в Python",
            desc="Знакомство с языком, установка окружения, первая программа.",
            topic="Основы Python",
            video_type="url",
            video_url="",
            order=1,
        )
        l2 = Lesson(
            title="Урок 2. Переменные и типы данных",
            desc="Числа, строки, списки и работа с ними.",
            topic="Основы Python",
            video_type="url",
            video_url="",
            order=2,
        )
        db.session.add_all([l1, l2])
        db.session.commit()

        t1 = Test(
            lesson_id=l1.id,
            question="Какая функция выводит текст на экран в Python?",
            options=["print()", "echo()", "console.log()", "output()"],
            correct=0,
        )
        task1 = Task(
            lesson_id=l1.id,
            title="Задача 1",
            desc="Напишите программу, которая выводит на экран ваше имя и возраст.",
        )
        db.session.add_all([t1, task1])
        db.session.commit()


# ------------------------------------------------------------------ #
#  Аутентификация (своя, без flask_login)
# ------------------------------------------------------------------ #
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)


def login_required(role=None):
    """Декоратор: требует вход, опционально — конкретную роль.
    Найденного пользователя кладёт в flask.g.user."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({"error": "Требуется вход в систему"}), 401
            if role and user.role != role:
                return jsonify({"error": "Недостаточно прав"}), 403
            g.user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


# ------------------------------------------------------------------ #
#  Сериализация моделей в JSON
# ------------------------------------------------------------------ #
def user_public(u, include_rank=False):
    d = {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "avatarColor": u.avatar_color,
    }
    if u.role == "pupil":
        d["points"] = u.points
        d["completedCount"] = CompletedLesson.query.filter_by(user_id=u.id).count()
        if include_rank:
            d["rank"] = pupil_rank(u.id)
    return d


def pupil_rank(user_id):
    pupils = User.query.filter_by(role="pupil").order_by(User.points.desc(), User.id.asc()).all()
    for i, p in enumerate(pupils):
        if p.id == user_id:
            return i + 1
    return None


def lesson_public(lesson):
    video_url = None
    if lesson.video_type == "url" and lesson.video_url:
        video_url = lesson.video_url
    elif lesson.video_type == "file" and lesson.video_filename:
        video_url = "/uploads/videos/" + lesson.video_filename
    return {
        "id": lesson.id,
        "title": lesson.title,
        "desc": lesson.desc,
        "topic": lesson.topic or "Без темы",
        "videoType": lesson.video_type,
        "videoUrl": video_url,
        "order": lesson.order,
    }


def test_public(test, for_user=None):
    d = {
        "id": test.id,
        "lessonId": test.lesson_id,
        "question": test.question,
        "options": test.options,
    }
    if for_user is not None:
        result = TestResult.query.filter_by(user_id=for_user.id, test_id=test.id, correct=True).first()
        d["answered"] = result is not None
        if result is not None:
            d["correct"] = test.correct
    else:
        # запрос от учителя — сразу видно правильный ответ
        d["correct"] = test.correct
    return d


def task_public(task):
    return {
        "id": task.id,
        "lessonId": task.lesson_id,
        "title": task.title,
        "desc": task.desc,
    }


def chat_public(msg):
    return {
        "id": msg.id,
        "channel": msg.channel,
        "sender": msg.sender,
        "text": msg.text,
        "time": msg.created_at.isoformat() + "Z",
    }


# ------------------------------------------------------------------ #
#  ИИ-помощник (заготовка). Когда будет настоящий backend с ИИ —
#  замените тело этой функции на вызов вашей модели.
# ------------------------------------------------------------------ #
def ai_reply(question):
    q = (question or "").lower()
    if "привет" in q:
        return "Привет! Чем помочь с уроком?"
    if "ошиб" in q:
        return ("Пришли текст ошибки — попробуем разобрать вместе. "
                "(Демо-режим: полноценный разбор появится после подключения настоящего ИИ.)")
    canned = [
        "Хороший вопрос! Пересмотри видео к текущему уроку ещё раз — там разбирается похожий пример.",
        "Попробуй разбить задачу на маленькие шаги и написать план перед кодом.",
        "Подсказка: проверь отступы и названия переменных — частая причина ошибок у новичков.",
        "Загляни в раздел «Тесты» этого урока — там есть вопрос почти на эту тему.",
        "Отличная попытка! Когда подключится настоящий ИИ-бэкенд, я смогу разобрать твой код построчно.",
    ]
    return random.choice(canned)


# ------------------------------------------------------------------ #
#  Маршруты
# ------------------------------------------------------------------ #
def register_routes(app):

    # ---------- статика фронтенда ----------
    @app.route("/")
    def index_page():
        return app.send_static_file("index.html")

    @app.route("/uploads/videos/<path:filename>")
    def uploaded_video(filename):
        return send_from_directory(UPLOAD_DIR, filename)

    # ---------- аутентификация ----------
    @app.route("/api/login", methods=["POST"])
    def api_login():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Неверный email или пароль"}), 401
        session["user_id"] = user.id
        return jsonify({"user": user_public(user, include_rank=True)})

    @app.route("/api/logout", methods=["POST"])
    def api_logout():
        session.clear()
        return jsonify({"ok": True})

    @app.route("/api/me", methods=["GET"])
    def api_me():
        user = current_user()
        if not user:
            return jsonify({"user": None})
        return jsonify({"user": user_public(user, include_rank=True)})

    @app.route("/api/me", methods=["PUT"])
    @login_required()
    def api_me_update():
        data = request.get_json(silent=True) or {}
        current_password = data.get("currentPassword") or ""
        if not check_password_hash(g.user.password_hash, current_password):
            return jsonify({"error": "Текущий пароль неверен"}), 400

        new_name = (data.get("name") or "").strip()
        new_email = (data.get("email") or "").strip().lower()
        new_password = data.get("password") or ""

        if new_email and new_email != g.user.email:
            if User.query.filter_by(email=new_email).first():
                return jsonify({"error": "Этот email уже используется другим аккаунтом"}), 400
            g.user.email = new_email

        if new_name:
            g.user.name = new_name
        if new_password:
            g.user.password_hash = generate_password_hash(new_password)

        db.session.commit()
        # обновляем сессию на случай смены email/id не меняется, так что сессия остаётся валидной
        return jsonify({"user": user_public(g.user, include_rank=True)})

    # ---------- ученики (только учитель) ----------
    @app.route("/api/students", methods=["GET"])
    @login_required(role="admin")
    def api_students_list():
        pupils = User.query.filter_by(role="pupil").order_by(User.points.desc(), User.id.asc()).all()
        return jsonify({"students": [user_public(p) for p in pupils]})

    @app.route("/api/students", methods=["POST"])
    @login_required(role="admin")
    def api_students_create():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        if not name or not email or len(password) < 4:
            return jsonify({"error": "Заполните имя, email и пароль (минимум 4 символа)"}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Такой email уже используется"}), 400
        colors = ["#34d399", "#eab454", "#e8735f", "#6ee7b7", "#f3cd82"]
        pupil = User(
            role="pupil",
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            avatar_color=random.choice(colors),
            points=0,
        )
        db.session.add(pupil)
        db.session.commit()
        return jsonify({"student": user_public(pupil)}), 201

    @app.route("/api/students/<int:student_id>/password", methods=["PUT"])
    @login_required(role="admin")
    def api_students_reset_password(student_id):
        data = request.get_json(silent=True) or {}
        password = data.get("password") or ""
        if len(password) < 4:
            return jsonify({"error": "Пароль должен быть не короче 4 символов"}), 400
        pupil = User.query.filter_by(id=student_id, role="pupil").first()
        if not pupil:
            return jsonify({"error": "Ученик не найден"}), 404
        pupil.password_hash = generate_password_hash(password)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/students/<int:student_id>", methods=["DELETE"])
    @login_required(role="admin")
    def api_students_delete(student_id):
        pupil = User.query.filter_by(id=student_id, role="pupil").first()
        if not pupil:
            return jsonify({"error": "Ученик не найден"}), 404
        db.session.delete(pupil)
        db.session.commit()
        return jsonify({"ok": True})

    # ---------- рейтинг (доступен и учителю, и ученику) ----------
    @app.route("/api/rating", methods=["GET"])
    @login_required()
    def api_rating():
        pupils = User.query.filter_by(role="pupil").order_by(User.points.desc(), User.id.asc()).all()
        result = {"pupils": [user_public(p) for p in pupils]}
        if g.user.role == "pupil":
            result["myRank"] = pupil_rank(g.user.id)
        return jsonify(result)

    # ---------- уроки ----------
    @app.route("/api/lessons", methods=["GET"])
    @login_required()
    def api_lessons_list():
        lessons = Lesson.query.order_by(Lesson.order.asc()).all()
        data = [lesson_public(l) for l in lessons]
        if g.user.role == "pupil":
            done_ids = {
                cl.lesson_id for cl in CompletedLesson.query.filter_by(user_id=g.user.id).all()
            }
            watched_ids = {
                wv.lesson_id for wv in WatchedVideo.query.filter_by(user_id=g.user.id).all()
            }
            for item in data:
                item["completed"] = item["id"] in done_ids
                item["watched"] = item["completed"] or (not item["videoUrl"]) or (item["id"] in watched_ids)
        return jsonify({"lessons": data})

    @app.route("/api/lessons/topics", methods=["GET"])
    @login_required()
    def api_lessons_topics():
        topics = [row[0] for row in db.session.query(Lesson.topic).distinct().all()]
        return jsonify({"topics": [t or "Без темы" for t in topics]})

    @app.route("/api/lessons", methods=["POST"])
    @login_required(role="admin")
    def api_lessons_create():
        # поддерживаем и multipart/form-data (файл видео), и JSON (ссылка)
        if request.content_type and "multipart/form-data" in request.content_type:
            form = request.form
            title = (form.get("title") or "").strip()
            desc = (form.get("desc") or "").strip()
            topic = (form.get("topic") or "").strip() or "Без темы"
            video_type = form.get("videoType") or "file"
            file = request.files.get("file")
        else:
            data = request.get_json(silent=True) or {}
            title = (data.get("title") or "").strip()
            desc = (data.get("desc") or "").strip()
            topic = (data.get("topic") or "").strip() or "Без темы"
            video_type = data.get("videoType") or "url"
            file = None

        if not title:
            return jsonify({"error": "Название урока обязательно"}), 400

        max_order = db.session.query(db.func.max(Lesson.order)).scalar() or 0
        lesson = Lesson(
            title=title,
            desc=desc,
            topic=topic,
            video_type=video_type,
            order=max_order + 1,
        )

        if video_type == "file" and file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext not in ALLOWED_VIDEO_EXT:
                return jsonify({"error": "Недопустимый формат видео: ." + ext}), 400
            filename = uuid.uuid4().hex + "." + ext
            file.save(os.path.join(UPLOAD_DIR, secure_filename(filename)))
            lesson.video_filename = filename
        elif video_type == "url":
            data = request.get_json(silent=True) or {}
            lesson.video_url = (data.get("videoUrl") or request.form.get("videoUrl") or "").strip()

        db.session.add(lesson)
        db.session.commit()
        return jsonify({"lesson": lesson_public(lesson)}), 201

    @app.route("/api/lessons/<int:lesson_id>", methods=["DELETE"])
    @login_required(role="admin")
    def api_lessons_delete(lesson_id):
        lesson = Lesson.query.get(lesson_id)
        if not lesson:
            return jsonify({"error": "Урок не найден"}), 404
        if lesson.video_filename:
            path = os.path.join(UPLOAD_DIR, lesson.video_filename)
            if os.path.exists(path):
                os.remove(path)
        db.session.delete(lesson)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/lessons/<int:lesson_id>/complete", methods=["POST"])
    @login_required(role="pupil")
    def api_lesson_complete(lesson_id):
        lesson = Lesson.query.get(lesson_id)
        if not lesson:
            return jsonify({"error": "Урок не найден"}), 404
        existing = CompletedLesson.query.filter_by(user_id=g.user.id, lesson_id=lesson_id).first()
        if not existing:
            db.session.add(CompletedLesson(user_id=g.user.id, lesson_id=lesson_id))
            g.user.points = (g.user.points or 0) + POINTS_FOR_LESSON
            db.session.commit()
        return jsonify({"ok": True, "points": g.user.points})

    @app.route("/api/lessons/<int:lesson_id>/watch", methods=["POST"])
    @login_required(role="pupil")
    def api_lesson_watch(lesson_id):
        lesson = Lesson.query.get(lesson_id)
        if not lesson:
            return jsonify({"error": "Урок не найден"}), 404
        existing = WatchedVideo.query.filter_by(user_id=g.user.id, lesson_id=lesson_id).first()
        if not existing:
            db.session.add(WatchedVideo(user_id=g.user.id, lesson_id=lesson_id))
            db.session.commit()
        return jsonify({"ok": True})

    # ---------- тесты ----------
    @app.route("/api/tests", methods=["GET"])
    @login_required()
    def api_tests_list():
        lesson_id = request.args.get("lesson_id", type=int)
        query = Test.query
        if lesson_id:
            query = query.filter_by(lesson_id=lesson_id)
        tests = query.all()
        for_user = g.user if g.user.role == "pupil" else None
        return jsonify({"tests": [test_public(t, for_user=for_user) for t in tests]})

    @app.route("/api/tests", methods=["POST"])
    @login_required(role="admin")
    def api_tests_create():
        data = request.get_json(silent=True) or {}
        lesson_id = data.get("lessonId")
        question = (data.get("question") or "").strip()
        options = [o.strip() for o in (data.get("options") or []) if o and o.strip()]
        correct = data.get("correct")
        if not lesson_id or not question or len(options) < 2 or correct is None:
            return jsonify({"error": "Заполните вопрос, минимум 2 варианта и правильный ответ"}), 400
        test = Test(lesson_id=lesson_id, question=question, options=options, correct=int(correct))
        db.session.add(test)
        db.session.commit()
        return jsonify({"test": test_public(test)}), 201

    @app.route("/api/tests/<int:test_id>", methods=["DELETE"])
    @login_required(role="admin")
    def api_tests_delete(test_id):
        test = Test.query.get(test_id)
        if not test:
            return jsonify({"error": "Тест не найден"}), 404
        db.session.delete(test)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/tests/<int:test_id>/submit", methods=["POST"])
    @login_required(role="pupil")
    def api_tests_submit(test_id):
        test = Test.query.get(test_id)
        if not test:
            return jsonify({"error": "Тест не найден"}), 404

        # если уже отвечено правильно раньше — баллы второй раз не начисляем
        already = TestResult.query.filter_by(user_id=g.user.id, test_id=test.id, correct=True).first()
        if already:
            return jsonify({"correct": True, "correctIndex": test.correct, "alreadyAnswered": True})

        data = request.get_json(silent=True) or {}
        chosen = data.get("chosenIndex")
        if chosen is None:
            return jsonify({"error": "Не выбран ответ"}), 400
        is_correct = int(chosen) == test.correct

        if is_correct:
            # неверные попытки не сохраняем — ученик может пробовать снова сколько угодно раз
            db.session.add(TestResult(user_id=g.user.id, test_id=test.id, correct=True))
            g.user.points = (g.user.points or 0) + POINTS_FOR_TEST
            db.session.commit()

        return jsonify({"correct": is_correct, "correctIndex": test.correct})

    # ---------- задачи ----------
    @app.route("/api/tasks", methods=["GET"])
    @login_required()
    def api_tasks_list():
        lesson_id = request.args.get("lesson_id", type=int)
        query = Task.query
        if lesson_id:
            query = query.filter_by(lesson_id=lesson_id)
        return jsonify({"tasks": [task_public(t) for t in query.all()]})

    @app.route("/api/tasks", methods=["POST"])
    @login_required(role="admin")
    def api_tasks_create():
        data = request.get_json(silent=True) or {}
        lesson_id = data.get("lessonId")
        title = (data.get("title") or "").strip()
        desc = (data.get("desc") or "").strip()
        if not lesson_id or not title or not desc:
            return jsonify({"error": "Заполните урок, название и условие задачи"}), 400
        task = Task(lesson_id=lesson_id, title=title, desc=desc)
        db.session.add(task)
        db.session.commit()
        return jsonify({"task": task_public(task)}), 201

    @app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
    @login_required(role="admin")
    def api_tasks_delete(task_id):
        task = Task.query.get(task_id)
        if not task:
            return jsonify({"error": "Задача не найдена"}), 404
        db.session.delete(task)
        db.session.commit()
        return jsonify({"ok": True})

    # ---------- чат ученика (учитель / ИИ) ----------
    @app.route("/api/chat/<channel>", methods=["GET"])
    @login_required(role="pupil")
    def api_chat_get(channel):
        if channel not in ("teacher", "ai"):
            return jsonify({"error": "Неизвестный канал"}), 400
        msgs = (
            ChatMessage.query.filter_by(pupil_id=g.user.id, channel=channel)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return jsonify({"messages": [chat_public(m) for m in msgs]})

    @app.route("/api/chat/<channel>", methods=["POST"])
    @login_required(role="pupil")
    def api_chat_post(channel):
        if channel not in ("teacher", "ai"):
            return jsonify({"error": "Неизвестный канал"}), 400
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "Пустое сообщение"}), 400

        msg = ChatMessage(pupil_id=g.user.id, channel=channel, sender="pupil", text=text)
        db.session.add(msg)
        db.session.commit()

        reply = None
        if channel == "ai":
            reply_text = ai_reply(text)
            reply = ChatMessage(pupil_id=g.user.id, channel="ai", sender="ai", text=reply_text)
            db.session.add(reply)
            db.session.commit()

        return jsonify({
            "message": chat_public(msg),
            "reply": chat_public(reply) if reply else None,
        }), 201

    # ---------- чат учителя ----------
    @app.route("/api/chat/threads", methods=["GET"])
    @login_required(role="admin")
    def api_chat_threads():
        pupil_ids = [
            row[0]
            for row in db.session.query(ChatMessage.pupil_id)
            .filter_by(channel="teacher")
            .distinct()
            .all()
        ]
        pupils = User.query.filter(User.id.in_(pupil_ids)).all()
        return jsonify({"threads": [user_public(p) for p in pupils]})

    @app.route("/api/chat/admin/<int:pupil_id>", methods=["GET"])
    @login_required(role="admin")
    def api_chat_admin_get(pupil_id):
        msgs = (
            ChatMessage.query.filter_by(pupil_id=pupil_id, channel="teacher")
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return jsonify({"messages": [chat_public(m) for m in msgs]})

    @app.route("/api/chat/admin/<int:pupil_id>", methods=["POST"])
    @login_required(role="admin")
    def api_chat_admin_post(pupil_id):
        pupil = User.query.filter_by(id=pupil_id, role="pupil").first()
        if not pupil:
            return jsonify({"error": "Ученик не найден"}), 404
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "Пустое сообщение"}), 400
        msg = ChatMessage(pupil_id=pupil_id, channel="teacher", sender="teacher", text=text)
        db.session.add(msg)
        db.session.commit()
        return jsonify({"message": chat_public(msg)}), 201


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=8000,host="localhost")
