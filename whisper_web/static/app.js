const page = document.body.dataset.page || "workspace";

if (page === "workspace") {
  setupWorkspacePage();
} else if (page === "history") {
  setupHistoryPage();
}

function setupWorkspacePage() {
  const form = document.getElementById("upload-form");
  const fileInput = document.getElementById("audio-file");
  const fileName = document.getElementById("file-name");
  const submitButton = document.getElementById("submit-button");
  const taskSelect = document.getElementById("task");

  const statusCard = document.getElementById("status-card");
  const statusText = document.getElementById("status-text");
  const progressText = document.getElementById("progress-text");
  const progressBar = document.getElementById("progress-bar");
  const stageText = document.getElementById("stage-text");
  const durationText = document.getElementById("duration-text");

  const resultPanel = document.getElementById("result-panel");
  const errorPanel = document.getElementById("error-panel");
  const errorText = document.getElementById("error-text");
  const languageValue = document.getElementById("language-value");
  const confidenceValue = document.getElementById("confidence-value");
  const taskValue = document.getElementById("task-value");
  const audioDurationValue = document.getElementById("audio-duration-value");
  const elapsedValue = document.getElementById("elapsed-value");
  const resultText = document.getElementById("result-text");
  const segmentsList = document.getElementById("segments-list");
  const segmentCount = document.getElementById("segment-count");
  const downloadLink = document.getElementById("download-link");

  let pollTimer = null;

  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    fileName.textContent = file ? file.name : "Choose file";
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileInput.files?.[0];
    if (!file) {
      return;
    }

    resetPanels();
    submitButton.disabled = true;
    statusCard.classList.remove("hidden");
    setProgress(0, "Uploading", "Uploading", 0, null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`/api/jobs?task=${encodeURIComponent(taskSelect.value)}`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Upload failed");
      }

      const payload = await response.json();
      pollJob(payload.job_id);
    } catch (error) {
      showError(error.message || "Unknown error");
      submitButton.disabled = false;
    }
  });

  function pollJob(jobId) {
    clearTimer();

    const tick = async () => {
      try {
        const response = await fetch(`/api/jobs/${jobId}`);
        if (!response.ok) {
          throw new Error("Failed to load job");
        }

        const job = await response.json();
        setProgress(
          job.progress,
          job.status,
          job.stage,
          job.processed_seconds,
          job.duration_seconds
        );

        if (job.status === "completed") {
          showResult(jobId, job);
          submitButton.disabled = false;
          clearTimer();
          return;
        }

        if (job.status === "failed") {
          showError(job.error || "Processing failed");
          submitButton.disabled = false;
          clearTimer();
          return;
        }

        pollTimer = window.setTimeout(tick, 800);
      } catch (error) {
        showError(error.message || "Polling failed");
        submitButton.disabled = false;
        clearTimer();
      }
    };

    tick();
  }

  function setProgress(progress, status, stage, processedSeconds, durationSeconds) {
    const normalized = Math.max(0, Math.min(100, Number(progress || 0)));
    progressBar.style.width = `${normalized}%`;
    progressText.textContent = `${normalized}%`;
    statusText.textContent = toHumanStatus(status);
    stageText.textContent = stage || "Processing";
    durationText.textContent = formatDurationProgress(processedSeconds, durationSeconds);
  }

  function showResult(jobId, job) {
    errorPanel.classList.add("hidden");
    resultPanel.classList.remove("hidden");

    languageValue.textContent = job.detected_language || "-";
    confidenceValue.textContent =
      typeof job.language_probability === "number"
        ? `${(job.language_probability * 100).toFixed(2)}%`
        : "-";
    taskValue.textContent = job.task === "translate" ? "Translate" : "Transcribe";
    audioDurationValue.textContent =
      typeof job.duration_seconds === "number" ? `${job.duration_seconds.toFixed(1)}s` : "-";
    elapsedValue.textContent =
      typeof job.elapsed_seconds === "number" ? formatElapsed(job.elapsed_seconds) : "-";
    resultText.textContent = job.text || "";
    segmentCount.textContent = `${job.segments.length} segments`;
    downloadLink.href = `/api/jobs/${jobId}/download`;

    segmentsList.innerHTML = "";
    for (const segment of job.segments) {
      const item = document.createElement("article");
      item.className = "segment-item";

      const time = document.createElement("time");
      time.textContent = `${segment.start_label} -> ${segment.end_label}`;

      const text = document.createElement("p");
      text.textContent = segment.text || "";

      item.appendChild(time);
      item.appendChild(text);
      segmentsList.appendChild(item);
    }
  }

  function showError(message) {
    resultPanel.classList.add("hidden");
    errorPanel.classList.remove("hidden");
    errorText.textContent = message;
    statusText.textContent = "Failed";
    stageText.textContent = message;
  }

  function resetPanels() {
    resultPanel.classList.add("hidden");
    errorPanel.classList.add("hidden");
    segmentsList.innerHTML = "";
    resultText.textContent = "";
    elapsedValue.textContent = "-";
  }

  function clearTimer() {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
  }
}

