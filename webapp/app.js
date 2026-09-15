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
import {
  getStorage,
  ref,
  uploadBytes,
} from "https://www.gstatic.com/firebasejs/10.14.1/firebase-storage.js";
import { firebaseConfig } from "./firebase-config.js";

// --------------------------------------------------------------------------- #
// 공통: 화면 전환 (홈 / 등록 / 풀기 / 보기-목록 / 보기-상세)
// --------------------------------------------------------------------------- #
const VIEW_IDS = ["home-view", "register-view", "solve-view", "browse-view", "detail-view"];
const homeBtn = document.getElementById("home-btn");

function showView(id) {
  for (const v of VIEW_IDS) {
    document.getElementById(v).hidden = v !== id;
  }
  homeBtn.hidden = id === "home-view";
  window.scrollTo(0, 0);
}

document.querySelectorAll(".menu-card").forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.view;
    showView(target);
    if (target === "browse-view") render(searchInput.value);
    if (target === "solve-view") renderSolveSetup();
  });
});
homeBtn.addEventListener("click", () => showView("home-view"));

// --------------------------------------------------------------------------- #
// Firebase 초기화
// --------------------------------------------------------------------------- #
const app = initializeApp(firebaseConfig);
const db = initializeFirestore(app, {
  localCache: persistentLocalCache({ tabManager: persistentMultipleTabManager() }),
});
const storage = getStorage(app);

let allQuestions = [];

