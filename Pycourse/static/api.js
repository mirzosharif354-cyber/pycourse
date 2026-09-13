/* ============================================================
   Pycourse — клиент API
   Обращается к настоящему Flask-бэкенду (app.py) вместо
   localStorage. Все функции возвращают Promise.
   ============================================================ */

(function (global) {
  "use strict";

  var BASE = "/api";

  function request(method, url, body, isFormData) {
    var opts = { method: method, credentials: "same-origin" };
    if (body !== undefined) {
      if (isFormData) {
        opts.body = body;
      } else {
        opts.headers = { "Content-Type": "application/json" };
        opts.body = JSON.stringify(body);
      }
    }
    return fetch(BASE + url, opts).then(function (res) {
      return res
        .json()
        .catch(function () { return {}; })
        .then(function (data) {
          if (!res.ok) {
            var err = new Error(data.error || "Ошибка запроса (" + res.status + ")");
            err.status = res.status;
            err.data = data;
            throw err;
          }
          return data;
        });
    });
  }

  var PycourseAPI = {
    /* -------- аутентификация -------- */
    login: function (email, password) {
      return request("POST", "/login", { email: email, password: password }).then(function (d) {
        return d.user;
      });
    },
    logout: function () {
      return request("POST", "/logout");
    },
    me: function () {
      return request("GET", "/me").then(function (d) { return d.user; });
    },
    updateProfile: function (currentPassword, updates) {
      var payload = Object.assign({ currentPassword: currentPassword }, updates);
      return request("PUT", "/me", payload).then(function (d) { return d.user; });
    },

    /* -------- ученики (учитель) -------- */
    listStudents: function () {
      return request("GET", "/students").then(function (d) { return d.students; });
    },
    createStudent: function (name, email, password) {
      return request("POST", "/students", { name: name, email: email, password: password });
    },
    resetStudentPassword: function (id, password) {
      return request("PUT", "/students/" + id + "/password", { password: password });
    },
    deleteStudent: function (id) {
      return request("DELETE", "/students/" + id);
    },

    /* -------- рейтинг -------- */
    getRating: function () {
      return request("GET", "/rating");
    },

    /* -------- уроки -------- */
    listLessons: function () {
      return request("GET", "/lessons").then(function (d) { return d.lessons; });
    },
    listTopics: function () {
      return request("GET", "/lessons/topics").then(function (d) { return d.topics; });
    },
    addLessonUrl: function (title, desc, topic, url) {
      return request("POST", "/lessons", {
        title: title, desc: desc, topic: topic, videoType: "url", videoUrl: url
      }).then(function (d) { return d.lesson; });
    },
    addLessonFile: function (title, desc, topic, file) {
      var fd = new FormData();
      fd.append("title", title);
      fd.append("desc", desc);
      fd.append("topic", topic);
      fd.append("videoType", "file");
      fd.append("file", file);
      return request("POST", "/lessons", fd, true).then(function (d) { return d.lesson; });
    },
    deleteLesson: function (id) {
      return request("DELETE", "/lessons/" + id);
    },
    completeLesson: function (id) {
      return request("POST", "/lessons/" + id + "/complete");
    },
    watchLesson: function (id) {
      return request("POST", "/lessons/" + id + "/watch");
    },

    /* -------- тесты -------- */
    listTests: function (lessonId) {
      var q = lessonId ? ("?lesson_id=" + encodeURIComponent(lessonId)) : "";
      return request("GET", "/tests" + q).then(function (d) { return d.tests; });
    },
    addTest: function (lessonId, question, options, correct) {
      return request("POST", "/tests", {
        lessonId: lessonId, question: question, options: options, correct: correct
      });
    },
    deleteTest: function (id) {
      return request("DELETE", "/tests/" + id);
    },
    submitTest: function (id, chosenIndex) {
      return request("POST", "/tests/" + id + "/submit", { chosenIndex: chosenIndex });
    },

    /* -------- задачи -------- */
    listTasks: function (lessonId) {
      var q = lessonId ? ("?lesson_id=" + encodeURIComponent(lessonId)) : "";
      return request("GET", "/tasks" + q).then(function (d) { return d.tasks; });
    },
    addTask: function (lessonId, title, desc) {
      return request("POST", "/tasks", { lessonId: lessonId, title: title, desc: desc });
    },
    deleteTask: function (id) {
      return request("DELETE", "/tasks/" + id);
    },

    /* -------- чат ученика -------- */
    getChat: function (channel) {
      return request("GET", "/chat/" + channel).then(function (d) { return d.messages; });
    },
    sendChat: function (channel, text) {
      return request("POST", "/chat/" + channel, { text: text });
    },

    /* -------- чат учителя -------- */
    listThreads: function () {
      return request("GET", "/chat/threads").then(function (d) { return d.threads; });
    },
    getAdminChat: function (pupilId) {
      return request("GET", "/chat/admin/" + pupilId).then(function (d) { return d.messages; });
    },
    sendAdminChat: function (pupilId, text) {
      return request("POST", "/chat/admin/" + pupilId, { text: text });
    }
  };

  global.PycourseAPI = PycourseAPI;
})(window);
