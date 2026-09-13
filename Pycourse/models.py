# -*- coding: utf-8 -*-
"""
Модели базы данных Pycourse.
Аутентификация — без flask_login: пароли хешируются через werkzeug.security,
а сессия пользователя хранится в обычной подписанной cookie-сессии Flask
(см. session['user_id'] в app.py).
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(10), nullable=False)  # 'admin' | 'pupil'
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar_color = db.Column(db.String(20), default="#34d399")
    points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    completed_lessons = db.relationship(
        "CompletedLesson", backref="user", cascade="all, delete-orphan"
    )
    test_results = db.relationship(
        "TestResult", backref="user", cascade="all, delete-orphan"
    )
    chat_messages = db.relationship(
        "ChatMessage", backref="pupil", cascade="all, delete-orphan"
    )


class Lesson(db.Model):
    __tablename__ = "lessons"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    desc = db.Column(db.Text, default="")
    topic = db.Column(db.String(120), default="Без темы")
    video_type = db.Column(db.String(10), default="url")  # 'url' | 'file'
    video_url = db.Column(db.String(500), default="")
    video_filename = db.Column(db.String(255))  # имя файла в uploads/videos
    order = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tests = db.relationship("Test", backref="lesson", cascade="all, delete-orphan")
    tasks = db.relationship("Task", backref="lesson", cascade="all, delete-orphan")


class Test(db.Model):
    __tablename__ = "tests"

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, nullable=False)  # список строк
    correct = db.Column(db.Integer, nullable=False)  # индекс правильного варианта

    results = db.relationship("TestResult", backref="test", cascade="all, delete-orphan")


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    desc = db.Column(db.Text, default="")


class CompletedLesson(db.Model):
    __tablename__ = "completed_lessons"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson"),)


class WatchedVideo(db.Model):
    """Отдельно от CompletedLesson: фиксирует, что ученик досмотрел
    видео урока до конца — нужно, чтобы открыть тест и задачи."""
    __tablename__ = "watched_videos"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False)
    watched_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "lesson_id", name="uq_user_watched_lesson"),)


class TestResult(db.Model):
    __tablename__ = "test_results"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey("tests.id"), nullable=False)
    correct = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "test_id", name="uq_user_test"),)


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    channel = db.Column(db.String(10), nullable=False)  # 'teacher' | 'ai'
    sender = db.Column(db.String(10), nullable=False)   # 'pupil' | 'teacher' | 'ai'
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