function formatTime(ts) {
  if (!ts) return "";
  const date = ts.toDate ? ts.toDate() : new Date(ts);
  return date.toLocaleString("ko-KR", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
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

async function loadQuestions() {
  if (!firebaseConfig.projectId) return;
  try {
    const q = query(collection(db, "questions"), orderBy("captured_at", "desc"));
    const snapshot = await getDocs(q);
    allQuestions = snapshot.docs.map((doc) => doc.data());
  } catch (err) {
    console.error("불러오기 실패", err);
  }
}

// --------------------------------------------------------------------------- #
// 퀴즈 보기 (목록 + 상세)
// --------------------------------------------------------------------------- #
const subjectGroupsEl = document.getElementById("subject-groups");
const statusEl = document.getElementById("status");
const searchInput = document.getElementById("search-input");
const detailBackBtn = document.getElementById("detail-back-btn");
const detailSubjectEl = document.getElementById("detail-subject");
const detailTimeEl = document.getElementById("detail-time");
const detailQuestionEl = document.getElementById("detail-question");
const detailChoicesEl = document.getElementById("detail-choices");
const detailNoAnswerEl = document.getElementById("detail-no-answer");
const detailExplanationEl = document.getElementById("detail-explanation");

function render(filterText) {
  if (!firebaseConfig.projectId) {
    statusEl.textContent = "webapp/firebase-config.js 에 Firebase 웹 설정값을 채워주세요.";
    return;
  }
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
      ? "아직 등록된 문제가 없습니다. [퀴즈 등록]에서 사진을 올려보세요."
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

function renderChoiceList(el, item) {
  el.innerHTML = "";
  const choices = item.choices || [];
  choices.forEach((choice, i) => {
    const li = document.createElement("li");
    li.className = "choice" + (i + 1 === item.answer_index ? " correct" : "");
    li.textContent = choice;
    el.appendChild(li);
  });
}

function showDetail(item) {
  detailSubjectEl.textContent = item.subject || "무제";
  detailTimeEl.textContent = formatTime(item.captured_at);
  detailQuestionEl.textContent = item.question || "(문제 없음)";
  renderChoiceList(detailChoicesEl, item);
  detailNoAnswerEl.hidden = item.answer_index != null;
  detailExplanationEl.hidden = !item.explanation;
  detailExplanationEl.textContent = item.explanation ? `해설: ${item.explanation}` : "";
  showView("detail-view");
}

detailBackBtn.addEventListener("click", () => showView("browse-view"));
searchInput.addEventListener("input", (e) => render(e.target.value));

// --------------------------------------------------------------------------- #
// 퀴즈 풀기
// --------------------------------------------------------------------------- #
const solveSetupEl = document.getElementById("solve-setup");
const solveSubjectListEl = document.getElementById("solve-subject-list");
const solveQuizEl = document.getElementById("solve-quiz");
const solveResultEl = document.getElementById("solve-result");
const solveProgressEl = document.getElementById("solve-progress");
const solveQuestionEl = document.getElementById("solve-question");
const solveChoicesEl = document.getElementById("solve-choices");
const solveFeedbackEl = document.getElementById("solve-feedback");
const solveExplanationEl = document.getElementById("solve-explanation");
const solveNextBtn = document.getElementById("solve-next-btn");
const solveScoreEl = document.getElementById("solve-score");
const solveRestartBtn = document.getElementById("solve-restart-btn");

let solveQueue = [];
let solveIndex = 0;
let solveScore = 0;

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function solvableQuestions(subject) {
  return allQuestions.filter(
    (q) => q.answer_index != null && (q.choices || []).length > 0
           && (!subject || q.subject === subject)
  );
}

function renderSolveSetup() {
  solveQuizEl.hidden = true;
  solveResultEl.hidden = true;
  solveSetupEl.hidden = false;
  solveSubjectListEl.innerHTML = "";

  const subjects = [...new Set(allQuestions.map((q) => q.subject || "무제"))].sort((a, b) =>
    a.localeCompare(b, "ko")
  );

  const makeBtn = (label, subject) => {
    const count = solvableQuestions(subject).length;
    const btn = document.createElement("button");
    btn.className = "menu-card solve-subject-btn";
    btn.disabled = count === 0;
    btn.innerHTML = `<span class="menu-label">${escapeHtml(label)}</span><span class="menu-desc">${count}문제</span>`;
    btn.addEventListener("click", () => startSolve(subject));
    return btn;
  };

  if (allQuestions.length === 0) {
    solveSubjectListEl.textContent = "아직 등록된 문제가 없습니다.";
    return;
  }
  solveSubjectListEl.appendChild(makeBtn("전체", null));
  for (const subject of subjects) {
    solveSubjectListEl.appendChild(makeBtn(subject, subject));
  }
}

function startSolve(subject) {
  solveQueue = shuffle(solvableQuestions(subject));
  solveIndex = 0;
  solveScore = 0;
  if (solveQueue.length === 0) {
    solveSubjectListEl.textContent = "정답이 확인된 문제가 없어서 풀 수 없습니다.";
    return;
  }
  solveSetupEl.hidden = true;
  solveQuizEl.hidden = false;
  renderSolveQuestion();
}

function renderSolveQuestion() {
  const item = solveQueue[solveIndex];
  solveProgressEl.textContent = `${solveIndex + 1} / ${solveQueue.length}  ·  ${item.subject || "무제"}`;
  solveQuestionEl.textContent = item.question || "(문제 없음)";
  solveFeedbackEl.hidden = true;
  solveExplanationEl.hidden = true;
  solveNextBtn.hidden = true;

  solveChoicesEl.innerHTML = "";
  (item.choices || []).forEach((choice, i) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.className = "choice-btn";
    btn.textContent = choice;
    btn.addEventListener("click", () => answerSolve(i + 1, btn));
    li.appendChild(btn);
    solveChoicesEl.appendChild(li);
  });
}

function answerSolve(pickedIndex, pickedBtn) {
  const item = solveQueue[solveIndex];
  const buttons = [...solveChoicesEl.querySelectorAll(".choice-btn")];
  buttons.forEach((b) => (b.disabled = true));

  const correct = pickedIndex === item.answer_index;
  if (correct) solveScore += 1;

  buttons[item.answer_index - 1].classList.add("correct");
  if (!correct) pickedBtn.classList.add("wrong");

  solveFeedbackEl.hidden = false;
  solveFeedbackEl.textContent = correct ? "정답입니다! 🎉" : "아쉬워요, 다시 확인해보세요.";
  solveFeedbackEl.className = "solve-feedback " + (correct ? "correct" : "wrong");

  if (item.explanation) {
    solveExplanationEl.hidden = false;
    solveExplanationEl.textContent = `해설: ${item.explanation}`;
  }

  solveNextBtn.hidden = false;
}

solveNextBtn.addEventListener("click", () => {
  solveIndex += 1;
  if (solveIndex >= solveQueue.length) {
    solveQuizEl.hidden = true;
    solveResultEl.hidden = false;
    solveScoreEl.textContent = `${solveScore} / ${solveQueue.length} 문제 맞혔습니다.`;
  } else {
    renderSolveQuestion();
  }
});

solveRestartBtn.addEventListener("click", renderSolveSetup);

// --------------------------------------------------------------------------- #
// 퀴즈 등록 (사진 업로드 -> Cloud Function 이 OCR/등록 처리)
// --------------------------------------------------------------------------- #
const registerSubjectInput = document.getElementById("register-subject");
const cameraInput = document.getElementById("camera-input");
const galleryInput = document.getElementById("gallery-input");
const registerStatusEl = document.getElementById("register-status");
const registerQueueEl = document.getElementById("register-queue");

function sanitizeSubject(text) {
  const trimmed = (text || "").trim();
  if (!trimmed) return "무제";
  return trimmed.replace(/[\\/:*?"<>|]/g, "_");
}

function timestampName(offsetSeconds) {
  const d = new Date(Date.now() + offsetSeconds * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  const date = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
  const time = `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  return `${date}_${time}`;
}

function addQueueItem(label) {
  const li = document.createElement("li");
  li.className = "register-queue-item";
  li.textContent = label;
  registerQueueEl.prepend(li);
  return li;
}

async function uploadPhoto(file, offsetSeconds) {
  const subject = sanitizeSubject(registerSubjectInput.value);
  const ext = (file.name.split(".").pop() || "jpg").toLowerCase();
  const filename = `${subject}_${timestampName(offsetSeconds)}.${ext}`;
  const item = addQueueItem(`${filename} - 업로드 중...`);
  try {
    await uploadBytes(ref(storage, `uploads/${filename}`), file, {
      contentType: file.type || "image/jpeg",
    });
    item.textContent = `${filename} - 업로드 완료! 잠시 후 [퀴즈 보기]에 나타납니다.`;
    item.classList.add("done");
  } catch (err) {
    item.textContent = `${filename} - 업로드 실패: ${err.message}`;
    item.classList.add("failed");
  }
}

async function handleFiles(fileList) {
  const files = [...fileList];
  if (files.length === 0) return;
  registerStatusEl.textContent = `${files.length}장 업로드 중...`;
  await Promise.all(files.map((file, i) => uploadPhoto(file, i)));
  registerStatusEl.textContent = "";
}

cameraInput.addEventListener("change", (e) => {
  handleFiles(e.target.files);
  e.target.value = "";
});
galleryInput.addEventListener("change", (e) => {
  handleFiles(e.target.files);
  e.target.value = "";
});

// --------------------------------------------------------------------------- #
loadQuestions();