async function setupHistoryPage() {
  const historyList = document.getElementById("history-list");
  const detailEmpty = document.getElementById("detail-empty");
  const detailContent = document.getElementById("detail-content");
  const detailTitle = document.getElementById("detail-title");
  const detailMeta = document.getElementById("detail-meta");
  const detailText = document.getElementById("detail-text");
  const detailSegments = document.getElementById("detail-segments");
  const detailDownload = document.getElementById("detail-download");

  try {
    const response = await fetch("/api/history");
    if (!response.ok) {
      throw new Error("Failed to load history");
    }

    const items = await response.json();
    historyList.innerHTML = "";

    if (!items.length) {
      historyList.innerHTML = `<article class="history-empty">No cached jobs yet.</article>`;
      return;
    }

    for (const item of items) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "history-item";
      card.innerHTML = `
        <span class="history-status ${item.status}">${item.status}</span>
        <strong>${escapeHtml(item.filename)}</strong>
        <p>${item.task === "translate" ? "Translate" : "Transcribe"} · ${item.created_at}</p>
      `;
      card.addEventListener("click", () => showHistoryDetail(item));
      historyList.appendChild(card);
    }

    showHistoryDetail(items[0]);
  } catch (error) {
    historyList.innerHTML = `<article class="history-empty">${escapeHtml(error.message || "Failed to load history")}</article>`;
  }

  function showHistoryDetail(item) {
    detailEmpty.classList.add("hidden");
    detailContent.classList.remove("hidden");
    detailTitle.textContent = item.filename;
    detailMeta.textContent = [
      item.task === "translate" ? "Translate" : "Transcribe",
      item.detected_language ? `Language: ${item.detected_language}` : "Language: -",
      typeof item.language_probability === "number"
        ? `Confidence: ${(item.language_probability * 100).toFixed(2)}%`
        : "Confidence: -",
      typeof item.elapsed_seconds === "number" ? `Done in ${formatElapsed(item.elapsed_seconds)}` : null,
      item.finished_at || item.created_at,
    ]
      .filter(Boolean)
      .join(" · ");
    detailText.textContent = item.text || "";
    detailDownload.href = `/api/jobs/${item.id}/download`;
    detailDownload.classList.toggle("hidden", item.status !== "completed");

    detailSegments.innerHTML = "";
    for (const segment of item.segments || []) {
      const row = document.createElement("article");
      row.className = "segment-item";

      const time = document.createElement("time");
      time.textContent = `${segment.start_label} -> ${segment.end_label}`;

      const text = document.createElement("p");
      text.textContent = segment.text || "";

      row.appendChild(time);
      row.appendChild(text);
      detailSegments.appendChild(row);
    }
  }
}

function toHumanStatus(status) {
  if (status === "queued") return "Queued";
  if (status === "processing") return "Processing";
  if (status === "completed") return "Completed";
  if (status === "failed") return "Failed";
  return "Processing";
}

function formatDurationProgress(processedSeconds, durationSeconds) {
  const processed = typeof processedSeconds === "number" ? processedSeconds.toFixed(1) : "0.0";
  const duration =
    typeof durationSeconds === "number" && durationSeconds > 0 ? durationSeconds.toFixed(1) : "?";
  return `${processed}s / ${duration}s`;
}

function formatElapsed(seconds) {
  const total = Math.max(0, Number(seconds || 0));
  if (total < 60) {
    return `${total.toFixed(1)}s`;
  }

  const minutes = Math.floor(total / 60);
  const remain = total - minutes * 60;
  return `${minutes}m ${remain.toFixed(1)}s`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
