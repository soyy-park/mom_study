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
import { profileConfig } from "./profile-config.js";

document.getElementById("profile-name").textContent = `${profileConfig.name} 님`;
document.getElementById("profile-major").textContent = profileConfig.major;
document.getElementById("profile-avatar").textContent = profileConfig.name.slice(0, 1);

// --------------------------------------------------------------------------- #
// 공통: 화면 전환 (홈 / 등록 / 풀기 / 보기-목록 / 보기-상세)
// --------------------------------------------------------------------------- #
const VIEW_IDS = ["home-view", "register-view", "solve-view", "browse-view"];

// 화면마다 URL 해시(#register, #solve, #browse)를 붙여서 브라우저 뒤로/앞으로
// 가기 버튼과 새로고침이 실제로 동작하게 한다(전에는 전부 같은 주소라 안 먹혔음).
const HASH_TO_VIEW = { "": "home-view", register: "register-view", solve: "solve-view", browse: "browse-view" };
const VIEW_TO_HASH = { "home-view": "", "register-view": "register", "solve-view": "solve", "browse-view": "browse" };

function showView(id) {
  for (const v of VIEW_IDS) {
    document.getElementById(v).hidden = v !== id;
  }
  window.scrollTo(0, 0);
}

// 실제 화면 전환(DOM 토글 + 화면별 초기화). URL은 이미 맞춰져 있다고 가정한다.
function applyView(id) {
  showView(id);
  if (id === "browse-view") render();
  if (id === "solve-view") renderSolveSetup();
}

