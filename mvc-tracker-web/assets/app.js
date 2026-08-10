const state = {
  papers: [],
  groups: [],
  status: null,
  filters: {
    search: "",
    team: "all",
    topic: "all",
    year: "all",
    status: "all",
    sort: "date",
  },
};

const nodes = {
  totalPapers: document.querySelector("#totalPapers"),
  recentPapers: document.querySelector("#recentPapers"),
  totalGroups: document.querySelector("#totalGroups"),
  highScorePapers: document.querySelector("#highScorePapers"),
  syncCard: document.querySelector("#syncCard"),
  teamSelect: document.querySelector("#teamSelect"),
  topicSelect: document.querySelector("#topicSelect"),
  yearSelect: document.querySelector("#yearSelect"),
  statusSelect: document.querySelector("#statusSelect"),
  searchInput: document.querySelector("#searchInput"),
  resultCount: document.querySelector("#resultCount"),
  paperList: document.querySelector("#paperList"),
  groupList: document.querySelector("#groupList"),
  exportButton: document.querySelector("#exportButton"),
};

const statusStoreKey = "mvc-tracker-status";

async function loadJson(path, fallback) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) return fallback;
    return await response.json();
  } catch {
    return fallback;
  }
}

function loadLocalStatuses() {
  try {
    return JSON.parse(localStorage.getItem(statusStoreKey) || "{}");
  } catch {
    return {};
  }
}

function saveLocalStatus(id, status) {
  const stored = loadLocalStatuses();
  stored[id] = status;
  localStorage.setItem(statusStoreKey, JSON.stringify(stored));
}

function applyLocalStatuses(papers) {
  const stored = loadLocalStatuses();
  return papers.map((paper) => ({ ...paper, status: stored[paper.id] || paper.status || "new" }));
}

function groupName(id) {
  return state.groups.find((group) => group.id === id)?.name || id || "unknown";
}

function daysSince(dateText) {
  if (!dateText) return Infinity;
  const date = new Date(`${dateText}T00:00:00`);
  return (Date.now() - date.getTime()) / 86400000;
}

function setupFilters() {
  const topics = [...new Set(state.papers.flatMap((paper) => paper.topic || []))].sort();
  const years = [...new Set(state.papers.map((paper) => paper.year).filter(Boolean))].sort((a, b) => b - a);

  for (const group of state.groups) {
    const option = document.createElement("option");
    option.value = group.id;
    option.textContent = group.name;
    nodes.teamSelect.appendChild(option);
  }

  for (const topic of topics) {
    const option = document.createElement("option");
    option.value = topic;
    option.textContent = topic;
    nodes.topicSelect.appendChild(option);
  }

  for (const year of years) {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    nodes.yearSelect.appendChild(option);
  }
}

function filteredPapers() {
  const query = state.filters.search.trim().toLowerCase();
  return state.papers
    .filter((paper) => {
      const text = [
        paper.title,
        paper.venue,
        groupName(paper.team),
        ...(paper.authors || []),
        ...(paper.topic || []),
      ]
        .join(" ")
        .toLowerCase();
      if (query && !text.includes(query)) return false;
      if (state.filters.team !== "all" && paper.team !== state.filters.team) return false;
      if (state.filters.topic !== "all" && !(paper.topic || []).includes(state.filters.topic)) return false;
      if (state.filters.year !== "all" && String(paper.year) !== state.filters.year) return false;
      if (state.filters.status !== "all" && paper.status !== state.filters.status) return false;
      return true;
    })
    .sort((a, b) => {
      if (state.filters.sort === "score") {
        return (b.relevance_score || 0) - (a.relevance_score || 0);
      }
      return (b.year || 0) - (a.year || 0) || String(b.first_seen || "").localeCompare(String(a.first_seen || ""));
    });
}

function renderSummary() {
  nodes.totalPapers.textContent = String(state.papers.length);
  nodes.recentPapers.textContent = String(state.papers.filter((paper) => daysSince(paper.first_seen) <= 30).length);
  nodes.totalGroups.textContent = String(state.groups.length);
  nodes.highScorePapers.textContent = String(state.papers.filter((paper) => (paper.relevance_score || 0) >= 75).length);

  const date = state.status?.date || "未同步";
  const added = state.status?.added ?? 0;
  nodes.syncCard.innerHTML = `<span>同步状态</span><strong>${date}</strong><span>新增 ${added} 篇</span>`;
}

