const form = document.getElementById("run-form");
const runButton = document.getElementById("run-button");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const metaPanelEl = document.getElementById("meta-panel");
const metaContentEl = document.getElementById("meta-content");
const cardTemplate = document.getElementById("result-card-template");
const codeFileInput = document.getElementById("code-file-input");
const codeFileNote = document.getElementById("code-file-note");
const runModeSelect = form.elements.namedItem("run_mode");
const modeHintEl = document.getElementById("mode-hint");
const fileReviewPanelEl = document.getElementById("file-review-panel");
const fileReviewGridEl = document.getElementById("file-review-grid");
const fileReviewActionsEl = document.getElementById("file-review-actions");

const modeHints = {
  triage: "Triage only structures the issue and extracts keywords. Code upload is optional.",
  analysis: "Analysis inspects the uploaded code file when provided, otherwise it uses the project root.",
  patch: "Patch generation works best with a code upload so analysis can target the right file first.",
  validation: "Validation runs patch generation first, then evaluates the proposed fix and report.",
  full: "Full flow runs triage -> analysis -> patch -> validation.",
};

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("warning", isError);
}

function renderMeta(result, uploadedFile) {
  metaContentEl.innerHTML = "";
  const items = [
    ["Run Mode", result.run_mode],
    ["Issue ID", result.issue.issue_id],
  ];

  items.forEach(([label, value]) => {
    const box = document.createElement("div");
    box.className = "meta-item";
    box.innerHTML = `<strong>${label}</strong><span>${escapeHtml(String(value))}</span>`;
    metaContentEl.appendChild(box);
  });
  metaPanelEl.classList.remove("hidden");
}

function addCard(title, badge, blocks) {
  const fragment = cardTemplate.content.cloneNode(true);
  fragment.querySelector(".result-title").textContent = title;
  fragment.querySelector(".result-badge").textContent = badge;
  const body = fragment.querySelector(".result-body");
  blocks.forEach((block) => body.appendChild(block));
  resultsEl.appendChild(fragment);
}

function createDataBlock(title, contentNode) {
  const wrapper = document.createElement("section");
  wrapper.className = "data-block";
  const heading = document.createElement("h3");
  heading.textContent = title;
  wrapper.appendChild(heading);
  wrapper.appendChild(contentNode);
  return wrapper;
}

function createKeyValueBlock(entries) {
  const dl = document.createElement("div");
  dl.className = "kv";
  entries.forEach(([key, value]) => {
    const row = document.createElement("div");
    row.innerHTML = `<strong>${escapeHtml(key)}</strong><span>${escapeHtml(String(value ?? "Not provided"))}</span>`;
    dl.appendChild(row);
  });
  return dl;
}

function createList(items, formatter = (item) => item) {
  const list = document.createElement("ul");
  items.forEach((item) => {
    const li = document.createElement("li");
    li.innerHTML = formatter(item);
    list.appendChild(li);
  });
  return list;
}

function createPre(text) {
  const pre = document.createElement("pre");
  pre.textContent = text;
  return pre;
}

function buildLcsMatrix(originalLines, updatedLines) {
  const rows = originalLines.length + 1;
  const cols = updatedLines.length + 1;
  const matrix = Array.from({ length: rows }, () => Array(cols).fill(0));

  for (let i = rows - 2; i >= 0; i -= 1) {
    for (let j = cols - 2; j >= 0; j -= 1) {
      if (originalLines[i] === updatedLines[j]) {
        matrix[i][j] = matrix[i + 1][j + 1] + 1;
      } else {
        matrix[i][j] = Math.max(matrix[i + 1][j], matrix[i][j + 1]);
      }
    }
  }

  return matrix;
}

