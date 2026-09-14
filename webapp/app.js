import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import {
  collection,
  query,
  orderBy,
  getDocs,
  persistentLocalCache,
  persistentMultipleTabManager,
  initializeFirestore,
} from "https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js";
import { firebaseConfig } from "./firebase-config.js";

const listView = document.getElementById("list-view");
const detailView = document.getElementById("detail-view");
const subjectGroupsEl = document.getElementById("subject-groups");
const statusEl = document.getElementById("status");
const searchInput = document.getElementById("search-input");
const backBtn = document.getElementById("back-btn");
const detailSubjectEl = document.getElementById("detail-subject");
const detailTimeEl = document.getElementById("detail-time");
const detailQuestionEl = document.getElementById("detail-question");
const detailChoicesEl = document.getElementById("detail-choices");
const detailNoAnswerEl = document.getElementById("detail-no-answer");

let allQuestions = [];

function formatTime(ts) {
  if (!ts) return "";
  const date = ts.toDate ? ts.toDate() : new Date(ts);
  return date.toLocaleString("ko-KR", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function groupBySubject(questions) {
  const groups = new Map();
  for (const q of questions) {
    const key = q.subject || "무제";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(q);
  }
  return new Map([...groups.entries()].sort((a, b) => a[0].localeCompare(b[0], "ko")));
}

function render(filterText) {
  const needle = (filterText || "").trim().toLowerCase();
  const filtered = !needle
    ? allQuestions
    : allQuestions.filter(
        (q) =>
          (q.subject || "").toLowerCase().includes(needle) ||
          (q.question || "").toLowerCase().includes(needle) ||
          (q.choices || []).some((c) => c.toLowerCase().includes(needle))
      );

  subjectGroupsEl.innerHTML = "";
  if (filtered.length === 0) {
    statusEl.textContent = allQuestions.length === 0
      ? "아직 동기화된 문제가 없습니다."
      : "검색 결과가 없습니다.";
    return;
  }
  statusEl.textContent = `${filtered.length}개`;

  for (const [subject, items] of groupBySubject(filtered)) {
    const groupEl = document.createElement("section");
    groupEl.className = "subject-group";

    const title = document.createElement("h2");
    title.className = "subject-title";
    title.textContent = `${subject} (${items.length})`;
    groupEl.appendChild(title);

    for (const item of items) {
      const card = document.createElement("div");
      card.className = "capture-card";
      card.innerHTML = `
        <div class="capture-time">${formatTime(item.captured_at)}</div>
        <div class="capture-preview">${escapeHtml(item.question || "(문제 없음)")}</div>
      `;
      card.addEventListener("click", () => showDetail(item));
      groupEl.appendChild(card);
    }
    subjectGroupsEl.appendChild(groupEl);
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderDetailChoices(item) {
  detailChoicesEl.innerHTML = "";
  const choices = item.choices || [];
  choices.forEach((choice, i) => {
    const li = document.createElement("li");
    li.className = "choice" + (i + 1 === item.answer_index ? " correct" : "");
    li.textContent = choice;
    detailChoicesEl.appendChild(li);
  });
  detailNoAnswerEl.hidden = item.answer_index != null;
}

function showDetail(item) {
  detailSubjectEl.textContent = item.subject || "무제";
  detailTimeEl.textContent = formatTime(item.captured_at);
  detailQuestionEl.textContent = item.question || "(문제 없음)";
  renderDetailChoices(item);
  listView.hidden = true;
  detailView.hidden = false;
  window.scrollTo(0, 0);
}

backBtn.addEventListener("click", () => {
  detailView.hidden = true;
  listView.hidden = false;
});

searchInput.addEventListener("input", (e) => render(e.target.value));

async function load() {
  if (!firebaseConfig.projectId) {
    statusEl.textContent = "webapp/firebase-config.js 에 Firebase 웹 설정값을 채워주세요.";
    return;
  }
  statusEl.textContent = "불러오는 중...";
  try {
    const app = initializeApp(firebaseConfig);
    const db = initializeFirestore(app, {
      localCache: persistentLocalCache({ tabManager: persistentMultipleTabManager() }),
    });
    const q = query(collection(db, "questions"), orderBy("captured_at", "desc"));
    const snapshot = await getDocs(q);
    allQuestions = snapshot.docs.map((doc) => doc.data());
    render(searchInput.value);
  } catch (err) {
    statusEl.textContent = `불러오기 실패: ${err.message}`;
  }
}

load();