function renderPapers() {
  const papers = filteredPapers();
  nodes.resultCount.textContent = `${papers.length} 篇匹配`;
  nodes.paperList.innerHTML = "";

  if (!papers.length) {
    nodes.paperList.innerHTML = `<div class="empty">没有匹配结果。调整筛选条件或等待下一次同步。</div>`;
    return;
  }

  for (const paper of papers) {
    const card = document.createElement("article");
    card.className = "paper-card";
    const href = paper.pdf_url || paper.code_url || "#";
    const topics = (paper.topic || []).map((topic) => `<span class="tag">${escapeHtml(topic)}</span>`).join("");
    const score = Number(paper.relevance_score || 0);
    const codeLink = paper.code_url ? `<a href="${escapeAttr(paper.code_url)}" target="_blank" rel="noreferrer">Code</a>` : "";
    const pdfLink = paper.pdf_url ? `<a href="${escapeAttr(paper.pdf_url)}" target="_blank" rel="noreferrer">PDF / Page</a>` : "";

    card.innerHTML = `
      <a class="paper-title" href="${escapeAttr(href)}" target="_blank" rel="noreferrer">${escapeHtml(paper.title)}</a>
      <div class="paper-meta">
        <span>${escapeHtml(String(paper.year || "n.d."))}</span>
        <span>${escapeHtml(paper.venue || "unknown venue")}</span>
        <span>${escapeHtml(groupName(paper.team))}</span>
        <span>${escapeHtml((paper.authors || []).slice(0, 6).join(", "))}</span>
      </div>
      <div class="tag-row">
        ${topics}
        <span class="tag warn">score ${score}</span>
      </div>
      <div class="paper-actions">
        <select class="status-select" aria-label="paper status">
          ${["new", "reading", "important", "done", "skip"].map((status) => `<option value="${status}" ${paper.status === status ? "selected" : ""}>${status}</option>`).join("")}
        </select>
        ${pdfLink}
        ${codeLink}
      </div>
    `;
    card.querySelector(".status-select").addEventListener("change", (event) => {
      paper.status = event.target.value;
      saveLocalStatus(paper.id, paper.status);
      renderSummary();
      if (state.filters.status !== "all") renderPapers();
    });
    nodes.paperList.appendChild(card);
  }
}

function renderGroups() {
  nodes.groupList.innerHTML = "";
  for (const group of state.groups) {
    const card = document.createElement("article");
    card.className = "group-card";
    const paperCount = state.papers.filter((paper) => paper.team === group.id).length;
    const topics = (group.topics || []).map((topic) => `<span class="tag">${escapeHtml(topic)}</span>`).join("");
    card.innerHTML = `
      <h3>${escapeHtml(group.name)}</h3>
      <p>${escapeHtml(group.institution || "")}</p>
      <p>${paperCount} 篇已入库</p>
      <div class="tag-row">${topics}</div>
      ${group.homepage ? `<a href="${escapeAttr(group.homepage)}" target="_blank" rel="noreferrer">主页</a>` : ""}
    `;
    nodes.groupList.appendChild(card);
  }
}

function wireEvents() {
  nodes.searchInput.addEventListener("input", (event) => {
    state.filters.search = event.target.value;
    renderPapers();
  });
  for (const [node, key] of [
    [nodes.teamSelect, "team"],
    [nodes.topicSelect, "topic"],
    [nodes.yearSelect, "year"],
    [nodes.statusSelect, "status"],
  ]) {
    node.addEventListener("change", (event) => {
      state.filters[key] = event.target.value;
      renderPapers();
    });
  }
  document.querySelectorAll("[data-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filters.sort = button.dataset.sort;
      document.querySelectorAll("[data-sort]").forEach((item) => item.classList.toggle("active", item === button));
      renderPapers();
    });
  });
  nodes.exportButton.addEventListener("click", exportCurrentList);
}

function exportCurrentList() {
  const rows = filteredPapers().map((paper) => ({
    title: paper.title,
    year: paper.year,
    venue: paper.venue,
    team: groupName(paper.team),
    topic: (paper.topic || []).join("; "),
    status: paper.status,
    score: paper.relevance_score,
    url: paper.pdf_url || paper.code_url || "",
  }));
  const blob = new Blob([JSON.stringify(rows, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `mvc-papers-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

async function init() {
  const [groups, papers, status] = await Promise.all([
    loadJson("./data/groups.json", []),
    loadJson("./data/papers.json", []),
    loadJson("./data/sync_status.json", null),
  ]);
  state.groups = groups;
  state.papers = applyLocalStatuses(papers);
  state.status = status;
  setupFilters();
  wireEvents();
  renderSummary();
  renderPapers();
  renderGroups();
}

init();