function collectChangedUpdatedLineIndexes(originalText, updatedText) {
  const originalLines = originalText.split("\n");
  const updatedLines = updatedText.split("\n");
  const matrix = buildLcsMatrix(originalLines, updatedLines);
  const changedIndexes = new Set();

  let i = 0;
  let j = 0;
  while (i < originalLines.length && j < updatedLines.length) {
    if (originalLines[i] === updatedLines[j]) {
      i += 1;
      j += 1;
      continue;
    }

    if (matrix[i + 1][j] >= matrix[i][j + 1]) {
      i += 1;
    } else {
      changedIndexes.add(j);
      j += 1;
    }
  }

  while (j < updatedLines.length) {
    changedIndexes.add(j);
    j += 1;
  }

  return changedIndexes;
}

function createHighlightedCodePreview(text, changedLineIndexes = new Set()) {
  const container = document.createElement("div");
  container.className = "code-preview";
  const lines = text.split("\n");

  lines.forEach((line, index) => {
    const lineEl = document.createElement("span");
    lineEl.className = "code-line";
    if (changedLineIndexes.has(index)) {
      lineEl.classList.add("changed");
    }
    lineEl.textContent = line || " ";
    container.appendChild(lineEl);
  });

  return container;
}

function createButton(label, onClick, className = "secondary-button") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function formatPathLabel(value) {
  if (!value) {
    return "Not provided";
  }
  const normalized = String(value).replaceAll("\\", "/");
  const pieces = normalized.split("/");
  return pieces[pieces.length - 1] || normalized;
}

function updateModeHint() {
  const mode = runModeSelect.value;
  modeHintEl.textContent = modeHints[mode] || modeHints.full;

  if (mode === "triage") {
    codeFileNote.textContent = "Optional for triage-only runs. Upload a code file when you want later stages to inspect a real file.";
  } else {
    codeFileNote.textContent = "Best for analysis, patch, validation, and full flow runs.";
  }
}

function updateCodeFileNote() {
  const file = codeFileInput.files[0];
  if (!file) {
    updateModeHint();
    return;
  }
  codeFileNote.textContent = `Selected code file: ${file.name}`;
}

async function copyTextToClipboard(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    setStatus(successMessage);
  } catch (error) {
    console.error(error);
    setStatus("Copy failed. Your browser blocked clipboard access.", true);
  }
}

