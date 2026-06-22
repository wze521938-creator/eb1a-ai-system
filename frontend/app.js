const form = document.querySelector("#upload-form");
const input = document.querySelector("#documents");
const dropzone = document.querySelector("#dropzone");
const fileList = document.querySelector("#file-list");
const button = document.querySelector("#submit-button");
const progress = document.querySelector("#progress");
const result = document.querySelector("#result");
const errorPanel = document.querySelector("#error");

function renderFiles() {
  fileList.replaceChildren();
  [...input.files].forEach((file) => {
    const row = document.createElement("div");
    const name = document.createElement("span");
    const size = document.createElement("small");
    name.textContent = file.name;
    size.textContent = `${(file.size / 1024).toFixed(1)} KB`;
    row.append(name, size);
    fileList.append(row);
  });
}

input.addEventListener("change", renderFiles);
["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("active");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, () => dropzone.classList.remove("active"));
});
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  input.files = event.dataTransfer.files;
  renderFiles();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!input.files.length) return;
  result.classList.add("hidden");
  errorPanel.classList.add("hidden");
  progress.classList.remove("hidden");
  button.disabled = true;

  try {
    const body = new FormData();
    [...input.files].forEach((file) => body.append("documents", file));
    const response = await fetch("/api/generate", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Generation failed. Please try again.");

    document.querySelector("#result-copy").textContent =
      `${payload.evidence_count} evidence item(s) classified. ${payload.warnings.length} review warning(s).`;
    document.querySelector("#download-link").href = payload.download_url;
    result.classList.remove("hidden");
  } catch (error) {
    errorPanel.textContent = error.message;
    errorPanel.classList.remove("hidden");
  } finally {
    progress.classList.add("hidden");
    button.disabled = false;
  }
});