// 사용자 조작(메뉴 클릭 등)으로 화면을 옮길 때는 이걸 호출한다 — 해시를 바꾸고,
// 그 결과로 발생하는 hashchange 이벤트가 applyView를 실행한다.
function navigateTo(id) {
  const hash = VIEW_TO_HASH[id] ?? "";
  if (location.hash.replace(/^#/, "") === hash) {
    applyView(id);
  } else {
    location.hash = hash;
  }
}

window.addEventListener("hashchange", () => {
  const id = HASH_TO_VIEW[location.hash.replace(/^#/, "")] || "home-view";
  applyView(id);
});

document.querySelectorAll(".menu-card").forEach((btn) => {
  btn.addEventListener("click", () => navigateTo(btn.dataset.view));
});
document.getElementById("brand-home-btn").addEventListener("click", () => navigateTo("home-view"));

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

const homeQuizCountEl = document.getElementById("home-quiz-count");

async function loadQuestions() {
  if (!firebaseConfig.projectId) {
    homeQuizCountEl.textContent = "설정이 필요해요";
    return;
  }
  try {
    const q = query(collection(db, "questions"), orderBy("captured_at", "desc"));
    const snapshot = await getDocs(q);
    allQuestions = snapshot.docs.map((doc) => doc.data());
  } catch (err) {
    console.error("불러오기 실패", err);
  }
  homeQuizCountEl.textContent = `누적 ${allQuestions.length}문제 보관`;
  populateBrowseFilters();
  // 새로고침으로 #browse/#solve에 바로 들어온 경우, 이 데이터 로딩이 끝나기 전에
  // 이미 한 번 렌더링됐을 수 있으므로 최신 데이터로 다시 그린다.
  if (!document.getElementById("browse-view").hidden) render();
  if (!document.getElementById("solve-view").hidden) renderSolveSetup();
}

// --------------------------------------------------------------------------- #
// 모아보기 (목록 + 상세 팝업)
// --------------------------------------------------------------------------- #
const subjectGroupsEl = document.getElementById("subject-groups");
const statusEl = document.getElementById("status");
const browseQuoteEl = document.getElementById("browse-quote");
const searchInput = document.getElementById("search-input");
const browseSearchToggleBtn = document.getElementById("browse-search-toggle-btn");
const browseSearchBoxEl = document.getElementById("browse-search-box");
const detailDrawerEl = document.getElementById("detail-drawer");
const detailSubjectEl = document.getElementById("detail-subject");
const detailTimeEl = document.getElementById("detail-time");
const detailQuestionEl = document.getElementById("detail-question");
const detailChoicesEl = document.getElementById("detail-choices");
const detailNoAnswerEl = document.getElementById("detail-no-answer");
const detailExplanationEl = document.getElementById("detail-explanation");
const detailExplanationTextEl = document.getElementById("detail-explanation-text");

browseSearchToggleBtn.addEventListener("click", () => {
  browseSearchBoxEl.hidden = !browseSearchBoxEl.hidden;
  if (!browseSearchBoxEl.hidden) searchInput.focus();
});

function populateBrowseFilters() {
  const grades = new Set();
  const semesters = new Set();
  const examTypes = new Set();
  const subjectCounts = new Map();
  for (const q of allQuestions) {
    const meta = parseSubjectMeta(q.subject);
    if (meta.grade) grades.add(meta.grade);
    if (meta.semester) semesters.add(meta.semester);
    if (meta.examType) examTypes.add(meta.examType);
    subjectCounts.set(meta.baseSubject, (subjectCounts.get(meta.baseSubject) || 0) + 1);
  }
  browseGradeMultiSelect.setEntries([...grades].sort((a, b) => a - b).map((g) => [g, `${g}학년`]));
  browseSemesterMultiSelect.setEntries([...semesters].sort((a, b) => a - b).map((s) => [s, `${s}학기`]));
  browseExamMultiSelect.setEntries([...examTypes].sort().map((e) => [e, e]));
  browseSubjectMultiSelect.setEntries(
    [...subjectCounts.entries()]
      .sort((a, b) => a[0].localeCompare(b[0], "ko"))
      .map(([subject, count]) => [subject, `${subject} (${count}건)`])
  );
}

function browseCard(item) {
  const meta = parseSubjectMeta(item.subject);
  const gradeSemester = meta.grade && meta.semester ? `${meta.grade}학년 ${meta.semester}학기` : "";
  const hasAnswer = item.answer_index != null;
  const badges = [`<span class="px-2 py-0.5 rounded bg-surface-container-high text-on-surface-variant font-label-sm text-[12px] font-medium">${escapeHtml(meta.baseSubject)}</span>`];
  if (gradeSemester) badges.push(`<span class="text-outline-variant font-label-sm">·</span><span class="text-on-surface-variant font-label-sm text-[12px]">${escapeHtml(gradeSemester)}</span>`);
  if (meta.examType) badges.push(`<span class="text-outline-variant font-label-sm">·</span><span class="text-on-surface-variant font-label-sm text-[12px]">${escapeHtml(meta.examType)}</span>`);

  const card = document.createElement("article");
  card.className = "group relative bg-surface-container-lowest rounded-2xl p-space-md sm:p-space-lg shadow-sm hover:shadow-md transition-all active:scale-[0.99] cursor-pointer";
  card.innerHTML = `
    <div class="absolute left-0 top-6 bottom-6 w-1 rounded-r bg-secondary/30 group-hover:bg-primary transition-colors"></div>
    <div class="flex items-start justify-between gap-space-md">
      <div class="flex-1 min-w-0">
        <div class="flex flex-wrap items-center gap-2 mb-2">${badges.join("")}</div>
        <h2 class="font-body-lg text-body-lg font-semibold text-on-surface leading-snug tracking-tight mb-3">${escapeHtml(item.question || "(문제 없음)")}</h2>
        <div class="flex flex-wrap items-center gap-y-1 gap-x-3 text-on-surface-variant font-label-sm text-label-sm pt-1">
          <span class="flex items-center gap-1 text-outline"><span class="material-symbols-outlined text-[16px]">calendar_today</span>${escapeHtml(formatTime(item.captured_at))}</span>
          <span class="text-outline-variant">|</span>
          <span class="flex items-center gap-1 ${hasAnswer ? "text-primary" : "text-tertiary"} font-semibold"><span class="material-symbols-outlined text-[17px]">${hasAnswer ? "check_circle" : "help"}</span>${hasAnswer ? "정답 표시됨" : "정답 미확인"}</span>
          <span class="text-outline-variant">|</span>
          <span class="bg-surface-container px-2 py-0.5 rounded text-[12px] text-on-secondary-container">${(item.choices || []).length}지 선다형</span>
        </div>
      </div>
      <div class="shrink-0 flex items-center justify-center w-12 h-12 rounded-xl bg-surface-container-low group-hover:bg-primary-container group-hover:text-on-primary-container text-on-surface-variant transition-colors self-center">
        <span class="material-symbols-outlined text-[28px] transition-transform group-hover:translate-x-0.5">chevron_right</span>
      </div>
    </div>
  `;
  card.addEventListener("click", () => showDetail(item));
  return card;
}

function render() {
  if (!firebaseConfig.projectId) {
    statusEl.textContent = "webapp/firebase-config.js 에 Firebase 웹 설정값을 채워주세요.";
    return;
  }
  browseQuoteEl.textContent = `차곡차곡 모아둔 문제가 벌써 ${allQuestions.length}개 쌓였어요!`;

  const needle = searchInput.value.trim().toLowerCase();
  const filters = {
    grade: browseGradeMultiSelect.getSelected(),
    semester: browseSemesterMultiSelect.getSelected(),
    examType: browseExamMultiSelect.getSelected(),
    subject: browseSubjectMultiSelect.getSelected(),
  };

  const filtered = allQuestions.filter((q) => {
    if (!matchesSetupFilters(parseSubjectMeta(q.subject), filters)) return false;
    if (!needle) return true;
    return (
      (q.subject || "").toLowerCase().includes(needle) ||
      (q.question || "").toLowerCase().includes(needle) ||
      (q.choices || []).some((c) => c.toLowerCase().includes(needle))
    );
  });

  subjectGroupsEl.innerHTML = "";
  if (filtered.length === 0) {
    statusEl.textContent = allQuestions.length === 0
      ? "아직 등록된 문제가 없습니다. [퀴즈 등록]에서 사진을 올려보세요."
      : "조건에 맞는 문제가 없습니다.";
    return;
  }
  statusEl.innerHTML = `<span class="w-2 h-2 rounded-full bg-primary"></span>총 <strong class="text-on-surface font-semibold text-body-md">${filtered.length}건</strong>의 지난 문제`;
  for (const item of filtered) subjectGroupsEl.appendChild(browseCard(item));
}

function renderChoiceList(el, item) {
  el.innerHTML = "";
  const choices = item.choices || [];
  choices.forEach((choice, i) => {
    const correct = i + 1 === item.answer_index;
    const li = document.createElement("li");
    li.className = `p-3 rounded-xl flex items-center justify-between gap-2.5 font-body-md text-body-md text-on-surface ${
      correct ? "bg-primary-fixed/40 ring-2 ring-primary" : "bg-surface-container-low"
    }`;
    li.innerHTML = `
      <span class="flex items-center gap-2.5"><span class="font-semibold ${correct ? "text-primary" : "text-secondary"}">${choiceLabel(i)}</span> ${escapeHtml(choice)}</span>
      ${correct ? '<span class="font-label-sm text-[12px] bg-primary text-on-primary px-2 py-0.5 rounded font-bold shrink-0">정답</span>' : ""}
    `;
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
  detailExplanationTextEl.textContent = item.explanation ? formatExplanation(item.explanation) : "";
  detailDrawerEl.hidden = false;
}

function closeDetailDrawer() {
  detailDrawerEl.hidden = true;
}

document.getElementById("detail-close-btn").addEventListener("click", closeDetailDrawer);
document.getElementById("detail-close-btn-2").addEventListener("click", closeDetailDrawer);
detailDrawerEl.addEventListener("click", (e) => {
  if (e.target === detailDrawerEl) closeDetailDrawer();
});

searchInput.addEventListener("input", () => render());

// --------------------------------------------------------------------------- #
// 퀴즈 풀기
// --------------------------------------------------------------------------- #
const solveSetupEl = document.getElementById("solve-setup");
const solveQuizEl = document.getElementById("solve-quiz");
const solveResultEl = document.getElementById("solve-result");
const solveProgressEl = document.getElementById("solve-progress");
const solveSubjectBadgeEl = document.getElementById("solve-subject-badge");
const solveQuestionBadgeEl = document.getElementById("solve-question-badge");
const solveResultBannerEl = document.getElementById("solve-result-banner");
const solveResultDetailEl = document.getElementById("solve-result-detail");
const solveQuestionEl = document.getElementById("solve-question");
const solveChoicesEl = document.getElementById("solve-choices");
const solveCheckBtn = document.getElementById("solve-check-btn");
const solveCorrectBarEl = document.getElementById("solve-correct-bar");
const solveWrongBoxEl = document.getElementById("solve-wrong-box");
const solveRetryBtn = document.getElementById("solve-retry-btn");
const solveExplanationCardEl = document.getElementById("solve-explanation-card");
const solveAnswerTagEl = document.getElementById("solve-answer-tag");
const solveExplanationEl = document.getElementById("solve-explanation");
const solveReviewAgainBtn = document.getElementById("solve-review-again-btn");
const solveNextBtn = document.getElementById("solve-next-btn");
const solveQuizBackBtn = document.getElementById("solve-quiz-back-btn");
const solveScoreEl = document.getElementById("solve-score");
const solveRestartBtn = document.getElementById("solve-restart-btn");
// 시험 범위 필터: 드롭다운 버튼 + 체크박스 패널로 복수 선택을 지원한다.
const openMultiSelectPanels = [];

function createMultiSelect({ btnId, labelId, panelId, allLabel, onChange }) {
  const btn = document.getElementById(btnId);
  const labelEl = document.getElementById(labelId);
  const panel = document.getElementById(panelId);
  let entries = [];
  const selected = new Set();

  function rowClass(checked) {
    return `flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer font-label-sm text-label-sm transition-colors ${
      checked ? "bg-primary-container text-on-primary font-semibold" : "hover:bg-surface-container text-on-surface"
    }`;
  }

  function updateLabel() {
    if (selected.size === 0) {
      labelEl.textContent = allLabel;
    } else if (selected.size === 1) {
      const value = [...selected][0];
      const found = entries.find(([v]) => v === value);
      labelEl.textContent = found ? found[1] : allLabel;
    } else {
      labelEl.textContent = `${selected.size}개 선택`;
    }
  }

  function render() {
    panel.innerHTML = "";
    if (entries.length === 0) {
      const empty = document.createElement("div");
      empty.className = "px-2.5 py-2 font-label-sm text-label-sm text-on-surface-variant";
      empty.textContent = "선택할 항목이 없어요";
      panel.appendChild(empty);
      return;
    }
    entries.forEach(([value, text]) => {
      const row = document.createElement("label");
      row.className = rowClass(selected.has(value));
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "w-4 h-4 shrink-0 accent-primary";
      cb.checked = selected.has(value);
      cb.addEventListener("change", () => {
        if (cb.checked) selected.add(value);
        else selected.delete(value);
        row.className = rowClass(cb.checked);
        updateLabel();
        onChange?.();
      });
      const span = document.createElement("span");
      span.className = "flex-1 truncate";
      span.textContent = text;
      row.appendChild(cb);
      row.appendChild(span);
      panel.appendChild(row);
    });
  }

  function close() {
    panel.hidden = true;
  }
  openMultiSelectPanels.push(close);

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const willOpen = panel.hidden;
    openMultiSelectPanels.forEach((fn) => fn());
    panel.hidden = !willOpen;
  });
  panel.addEventListener("click", (e) => e.stopPropagation());

  return {
    setEntries(newEntries) {
      entries = newEntries;
      selected.clear();
      updateLabel();
      render();
    },
    getSelected: () => selected,
    reset() {
      selected.clear();
      updateLabel();
      render();
    },
  };
}

document.addEventListener("click", () => {
  openMultiSelectPanels.forEach((fn) => fn());
});

const gradeMultiSelect = createMultiSelect({
  btnId: "filter-grade-btn",
  labelId: "filter-grade-label",
  panelId: "filter-grade-panel",
  allLabel: "전체 학년",
  onChange: () => updateSolveSetupSummary(),
});
const semesterMultiSelect = createMultiSelect({
  btnId: "filter-semester-btn",
  labelId: "filter-semester-label",
  panelId: "filter-semester-panel",
  allLabel: "전체 학기",
  onChange: () => updateSolveSetupSummary(),
});
const examMultiSelect = createMultiSelect({
  btnId: "filter-exam-btn",
  labelId: "filter-exam-label",
  panelId: "filter-exam-panel",
  allLabel: "전체 시험",
  onChange: () => updateSolveSetupSummary(),
});
const subjectMultiSelect = createMultiSelect({
  btnId: "filter-subject-btn",
  labelId: "filter-subject-label",
  panelId: "filter-subject-panel",
  allLabel: "전체 과목",
  onChange: () => updateSolveSetupSummary(),
});

// 모아보기 화면의 시험 범위 필터도 같은 드롭다운(체크박스 패널) 컴포넌트를 재사용한다.
const browseGradeMultiSelect = createMultiSelect({
  btnId: "browse-filter-grade-btn",
  labelId: "browse-filter-grade-label",
  panelId: "browse-filter-grade-panel",
  allLabel: "전체 학년",
  onChange: () => render(),
});
const browseSemesterMultiSelect = createMultiSelect({
  btnId: "browse-filter-semester-btn",
  labelId: "browse-filter-semester-label",
  panelId: "browse-filter-semester-panel",
  allLabel: "전체 학기",
  onChange: () => render(),
});
const browseExamMultiSelect = createMultiSelect({
  btnId: "browse-filter-exam-btn",
  labelId: "browse-filter-exam-label",
  panelId: "browse-filter-exam-panel",
  allLabel: "전체 시험",
  onChange: () => render(),
});
const browseSubjectMultiSelect = createMultiSelect({
  btnId: "browse-filter-subject-btn",
  labelId: "browse-filter-subject-label",
  panelId: "browse-filter-subject-panel",
  allLabel: "전체 과목",
  onChange: () => render(),
});

const solveCountGroupEl = document.getElementById("solve-count-group");
const solveSetupSummaryEl = document.getElementById("solve-setup-summary");
const solveStartBtn = document.getElementById("solve-start-btn");
const solveStartLabelEl = document.getElementById("solve-start-label");
const solveSetupBackBtn = document.getElementById("solve-setup-back-btn");
const solveResetBtn = document.getElementById("solve-reset-btn");

let solveQueue = [];
let solveIndex = 0;
let solveScore = 0;
let solveMissedThisQuestion = false; // 이번 문제에서 오답을 한 번이라도 골랐는지
let solveSelectedIndex = null; // 정답 확인 전, 지금 고른(아직 채점 안 한) 보기
let solveAnswered = false; // 이번 문제를 채점했는지(정답을 맞혀서 끝났는지)
let solveWrongIndexes = new Set(); // 이번 문제에서 오답으로 확인된 보기 번호들
let solveScoredThisQuestion = false; // 이번 문제로 이미 점수를 받았는지(다시 풀기로 중복 채점 방지)
let solveSelectedCount = "20"; // 퀴즈 설정에서 고른 출제 문항 수("10"/"20"/"30"/"all")

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function solvableQuestions() {
  return allQuestions.filter((q) => q.answer_index != null && (q.choices || []).length > 0);
}

// 등록 화면(currentSubjectLabel())이 "정보처리기사 3학년2학기 중간고사"처럼
// 과목/학년학기/시험종류를 한 문자열로 합쳐서 저장하므로, 필터링을 위해 여기서 다시 분리한다.
const GRADE_SEMESTER_RE = /^(\d+)학년(\d+)학기$/;
const EXAM_TYPE_RE = /^(중간고사|기말고사)$/;

function parseSubjectMeta(subject) {
  const tokens = (subject || "무제").trim().split(/\s+/);
  let grade = null;
  let semester = null;
  let examType = null;
  while (tokens.length > 1) {
    const last = tokens[tokens.length - 1];
    const gs = last.match(GRADE_SEMESTER_RE);
    if (gs) {
      grade = gs[1];
      semester = gs[2];
      tokens.pop();
      continue;
    }
    if (EXAM_TYPE_RE.test(last)) {
      examType = last;
      tokens.pop();
      continue;
    }
    break;
  }
  return { baseSubject: tokens.join(" "), grade, semester, examType };
}

function currentSetupFilters() {
  return {
    grade: gradeMultiSelect.getSelected(),
    semester: semesterMultiSelect.getSelected(),
    examType: examMultiSelect.getSelected(),
    subject: subjectMultiSelect.getSelected(),
  };
}

// 각 필터는 빈 선택(Set 크기 0)이면 "전체"로 취급하고, 하나 이상 고르면 그중 하나만
// 맞아도 통과시킨다(OR 조건) — 예: 학년에서 "1학년"과 "2학년"을 함께 선택.
function matchesSetupFilters(meta, filters) {
  if (filters.grade.size > 0 && !filters.grade.has(meta.grade)) return false;
  if (filters.semester.size > 0 && !filters.semester.has(meta.semester)) return false;
  if (filters.examType.size > 0 && !filters.examType.has(meta.examType)) return false;
  if (filters.subject.size > 0 && !filters.subject.has(meta.baseSubject)) return false;
  return true;
}

function filteredSolvableQuestions(filters) {
  return solvableQuestions().filter((q) => matchesSetupFilters(parseSubjectMeta(q.subject), filters));
}

function renderSolveSetup() {
  solveQuizEl.hidden = true;
  solveResultEl.hidden = true;
  solveSetupEl.hidden = false;

  const pool = solvableQuestions();
  if (pool.length === 0) {
    solveSetupSummaryEl.textContent = "아직 정답이 확인된 문제가 없습니다.";
    solveStartBtn.disabled = true;
    solveStartBtn.classList.add("opacity-40", "pointer-events-none");
    return;
  }
  solveStartBtn.disabled = false;
  solveStartBtn.classList.remove("opacity-40", "pointer-events-none");

  const grades = new Set();
  const semesters = new Set();
  const examTypes = new Set();
  const subjectCounts = new Map();
  pool.forEach((q) => {
    const meta = parseSubjectMeta(q.subject);
    if (meta.grade) grades.add(meta.grade);
    if (meta.semester) semesters.add(meta.semester);
    if (meta.examType) examTypes.add(meta.examType);
    subjectCounts.set(meta.baseSubject, (subjectCounts.get(meta.baseSubject) || 0) + 1);
  });

  gradeMultiSelect.setEntries([...grades].sort((a, b) => a - b).map((g) => [g, `${g}학년`]));
  semesterMultiSelect.setEntries([...semesters].sort((a, b) => a - b).map((s) => [s, `${s}학기`]));
  examMultiSelect.setEntries([...examTypes].sort().map((e) => [e, e]));
  subjectMultiSelect.setEntries(
    [...subjectCounts.entries()]
      .sort((a, b) => a[0].localeCompare(b[0], "ko"))
      .map(([subject, count]) => [subject, `${subject} (${count}제)`])
  );

  updateSolveSetupSummary();
}

function updateSolveSetupSummary() {
  const pool = filteredSolvableQuestions(currentSetupFilters());
  const poolSize = pool.length;
  const effectiveCount = solveSelectedCount === "all" ? poolSize : Math.min(Number(solveSelectedCount), poolSize);

  if (poolSize === 0) {
    solveSetupSummaryEl.textContent = "선택한 조건에 맞는 문제가 없어요. 조건을 조정해보세요.";
  } else {
    solveSetupSummaryEl.innerHTML = `선택 조건에 해당하는 <strong>${poolSize}문제</strong> 중 <strong class="text-primary">${effectiveCount}문제</strong>를 무작위로 준비합니다.`;
  }
  solveStartLabelEl.textContent = poolSize === 0 ? "랜덤 퀴즈 시작하기" : `랜덤 퀴즈 시작하기 (${effectiveCount}문항)`;
}

const COUNT_BTN_BASE =
  "count-btn min-h-[54px] rounded-2xl bg-surface-container hover:bg-surface-container-high border border-outline-variant/40 shadow-sm flex items-center justify-center font-headline-md text-body-xl font-bold text-on-surface transition-all";
const COUNT_BTN_ACTIVE =
  "count-btn min-h-[54px] rounded-2xl bg-primary-container ring-2 ring-primary/20 shadow-lg flex items-center justify-center font-headline-md text-body-xl font-bold text-on-primary transition-all";

[...solveCountGroupEl.querySelectorAll("button")].forEach((btn) => {
  btn.addEventListener("click", () => {
    solveSelectedCount = btn.dataset.count;
    [...solveCountGroupEl.querySelectorAll("button")].forEach((b) => {
      b.className = b === btn ? COUNT_BTN_ACTIVE : COUNT_BTN_BASE;
    });
    updateSolveSetupSummary();
  });
});

solveResetBtn.addEventListener("click", () => {
  gradeMultiSelect.reset();
  semesterMultiSelect.reset();
  examMultiSelect.reset();
  subjectMultiSelect.reset();
  solveSelectedCount = "20";
  [...solveCountGroupEl.querySelectorAll("button")].forEach((b) => {
    b.className = b.dataset.count === "20" ? COUNT_BTN_ACTIVE : COUNT_BTN_BASE;
  });
  updateSolveSetupSummary();
});

solveSetupBackBtn.addEventListener("click", () => navigateTo("home-view"));

solveStartBtn.addEventListener("click", () => {
  const pool = filteredSolvableQuestions(currentSetupFilters());
  let queue = shuffle(pool);
  if (solveSelectedCount !== "all") queue = queue.slice(0, Number(solveSelectedCount));
  solveQueue = queue;
  solveIndex = 0;
  solveScore = 0;
  if (solveQueue.length === 0) return;
  solveSetupEl.hidden = true;
  solveQuizEl.hidden = false;
  renderSolveQuestion();
});

const CIRCLED_DIGITS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";
function choiceLabel(i) {
  return CIRCLED_DIGITS[i] || `${i + 1}.`;
}

// 해설 안에 ①②③... 같은 번호가 나오면 무조건 그 앞에서 줄을 바꾼다
// (원문에 줄바꿈이 없어도 강제로 끊어서 읽기 쉽게 만든다).
function formatExplanation(text) {
  // 원문에 이미 섞여 있는 줄바꿈(OCR 줄바꿈 등)은 먼저 공백으로 합쳐서 단어 중간에
  // 끊기는 걸 막고, ①②③... 앞에서만 우리가 원하는 줄바꿈을 새로 넣는다.
  const normalized = (text || "").replace(/\s+/g, " ").trim();
  return normalized
    .split(new RegExp(`(?=[${CIRCLED_DIGITS}])`, "g"))
    .map((s) => s.trim())
    .filter(Boolean)
    .join("\n");
}

const CHOICE_BASE =
  "choice-btn w-full min-h-[40px] p-2 rounded-xl text-left transition-all duration-150 flex items-start sm:items-center justify-between gap-2 bg-surface-container-low hover:bg-surface-container text-on-surface shadow-sm";
const CHOICE_NUM_BASE =
  "choice-num w-6 h-6 rounded-full bg-surface-container-high text-secondary flex items-center justify-center font-label-sm text-label-sm font-bold shrink-0";
const CHOICE_TEXT_BASE = "choice-text font-body-md text-body-md leading-snug";

const CHOICE_PRIMARY =
  "choice-btn w-full min-h-[40px] p-2 rounded-xl text-left transition-all duration-150 flex items-start sm:items-center justify-between gap-2 bg-primary-fixed/40 text-on-surface shadow-md ring-2";
const CHOICE_NUM_PRIMARY =
  "choice-num w-6 h-6 rounded-full bg-primary text-on-primary flex items-center justify-center font-label-sm text-label-sm font-bold shrink-0 shadow-sm";
const CHOICE_TEXT_SELECTED = "choice-text font-body-md text-body-md font-semibold text-on-surface leading-snug";
const CHOICE_TEXT_CORRECT = "choice-text font-body-md text-body-md font-bold text-primary leading-snug";

const CHOICE_WRONG =
  "choice-btn w-full min-h-[40px] p-2 rounded-xl text-left transition-all duration-150 flex items-start sm:items-center justify-between gap-2 bg-error-container/60 text-on-surface shadow-md ring-2 ring-error/50";
const CHOICE_NUM_WRONG =
  "choice-num w-6 h-6 rounded-full bg-error text-on-error flex items-center justify-center font-label-sm text-label-sm font-bold shrink-0 shadow-sm";

const CHECK_BTN_DISABLED =
  "w-full min-h-[40px] rounded-xl bg-surface-container-highest text-outline font-label-md text-label-md flex items-center justify-center gap-1.5 cursor-not-allowed";
const CHECK_BTN_ENABLED =
  "w-full min-h-[40px] rounded-xl bg-primary-container text-on-primary font-label-md text-label-md shadow-md hover:bg-primary active:translate-y-0.5 transition-all flex items-center justify-center gap-1.5";

const CORRECT_BADGE_HTML =
  '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary text-on-primary font-label-sm text-label-sm font-bold shadow-sm">정답<span class="material-symbols-outlined text-[16px]">check</span></span>';
const WRONG_BADGE_HTML =
  '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-[#c24130] text-white font-label-sm text-label-sm font-bold shadow-sm">오답<span class="material-symbols-outlined text-[16px] text-white">close</span></span>';

function renderSolveQuestion() {
  const item = solveQueue[solveIndex];
  solveProgressEl.textContent = `Q ${solveIndex + 1} / ${solveQueue.length}`;
  solveSubjectBadgeEl.textContent = item.subject || "무제";
  solveQuestionBadgeEl.textContent = `기출 문항 ${String(solveIndex + 1).padStart(2, "0")}`;
  solveQuestionEl.textContent = item.question || "(문제 없음)";
  solveResultBannerEl.hidden = true;
  solveExplanationCardEl.hidden = true;
  solveSelectedIndex = null;
  solveAnswered = false;
  solveMissedThisQuestion = false;
  solveWrongIndexes = new Set();
  solveScoredThisQuestion = false;

  renderChoices(item);
  showActionState("ready");
}

function renderChoices(item) {
  solveChoicesEl.innerHTML = "";
  (item.choices || []).forEach((choice, i) => {
    const idx = i + 1;
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.index = idx;
    btn.className = CHOICE_BASE;

    const left = document.createElement("div");
    left.className = "flex items-start sm:items-center gap-2 flex-1";
    const num = document.createElement("span");
    num.className = CHOICE_NUM_BASE;
    num.textContent = choiceLabel(i);
    const text = document.createElement("span");
    text.className = CHOICE_TEXT_BASE;
    text.textContent = choice;
    left.appendChild(num);
    left.appendChild(text);

    const badge = document.createElement("div");
    badge.className = "choice-badge flex items-center gap-2 shrink-0";
    badge.hidden = true;

    btn.appendChild(left);
    btn.appendChild(badge);
    btn.addEventListener("click", () => selectChoice(idx, btn));
    li.appendChild(btn);
    solveChoicesEl.appendChild(li);
  });
}

function selectChoice(idx, btn) {
  if (solveAnswered) return;
  solveSelectedIndex = idx;
  [...solveChoicesEl.querySelectorAll("button")].forEach((b) => {
    if (solveWrongIndexes.has(Number(b.dataset.index))) return; // 이미 오답으로 확인된 보기는 그대로 둔다
    const isSelected = b === btn;
    b.className = isSelected ? CHOICE_PRIMARY : CHOICE_BASE;
    b.querySelector(".choice-num").className = isSelected ? CHOICE_NUM_PRIMARY : CHOICE_NUM_BASE;
    b.querySelector(".choice-text").className = isSelected ? CHOICE_TEXT_SELECTED : CHOICE_TEXT_BASE;
  });
  showActionState("selected");
}

function showActionState(state) {
  solveCheckBtn.hidden = state === "correct" || state === "wrong";
  solveCheckBtn.disabled = state !== "selected";
  solveCheckBtn.className = state === "selected" ? CHECK_BTN_ENABLED : CHECK_BTN_DISABLED;
  solveCorrectBarEl.hidden = state !== "correct";
  solveWrongBoxEl.hidden = state !== "wrong";
}

function checkAnswer() {
  if (solveSelectedIndex == null || solveAnswered) return;
  const item = solveQueue[solveIndex];
  const correct = solveSelectedIndex === item.answer_index;

  const buttons = [...solveChoicesEl.querySelectorAll("button")];
  const pickedBtn = buttons[solveSelectedIndex - 1];

  if (!correct) {
    // 오답: 고른 보기만 잠그고 표시한 뒤, "다시 풀어보기"를 누르거나 다른 보기를
    // 바로 골라도 이어서 풀 수 있게 나머지 보기는 그대로 눌러볼 수 있게 둔다.
    solveMissedThisQuestion = true;
    solveWrongIndexes.add(solveSelectedIndex);
    solveSelectedIndex = null;
    pickedBtn.disabled = true;
    pickedBtn.className = CHOICE_WRONG;
    pickedBtn.querySelector(".choice-num").className = CHOICE_NUM_WRONG;
    const badge = pickedBtn.querySelector(".choice-badge");
    badge.hidden = false;
    badge.innerHTML = WRONG_BADGE_HTML;
    showActionState("wrong");
    return;
  }

  // 정답: 이번에야 전체를 잠근다. 첫 시도에 맞혔을 때만 점수로 인정
  // (다시 풀어서 맞힌 건 학습으로만 카운트).
  solveAnswered = true;
  buttons.forEach((b) => (b.disabled = true));
  pickedBtn.className = CHOICE_PRIMARY;
  pickedBtn.querySelector(".choice-num").className = CHOICE_NUM_PRIMARY;
  pickedBtn.querySelector(".choice-text").className = CHOICE_TEXT_CORRECT;
  const badge = pickedBtn.querySelector(".choice-badge");
  badge.hidden = false;
  badge.innerHTML = CORRECT_BADGE_HTML;
  if (!solveMissedThisQuestion && !solveScoredThisQuestion) {
    solveScore += 1;
    solveScoredThisQuestion = true;
  }

  solveResultDetailEl.textContent = solveMissedThisQuestion
    ? "다시 도전해서 맞혔어요, 잘하셨어요!"
    : "완벽하게 이해하셨네요! 🎉";
  solveResultBannerEl.hidden = false;

  solveAnswerTagEl.textContent = `정답: ${choiceLabel(item.answer_index - 1)}번`;
  if (item.explanation) {
    solveExplanationEl.hidden = false;
    solveExplanationEl.textContent = formatExplanation(item.explanation);
  } else {
    solveExplanationEl.hidden = true;
  }
  solveExplanationCardEl.hidden = false;
  showActionState("correct");
}

solveCheckBtn.addEventListener("click", checkAnswer);

solveRetryBtn.addEventListener("click", () => {
  // 같은 문제를 완전히 처음부터 다시 고를 수 있도록 초기화한다(다음 문제로는 안 넘어감).
  solveSelectedIndex = null;
  solveAnswered = false;
  solveWrongIndexes = new Set();
  renderChoices(solveQueue[solveIndex]);
  showActionState("ready");
});

solveReviewAgainBtn.addEventListener("click", () => {
  // 이미 맞힌 문제를 연습 삼아 한 번 더 풀어본다(점수는 이미 받았으니 다시 세지 않음).
  solveSelectedIndex = null;
  solveAnswered = false;
  solveWrongIndexes = new Set();
  solveMissedThisQuestion = false;
  solveResultBannerEl.hidden = true;
  solveExplanationCardEl.hidden = true;
  renderChoices(solveQueue[solveIndex]);
  showActionState("ready");
});

solveQuizBackBtn.addEventListener("click", renderSolveSetup);

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
const gradeInput = document.getElementById("grade-input");
const semesterInput = document.getElementById("semester-input");
const subjectSelect = document.getElementById("subject-select");
const addSubjectBtn = document.getElementById("btn-add-subject");
const btnCamera = document.getElementById("btn-camera");
const galleryInput = document.getElementById("gallery-input");
const registerStatusEl = document.getElementById("register-status");
const registerQueueEl = document.getElementById("register-queue");

function sanitizeSubject(text) {
  const trimmed = (text || "").trim();
  if (!trimmed) return "무제";
  return trimmed.replace(/[\\/:*?"<>|]/g, "_");
}

const addSubjectModal = document.getElementById("add-subject-modal");
const newSubjectInput = document.getElementById("new-subject-input");
const closeAddSubjectBtn = document.getElementById("btn-close-add-subject");
const cancelAddSubjectBtn = document.getElementById("btn-cancel-add-subject");
const confirmAddSubjectBtn = document.getElementById("btn-confirm-add-subject");

function openAddSubjectModal() {
  newSubjectInput.value = "";
  addSubjectModal.hidden = false;
  newSubjectInput.focus();
}

function closeAddSubjectModal() {
  addSubjectModal.hidden = true;
  if (subjectSelect.value === "custom") subjectSelect.selectedIndex = 0;
}

function confirmAddSubject() {
  const newSubject = newSubjectInput.value.trim();
  if (!newSubject) {
    newSubjectInput.focus();
    return;
  }
  const opt = document.createElement("option");
  opt.value = newSubject;
  opt.textContent = newSubject;
  opt.selected = true;
  subjectSelect.insertBefore(opt, subjectSelect.lastElementChild);
  addSubjectModal.hidden = true;
}

addSubjectBtn.addEventListener("click", openAddSubjectModal);
closeAddSubjectBtn.addEventListener("click", closeAddSubjectModal);
cancelAddSubjectBtn.addEventListener("click", closeAddSubjectModal);
confirmAddSubjectBtn.addEventListener("click", confirmAddSubject);
newSubjectInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    confirmAddSubject();
  }
});
addSubjectModal.addEventListener("click", (e) => {
  if (e.target === addSubjectModal) closeAddSubjectModal();
});
subjectSelect.addEventListener("change", () => {
  if (subjectSelect.value === "custom") openAddSubjectModal();
});

function currentSubjectLabel() {
  const subjectText = subjectSelect.options[subjectSelect.selectedIndex]?.textContent || "";
  const grade = gradeInput.value.trim();
  const semester = semesterInput.value.trim();
  const examType = document.querySelector('input[name="exam_type"]:checked')?.value === "final" ? "기말고사" : "중간고사";
  const gradeSemester = grade && semester ? `${grade}학년${semester}학기` : "";
  return [subjectText, gradeSemester, examType].filter(Boolean).join(" ");
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
  const subject = sanitizeSubject(currentSubjectLabel());
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

galleryInput.addEventListener("change", (e) => {
  handleFiles(e.target.files);
  e.target.value = "";
});

// --------------------------------------------------------------------------- #
// 캡처하기 (PC 전용) - 실제 윈도우 화면 캡처처럼 화면/창을 고르고 영역을 드래그해서 자른다.
// --------------------------------------------------------------------------- #
const captureModal = document.getElementById("capture-modal");
const captureImage = document.getElementById("capture-image");
const captureCropArea = document.getElementById("capture-crop-area");
const captureSelection = document.getElementById("capture-selection");
const captureCancelBtn = document.getElementById("capture-cancel-btn");
const captureConfirmBtn = document.getElementById("capture-confirm-btn");

const supportsScreenCapture = !!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia);
if (!supportsScreenCapture) {
  btnCamera.disabled = true;
  btnCamera.classList.add("opacity-40", "pointer-events-none");
  btnCamera.title = "PC 브라우저에서만 사용할 수 있어요";
}

let cropStart = null;
let cropRect = null;

function resetCropSelection() {
  cropStart = null;
  cropRect = null;
  captureSelection.hidden = true;
  captureConfirmBtn.disabled = true;
}

async function startScreenCapture() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({ video: { cursor: "never" } });
  } catch (err) {
    return; // 사용자가 선택을 취소했거나 권한을 거부함
  }
  const video = document.createElement("video");
  video.srcObject = stream;
  await video.play();
  await new Promise((resolve) => setTimeout(resolve, 150)); // 첫 프레임 안정화 대기
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  stream.getTracks().forEach((t) => t.stop());

  captureImage.onload = () => {
    resetCropSelection();
    captureModal.hidden = false;
  };
  captureImage.src = canvas.toDataURL("image/png");
}

