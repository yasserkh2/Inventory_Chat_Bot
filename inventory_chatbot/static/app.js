const form = document.getElementById("chat-form");
const sessionIdInput = document.getElementById("session-id");
const messageInput = document.getElementById("message");
const answerEl = document.getElementById("answer");
const resultPreviewEl = document.getElementById("result-preview");
const sqlEl = document.getElementById("sql-query");
const metadataEl = document.getElementById("metadata");
const submitButton = document.getElementById("submit-button");
const chatHistoryEl = document.getElementById("chat-history");
const refreshHistoryButton = document.getElementById("clear-history-button");
const storageKey = "inventory-chat-session-id";

const metadataKeys = [
  ["Status", "status"],
  ["Provider", "provider"],
  ["Model", "model"],
  ["Latency", "latency_ms"],
  ["Tokens", "token_usage"],
];

function renderMetadata(payload) {
  metadataEl.innerHTML = "";
  metadataKeys.forEach(([label, key]) => {
    const wrapper = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;

    if (key === "token_usage") {
      const usage = payload.token_usage || {};
      dd.textContent = `${usage.total_tokens || 0} total (${usage.prompt_tokens || 0} prompt / ${usage.completion_tokens || 0} completion)`;
    } else if (key === "latency_ms") {
      dd.textContent = `${payload.latency_ms ?? 0} ms`;
    } else {
      dd.textContent = payload[key] ?? "n/a";
    }

    wrapper.appendChild(dt);
    wrapper.appendChild(dd);
    metadataEl.appendChild(wrapper);
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderResultPreview(payload) {
  const preview = payload?.result_preview || {};
  const rows = Array.isArray(preview.rows) ? preview.rows : [];

  if (rows.length > 0) {
    const columns = Array.from(
      rows.reduce((set, row) => {
        Object.keys(row || {}).forEach((key) => set.add(key));
        return set;
      }, new Set()),
    );

    const header = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
    const body = rows
      .map((row) => {
        const cells = columns
          .map((column) => `<td>${escapeHtml(row?.[column] ?? "")}</td>`)
          .join("");
        return `<tr>${cells}</tr>`;
      })
      .join("");

    resultPreviewEl.innerHTML = `
      <div class="result-preview-meta">${escapeHtml(preview.row_count ?? rows.length)} row(s)</div>
      <div class="result-table-wrap">
        <table class="result-table">
          <thead><tr>${header}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    `;
    return;
  }

  const scalarEntries = Object.entries(preview).filter(([key]) => key !== "rows");
  if (scalarEntries.length > 0) {
    resultPreviewEl.innerHTML = `
      <dl class="result-kv">
        ${scalarEntries
          .map(
            ([key, value]) =>
              `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(
                typeof value === "object" ? JSON.stringify(value) : value,
              )}</dd></div>`,
          )
          .join("")}
      </dl>
    `;
    return;
  }

  resultPreviewEl.innerHTML = '<p class="empty-history">No structured result returned.</p>';
}

function formatTurnDetails(turn) {
  const bits = [];
  if (turn.specialist_name) {
    bits.push(`Agent: ${turn.specialist_name}`);
  }
  if (turn.intent_id) {
    bits.push(`Intent: ${turn.intent_id}`);
  }
  if (turn.created_at) {
    bits.push(`At: ${new Date(turn.created_at).toLocaleString()}`);
  }
  return bits.join(" • ");
}

function renderHistory(turns) {
  if (!Array.isArray(turns) || turns.length === 0) {
    chatHistoryEl.innerHTML = '<p class="empty-history">No messages yet. Start the conversation.</p>';
    return;
  }

  chatHistoryEl.innerHTML = turns
    .map((turn) => {
      const details = formatTurnDetails(turn);
      const assistantMessage = turn.assistant_message || details || `Status: ${turn.status}`;
      const sqlBlock = turn.sql_query
        ? `<pre class="history-sql">${escapeHtml(turn.sql_query)}</pre>`
        : "";
      const clarification =
        turn.status === "error" && turn.clarification_message
          ? `<p class="history-clarification">${escapeHtml(turn.clarification_message)}</p>`
          : "";

      return `
        <article class="history-turn history-turn-${escapeHtml(turn.status)}">
          <p class="history-role">You</p>
          <p class="history-message">${escapeHtml(turn.user_message || "")}</p>
          <p class="history-role">Assistant</p>
          ${clarification || `<p class="history-message">${escapeHtml(assistantMessage)}</p>`}
          ${sqlBlock}
        </article>
      `;
    })
    .join("");

  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
}

async function loadHistory() {
  const sessionId = sessionIdInput.value.trim();
  if (!sessionId) {
    renderHistory([]);
    return;
  }

  try {
    const response = await fetch(`/api/history?session_id=${encodeURIComponent(sessionId)}`);
    const payload = await response.json();
    renderHistory(payload.turns || []);
  } catch (error) {
    chatHistoryEl.innerHTML = `<p class="empty-history">Failed to load history: ${escapeHtml(error.message)}</p>`;
  }
}

sessionIdInput.value = localStorage.getItem(storageKey) || sessionIdInput.value;
loadHistory();

sessionIdInput.addEventListener("change", () => {
  localStorage.setItem(storageKey, sessionIdInput.value.trim());
  loadHistory();
});

refreshHistoryButton.addEventListener("click", async () => {
  await loadHistory();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const sessionId = sessionIdInput.value.trim();
  const body = {
    session_id: sessionId,
    message: messageInput.value.trim(),
    context: {},
  };

  submitButton.disabled = true;
  submitButton.textContent = "Sending...";
  localStorage.setItem(storageKey, sessionId);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    answerEl.textContent = payload.natural_language_answer || "No answer returned.";
    renderResultPreview(payload);
    sqlEl.textContent = payload.sql_query || "No query returned.";
    renderMetadata(payload);
    messageInput.value = "";
    await loadHistory();
  } catch (error) {
    answerEl.textContent = `Request failed: ${error.message}`;
    renderResultPreview({ result_preview: {} });
    sqlEl.textContent = "No query returned.";
    renderMetadata({
      status: "error",
      provider: "n/a",
      model: "n/a",
      latency_ms: 0,
      token_usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
    });
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Send Query";
  }
});
