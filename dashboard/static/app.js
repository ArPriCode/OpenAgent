// OS-Agent Dashboard Client-Side Logic

let currentStatus = null;

// Initial Load
document.addEventListener("DOMContentLoaded", () => {
  fetchStatus();
  fetchRepos();
  setInterval(fetchStatus, 2500);

  // Time window form submission
  const timeForm = document.getElementById("time-window-form");
  timeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const start = document.getElementById("input-start-time").value;
    const end = document.getElementById("input-end-time").value;

    try {
      const res = await fetch("/api/time-window", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start_time: start, end_time: end })
      });
      if (res.ok) {
        const badge = document.getElementById("schedule-saved-badge");
        badge.classList.remove("hidden");
        setTimeout(() => badge.classList.add("hidden"), 3000);
        fetchStatus();
      }
    } catch (err) {
      alert("Failed to update schedule: " + err);
    }
  });

  // Add repo form toggle
  const btnShowAdd = document.getElementById("btn-show-add-repo");
  const addPanel = document.getElementById("add-repo-panel");
  const btnCancelAdd = document.getElementById("btn-cancel-add-repo");

  btnShowAdd.addEventListener("click", () => addPanel.classList.remove("hidden"));
  btnCancelAdd.addEventListener("click", () => addPanel.classList.add("hidden"));

  // Add repo form submit
  const addRepoForm = document.getElementById("add-repo-form");
  addRepoForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("new-repo-name").value.trim();
    const labelsStr = document.getElementById("new-repo-labels").value.trim();
    const labels = labelsStr ? labelsStr.split(",").map(s => s.trim()) : ["good first issue", "help wanted"];

    try {
      const res = await fetch("/api/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: name, labels })
      });
      if (res.ok) {
        addPanel.classList.add("hidden");
        addRepoForm.reset();
        fetchRepos();
        fetchStatus();
      } else {
        const err = await res.json();
        alert(err.detail || "Failed to add repo");
      }
    } catch (err) {
      alert("Error: " + err);
    }
  });

  // Manual cycle trigger
  const btnRun = document.getElementById("btn-run-cycle");
  btnRun.addEventListener("click", async () => {
    btnRun.disabled = true;
    btnRun.innerHTML = `<span class="icon">⏳</span><span>Executing Cycle...</span>`;
    try {
      const res = await fetch("/api/run-cycle?force=true", { method: "POST" });
      const data = await res.json();
      fetchStatus();
    } catch (err) {
      alert("Run error: " + err);
    } finally {
      btnRun.disabled = false;
      btnRun.innerHTML = `<span class="icon">▶</span><span>Run Cycle Now</span>`;
    }
  });

  // Dry Run toggle
  const btnDryRun = document.getElementById("btn-toggle-dryrun");
  btnDryRun.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/toggle-dry-run", { method: "POST" });
      const data = await res.json();
      updateDryRunUI(data.dry_run);
    } catch (err) {
      console.error(err);
    }
  });
});

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    currentStatus = data;

    // Clock
    document.getElementById("live-clock").innerText = data.current_time.split(" ")[1] || "--:--:--";

    // Pill
    const pill = document.getElementById("window-status-pill");
    const pillText = document.getElementById("window-status-text");
    if (data.is_active) {
      pill.className = "status-pill active";
      pillText.innerText = "🟢 ACTIVE WINDOW";
    } else {
      pill.className = "status-pill dormant";
      pillText.innerText = "⏸️ DORMANT (WAITING)";
    }

    // Metrics
    document.getElementById("val-time-window").innerText = `${data.window_start} - ${data.window_end}`;
    const nextSec = data.seconds_to_next_window;
    if (data.is_active) {
      document.getElementById("val-next-window").innerText = "Agent is active and listening!";
    } else {
      const hours = Math.floor(nextSec / 3600);
      const mins = Math.floor((nextSec % 3600) / 60);
      document.getElementById("val-next-window").innerText = `Next window in ~${hours}h ${mins}m`;
    }

    document.getElementById("val-repos-count").innerText = data.tracked_repos_count;
    document.getElementById("val-pending-count").innerText = data.pending_approvals.length;
    document.getElementById("val-completed-count").innerText = data.completed_contributions.length;
    document.getElementById("pending-badge").innerText = `${data.pending_approvals.length} Pending`;

    // Dry Run Button
    updateDryRunUI(data.dry_run);

    // Inputs initial populate if empty
    const startInp = document.getElementById("input-start-time");
    const endInp = document.getElementById("input-end-time");
    if (document.activeElement !== startInp) startInp.value = data.window_start;
    if (document.activeElement !== endInp) endInp.value = data.window_end;

    // Pending Approvals Render
    renderPendingApprovals(data.pending_approvals);

    // Completed PRs Render
    renderCompletedContributions(data.completed_contributions);

    // Activity Log Render
    renderActivityLog(data.activity_log);
  } catch (err) {
    console.error("fetchStatus error:", err);
  }
}

function updateDryRunUI(isDry) {
  const btn = document.getElementById("btn-toggle-dryrun");
  const text = document.getElementById("dryrun-text");
  if (isDry) {
    btn.className = "btn btn-secondary";
    text.innerText = "🧪 Dry-Run: ON";
  } else {
    btn.className = "btn btn-danger";
    text.innerText = "⚠️ Live GitHub: ON";
  }
}

async function fetchRepos() {
  try {
    const res = await fetch("/api/repos");
    if (!res.ok) return;
    const repos = await res.json();
    renderReposList(repos);
  } catch (err) {
    console.error("fetchRepos error:", err);
  }
}