btnCamera.addEventListener("click", startScreenCapture);

captureCropArea.addEventListener("mousedown", (e) => {
  const rect = captureImage.getBoundingClientRect();
  cropStart = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  captureSelection.hidden = false;
  captureSelection.style.left = `${cropStart.x}px`;
  captureSelection.style.top = `${cropStart.y}px`;
  captureSelection.style.width = "0px";
  captureSelection.style.height = "0px";
  captureConfirmBtn.disabled = true;
});

captureCropArea.addEventListener("mousemove", (e) => {
  if (!cropStart) return;
  const rect = captureImage.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  cropRect = {
    left: Math.min(x, cropStart.x),
    top: Math.min(y, cropStart.y),
    width: Math.abs(x - cropStart.x),
    height: Math.abs(y - cropStart.y),
  };
  captureSelection.style.left = `${cropRect.left}px`;
  captureSelection.style.top = `${cropRect.top}px`;
  captureSelection.style.width = `${cropRect.width}px`;
  captureSelection.style.height = `${cropRect.height}px`;
});

window.addEventListener("mouseup", () => {
  if (!cropStart) return;
  cropStart = null;
  if (cropRect && cropRect.width > 10 && cropRect.height > 10) {
    captureConfirmBtn.disabled = false;
  }
});

captureCancelBtn.addEventListener("click", () => {
  captureModal.hidden = true;
  resetCropSelection();
});

captureConfirmBtn.addEventListener("click", () => {
  if (!cropRect) return;
  const scaleX = captureImage.naturalWidth / captureImage.clientWidth;
  const scaleY = captureImage.naturalHeight / captureImage.clientHeight;
  const canvas = document.createElement("canvas");
  canvas.width = cropRect.width * scaleX;
  canvas.height = cropRect.height * scaleY;
  canvas.getContext("2d").drawImage(
    captureImage,
    cropRect.left * scaleX,
    cropRect.top * scaleY,
    cropRect.width * scaleX,
    cropRect.height * scaleY,
    0,
    0,
    canvas.width,
    canvas.height
  );
  canvas.toBlob((blob) => {
    if (!blob) return;
    handleFiles([new File([blob], "screen_capture.png", { type: "image/png" })]);
  }, "image/png");
  captureModal.hidden = true;
  resetCropSelection();
});

// --------------------------------------------------------------------------- #
// 새로고침/북마크로 바로 들어왔을 때도 지금 주소(#register, #solve, #browse)에
// 맞는 화면이 뜨도록, 첫 로드 시 한 번 현재 해시를 그대로 적용한다.
applyView(HASH_TO_VIEW[location.hash.replace(/^#/, "")] || "home-view");
loadQuestions();
