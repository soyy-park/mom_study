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
const detailTextEl = document.getElementById("detail-text");

let allCaptures = [];

function formatTime(ts) {
  if (!ts) return "";
  const date = ts.toDate ? ts.toDate() : new Date(ts);
  return date.toLocaleString("ko-KR", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function groupBySubject(captures) {
  const groups = new Map();
  for (const c of captures) {
    const key = c.subject || "무제";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  return new Map([...groups.entries()].sort((a, b) => a[0].localeCompare(b[0], "ko")));
}

function render(filterText) {
  const needle = (filterText || "").trim().toLowerCase();
  const filtered = !needle
    ? allCaptures
    : allCaptures.filter(
        (c) =>
          (c.subject || "").toLowerCase().includes(needle) ||
          (c.full_text || "").toLowerCase().includes(needle)
      );

  subjectGroupsEl.innerHTML = "";
  if (filtered.length === 0) {
    statusEl.textContent = allCaptures.length === 0
      ? "아직 동기화된 캡처가 없습니다."
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
        <div class="capture-preview">${escapeHtml(item.full_text || "(내용 없음)")}</div>
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

function renderDetailText(text) {
  detailTextEl.innerHTML = "";
  const lines = (text || "(내용 없음)").split("\n");
  for (const line of lines) {
    const div = document.createElement("div");
    if (line.startsWith("[정답]")) {
      div.className = "answer-line";
    }
    div.textContent = line;
    detailTextEl.appendChild(div);
  }
}

function showDetail(item) {
  detailSubjectEl.textContent = item.subject || "무제";
  detailTimeEl.textContent = formatTime(item.captured_at);
  renderDetailText(item.full_text);
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
    const q = query(collection(db, "captures"), orderBy("captured_at", "desc"));
    const snapshot = await getDocs(q);
    allCaptures = snapshot.docs.map((doc) => doc.data());
    render(searchInput.value);
  } catch (err) {
    statusEl.textContent = `불러오기 실패: ${err.message}`;
  }
}

load();