function downloadTextFile(filename, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function renderFilePreview(filePreview) {
  fileReviewGridEl.innerHTML = "";
  fileReviewActionsEl.innerHTML = "";

  if (!filePreview || !filePreview.original_content) {
    fileReviewPanelEl.classList.add("hidden");
    return;
  }

  const originalBlock = createDataBlock(
    `Uploaded File: ${filePreview.original_filename}`,
    createPre(filePreview.original_content),
  );
  fileReviewGridEl.appendChild(originalBlock);

  if (filePreview.fixed_content) {
    const changedLines = collectChangedUpdatedLineIndexes(
      filePreview.original_content,
      filePreview.fixed_content,
    );
    const fixedBlock = createDataBlock(
      `Changed File: ${filePreview.fixed_filename}`,
      createHighlightedCodePreview(filePreview.fixed_content, changedLines),
    );
    fileReviewGridEl.appendChild(fixedBlock);

    fileReviewActionsEl.appendChild(
      createButton("Copy Uploaded File", () => {
        copyTextToClipboard(
          filePreview.original_content,
          `Copied ${filePreview.original_filename}`,
        );
      }),
    );
    fileReviewActionsEl.appendChild(
      createButton("Copy Changed File", () => {
        copyTextToClipboard(
          filePreview.fixed_content,
          `Copied ${filePreview.fixed_filename}`,
        );
      }),
    );
    fileReviewActionsEl.appendChild(
      createButton("Download Fixed File", () => {
        downloadTextFile(filePreview.fixed_filename, filePreview.fixed_content);
        setStatus(`Downloaded ${filePreview.fixed_filename}`);
      }),
    );
  } else {
    fileReviewActionsEl.appendChild(
      createButton("Copy Uploaded File", () => {
        copyTextToClipboard(
          filePreview.original_content,
          `Copied ${filePreview.original_filename}`,
        );
      }),
    );
  }

  fileReviewPanelEl.classList.remove("hidden");
}

function renderResults(payload) {
  resultsEl.innerHTML = "";
  renderMeta(payload.result, payload.uploaded_file);
  renderFilePreview(payload.file_preview);

  const { triage, analysis, patch, validation } = payload.result;

  if (triage) {
    addCard("Triage Agent", triage.issue_type.toUpperCase(), [
      createDataBlock(
        "Summary",
        createKeyValueBlock([
          ["Priority", triage.priority],
          ["Normalized Title", triage.normalized_title],
          ["Expected Behavior", triage.expected_behavior || "Not provided"],
          ["Artifact File", formatPathLabel(triage.artifact_path)],
        ]),
      ),
      createDataBlock("Keywords", createList(triage.search_keywords || [])),
      createDataBlock("Triage Notes", createPre(triage.summary || "")),
    ]);
  }

  if (analysis) {
    addCard("Codebase Analysis Agent", `${analysis.findings.length} finding(s)`, [
      createDataBlock(
        "Analysis Summary",
        createKeyValueBlock([
          ["Repository Root", analysis.repo_path],
          ["Search Terms", (analysis.search_terms || []).join(", ")],
          ["Artifact File", formatPathLabel(analysis.artifact_path)],
        ]),
      ),
      createDataBlock(
        "Findings",
        createList(analysis.findings || [], (finding) => {
          const lineInfo =
            finding.line_start && finding.line_end
              ? `Lines ${finding.line_start}-${finding.line_end}`
              : "Line hints not available";
          return `<strong>${escapeHtml(finding.file_path)}</strong><br>${escapeHtml(
            finding.reason,
          )}<br><em>${escapeHtml(lineInfo)}</em><pre>${escapeHtml(finding.snippet)}</pre>`;
        }),
      ),
    ]);
  }

  if (patch) {
    addCard("Patch Generation Agent", patch.risk_level.toUpperCase(), [
      createDataBlock(
        "Patch Summary",
        createKeyValueBlock([
          ["Summary", patch.summary],
          ["Target Files", (patch.target_files || []).join(", ")],
          ["Artifact File", formatPathLabel(patch.artifact_path)],
          ["Patch Draft File", formatPathLabel(patch.patch_draft_path)],
        ]),
      ),
      createDataBlock(
        "Change Plan",
        createList(patch.change_plan || [], (change) => {
          return `<strong>${escapeHtml(change.file_path)}</strong><br>${escapeHtml(
            change.change_summary,
          )}<br><em>${escapeHtml(change.evidence)}</em>`;
        }),
      ),
      createDataBlock("Patch Draft", createPre(patch.patch_draft || "")),
    ]);
  }

  if (validation) {
    addCard("Validation & Report Agent", validation.verdict.status.toUpperCase(), [
      createDataBlock(
        "Verdict",
        createKeyValueBlock([
          ["Confidence", validation.verdict.confidence],
          ["Passed", validation.verdict.checks_passed],
          ["Failed", validation.verdict.checks_failed],
          ["Warned", validation.verdict.checks_warned],
          ["Artifact File", formatPathLabel(validation.artifact_path)],
        ]),
      ),
      createDataBlock("Assessment", createPre(validation.llm_assessment || "")),
      createDataBlock("Recommendation", createPre(validation.recommendation || "")),
      createDataBlock(
        "Checks",
        createList(validation.checks || [], (check) => {
          return `<strong>${escapeHtml(check.name)}</strong> [${escapeHtml(
            check.status,
          )}]<br>${escapeHtml(check.detail)}`;
        }),
      ),
    ]);
  }
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

runModeSelect.addEventListener("change", updateModeHint);

codeFileInput.addEventListener("change", updateCodeFileNote);

updateModeHint();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  runButton.disabled = true;
  resultsEl.innerHTML = "";
  metaPanelEl.classList.add("hidden");
  fileReviewPanelEl.classList.add("hidden");
  setStatus("Running agents...");

  try {
    const formData = new FormData(form);
    const response = await fetch("/api/run", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Request failed");
    }
    renderResults(payload);
    setStatus("Run completed successfully.");
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Something went wrong.", true);
  } finally {
    runButton.disabled = false;
  }
});