function renderReposList(repos) {
  const container = document.getElementById("repo-list-container");
  if (!repos || repos.length === 0) {
    container.innerHTML = `<div class="empty-state">No repositories registered yet. Add one above!</div>`;
    return;
  }

  container.innerHTML = repos.map(r => `
    <div class="repo-item ${r.enabled ? '' : 'disabled'}">
      <div class="repo-meta">
        <h3>${r.repo}</h3>
        <div class="repo-tags">
          ${r.labels.map(lbl => `<span class="repo-tag">${lbl}</span>`).join("")}
        </div>
      </div>
      <div class="repo-controls">
        <button class="btn btn-sm ${r.enabled ? 'btn-secondary' : 'btn-primary'}" onclick="toggleRepo('${r.repo}')">
          ${r.enabled ? 'Disable' : 'Enable'}
        </button>
        <button class="btn-icon" onclick="deleteRepo('${r.repo}')" title="Delete">🗑️</button>
      </div>
    </div>
  `).join("");
}

async function toggleRepo(fullName) {
  try {
    await fetch(`/api/repos/${fullName}/toggle`, { method: "PATCH" });
    fetchRepos();
    fetchStatus();
  } catch (err) {
    alert("Toggle failed: " + err);
  }
}

async function deleteRepo(fullName) {
  if (!confirm(`Remove repository ${fullName}?`)) return;
  try {
    await fetch(`/api/repos/${fullName}`, { method: "DELETE" });
    fetchRepos();
    fetchStatus();
  } catch (err) {
    alert("Delete failed: " + err);
  }
}

async function quickAddRepo(repo, labels) {
  try {
    const res = await fetch("/api/repos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo, labels })
    });
    if (res.ok) {
      fetchRepos();
      fetchStatus();
    } else {
      const err = await res.json();
      alert(err.detail || "Repository already added!");
    }
  } catch (err) {
    alert("Error: " + err);
  }
}

function renderPendingApprovals(pending) {
  const container = document.getElementById("pending-approvals-container");
  if (!pending || pending.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">✨</span>
        <p>No actions waiting for review. The agent is idle & ready!</p>
      </div>`;
    return;
  }

  container.innerHTML = pending.map(item => `
    <div class="pending-card">
      <div class="pending-header">
        <div>
          <div class="pending-title">#${item.issue_number}: ${item.issue_title}</div>
          <div class="pending-repo">Repository: ${item.repo} | Branch: ${item.branch_name}</div>
        </div>
        <span class="badge warning">Needs Approval</span>
      </div>

      <div style="font-size: 0.82rem; color: #a5b4fc; margin-bottom: 6px;">
        <strong>Gemini Solution Summary:</strong> ${item.solution_summary || 'Applied fix'}
      </div>

      <div class="diff-preview"><strong>Grok PR Description:</strong>\n${item.pr_description}</div>

      <div class="pending-footer">
        <button class="btn btn-sm btn-danger" onclick="rejectAction('${item.id}')">✕ Reject / Discard</button>
        <button class="btn btn-sm btn-success" onclick="approveAction('${item.id}')">✓ Approve & Push PR</button>
      </div>
    </div>
  `).join("");
}

async function approveAction(actionId) {
  try {
    const res = await fetch(`/api/approve/${actionId}`, { method: "POST" });
    if (res.ok) {
      fetchStatus();
    } else {
      alert("Approval error");
    }
  } catch (err) {
    alert("Failed to approve: " + err);
  }
}

async function rejectAction(actionId) {
  try {
    await fetch(`/api/reject/${actionId}`, { method: "POST" });
    fetchStatus();
  } catch (err) {
    alert("Failed to reject: " + err);
  }
}

function renderCompletedContributions(completed) {
  const container = document.getElementById("completed-container");
  if (!completed || completed.length === 0) {
    container.innerHTML = `<div class="empty-state"><p>No PRs created yet. Run a contribution cycle during your active window!</p></div>`;
    return;
  }

  container.innerHTML = completed.map(c => {
    const isMock = c.pr_url && c.pr_url.includes("mock-pr-preview");
    const targetUrl = isMock ? `https://github.com/${c.repo}/issues/${c.issue_number}` : c.pr_url;
    const linkLabel = isMock ? "View Issue (Simulation) ↗" : "View Pull Request ↗";
    const forkLink = c.fork_url ? `<a href="${c.fork_url}" target="_blank" style="color: #67e8f9; margin-left: 8px; font-size: 0.75rem; text-decoration: underline;">Fork ↗</a>` : "";

    return `
      <div class="completed-item">
        <div>
          <div class="completed-title">${c.repo} #${c.issue_number}: ${c.issue_title}</div>
          <div style="font-size: 0.74rem; color: #94a3b8; margin-top: 2px;">
            Status: <span style="color: #34d399; font-weight: 600;">PR Active</span>
            ${forkLink}
          </div>
        </div>
        <a href="${targetUrl}" target="_blank" class="completed-link">${linkLabel}</a>
      </div>
    `;
  }).join("");
}

function renderActivityLog(logs) {
  const container = document.getElementById("log-stream");
  if (!logs || logs.length === 0) return;

  container.innerHTML = logs.map(l => `
    <div class="log-line ${l.level}">
      <span style="color: #64748b;">[${l.timestamp}]</span> ${escapeHtml(l.message)}
    </div>
  `).join("");
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
