(function () {
  "use strict";

  var MAX_FILE_SIZE = 8 * 1024 * 1024;
  var allowedTypes = ["image/jpeg", "image/png"];
  var selectedFile = null;
  var previewUrl = null;
  var isAnalyzing = false;

  function byId(id) {
    return document.getElementById(id);
  }

  var drop = byId("drop");
  var fileInput = byId("file");
  var prompt = byId("ph");
  var preview = byId("preview");
  var previewImage = byId("preview-image");
  var previewName = byId("preview-name");
  var previewSize = byId("preview-size");
  var removeButton = byId("clear");
  var uploadError = byId("upload-error");
  var diagnoseButton = byId("go");
  var diagnoseLabel = byId("go-label");
  var spinner = document.querySelector(".upload-spinner");
  var emptyState = byId("empty");
  var loadingState = byId("loading");
  var resultState = byId("result");
  var errorState = byId("err");
  var errorMessage = byId("error-message");
  var loginLink = byId("login-link");
  var confidenceText = byId("conf");
  var confidenceBar = byId("confbar");
  var severityText = byId("sev");
  var severityBar = byId("sevbar");
  var severityMetric = byId("severity-metric");
  var exampleButtons = document.querySelectorAll(".upload-example-button");

  if (
    !drop ||
    !fileInput ||
    !prompt ||
    !preview ||
    !previewImage ||
    !diagnoseButton
  ) {
    return;
  }

  function setUploadError(message) {
    if (!uploadError) {
      return;
    }
    uploadError.textContent = message;
    uploadError.hidden = !message;
  }

  function rejectSelectedFile(message) {
    clearPreviewUrl();
    selectedFile = null;
    fileInput.value = "";
    previewImage.removeAttribute("src");
    preview.hidden = true;
    prompt.hidden = false;
    diagnoseButton.disabled = true;
    hideDiagnosisStates();
    if (emptyState) emptyState.hidden = false;
    setUploadError(message);
  }

  function formatFileSize(size) {
    return size >= 1024 * 1024
      ? (size / (1024 * 1024)).toFixed(1) + " MB"
      : Math.max(1, Math.round(size / 1024)) + " KB";
  }

  function clearPreviewUrl() {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
  }

  function hideDiagnosisStates() {
    if (emptyState) emptyState.hidden = true;
    if (loadingState) loadingState.hidden = true;
    if (resultState) resultState.hidden = true;
    if (errorState) errorState.hidden = true;
  }

  function setSelectedFile(file) {
    if (isAnalyzing || !file) {
      return;
    }

    if (!allowedTypes.includes(file.type)) {
      rejectSelectedFile("Please choose a JPG or PNG image.");
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      rejectSelectedFile(
        "This image is larger than 8 MB. Choose a smaller photo.",
      );
      return;
    }

    clearPreviewUrl();
    selectedFile = file;
    fileInput.value = "";
    previewUrl = URL.createObjectURL(file);
    previewImage.src = previewUrl;
    if (previewName) previewName.textContent = file.name;
    if (previewSize) previewSize.textContent = formatFileSize(file.size);
    prompt.hidden = true;
    preview.hidden = false;
    diagnoseButton.disabled = false;
    setUploadError("");
    hideDiagnosisStates();
    if (emptyState) emptyState.hidden = false;
  }

  function resetPage() {
    if (isAnalyzing) {
      return;
    }
    clearPreviewUrl();
    selectedFile = null;
    fileInput.value = "";
    previewImage.removeAttribute("src");
    preview.hidden = true;
    prompt.hidden = false;
    diagnoseButton.disabled = true;
    setUploadError("");
    hideDiagnosisStates();
    if (emptyState) emptyState.hidden = false;
  }

  function setAnalyzing(analyzing) {
    isAnalyzing = analyzing;
    diagnoseButton.disabled = analyzing || !selectedFile;
    diagnoseButton.setAttribute("aria-busy", String(analyzing));
    if (diagnoseLabel) {
      diagnoseLabel.textContent = analyzing
        ? "Analysing leaf..."
        : "Diagnose Leaf";
    }
    if (spinner) spinner.hidden = !analyzing;
    if (removeButton) removeButton.disabled = analyzing;
    fileInput.disabled = analyzing;
    exampleButtons.forEach(function (button) {
      button.disabled = analyzing;
    });
    drop.setAttribute("aria-disabled", String(analyzing));
  }

  function setMeter(bar, text, value, classPrefix) {
    var safeValue = Number.isFinite(Number(value))
      ? Math.max(0, Math.min(100, Number(value)))
      : 0;
    var tone = safeValue >= 80 ? "high" : safeValue >= 60 ? "medium" : "low";
    if (bar) {
      bar.style.width = safeValue + "%";
      bar.className = classPrefix + " is-" + tone;
      var meter = bar.closest('[role="meter"]');
      if (meter) meter.setAttribute("aria-valuenow", String(safeValue));
    }
    if (text) text.textContent = safeValue + "%";
    return { value: safeValue, tone: tone };
  }

  function renderPossibilities(items) {
    var container = byId("top3");
    if (!container) return;
    container.replaceChildren();

    (Array.isArray(items) ? items : []).slice(0, 3).forEach(function (item) {
      var row = document.createElement("div");
      row.className = "diagnosis-possibility-row";

      var text = document.createElement("span");
      text.className = "diagnosis-possibility-name";
      text.textContent =
        String(item.crop || "") + " — " + String(item.disease || "");

      var track = document.createElement("span");
      track.className = "diagnosis-possibility-track";
      track.setAttribute("aria-hidden", "true");

      var bar = document.createElement("span");
      bar.className = "diagnosis-possibility-bar";
      var probability = Number.isFinite(Number(item.p))
        ? Math.max(0, Math.min(100, Number(item.p)))
        : 0;
      bar.style.width = probability + "%";
      track.appendChild(bar);

      var percentage = document.createElement("strong");
      percentage.className = "diagnosis-possibility-percent";
      percentage.textContent = probability + "%";

      row.append(text, track, percentage);
      container.appendChild(row);
    });
  }

  function showDiagnosis(data) {
    hideDiagnosisStates();
    if (!resultState) return;
    resultState.hidden = false;

    var healthy = Boolean(data.healthy);
    var confidence = setMeter(
      confidenceBar,
      confidenceText,
      data.confidence,
      "diagnosis-meter-fill",
    );
    var status = byId("status");
    var crop = byId("crop");
    var disease = byId("disease");
    var yieldValue = byId("yield");
    var solution = byId("sol");
    var lowNotice = byId("low-confidence");

    if (status) {
      status.textContent = healthy ? "Healthy" : "Disease detected";
      status.className =
        "diagnosis-status " +
        (healthy ? "diagnosis-status-healthy" : "diagnosis-status-diseased");
    }
    if (crop) crop.textContent = "Crop: " + String(data.crop || "");
    if (disease) disease.textContent = String(data.disease || "");
    if (yieldValue) yieldValue.textContent = String(data.yield_rate || "");
    if (solution) solution.textContent = String(data.solution || "");
    if (lowNotice) lowNotice.hidden = confidence.value >= 60;

    if (severityMetric) severityMetric.hidden = healthy;
    if (!healthy) {
      var severity = setMeter(
        severityBar,
        severityText,
        data.severity,
        "diagnosis-meter-fill",
      );
      if (severityText) severityText.textContent = severity.value + "% of leaf";
    }

    renderPossibilities(data.top3);
  }

  function showError(message, statusCode) {
    hideDiagnosisStates();
    if (!errorState) return;
    errorState.hidden = false;
    if (errorMessage) {
      errorMessage.textContent =
        statusCode === 401
          ? "Your session expired. Please log in again."
          : String(
              message || "We could not diagnose this image. Please try again.",
            );
    }
    if (loginLink) loginLink.hidden = statusCode !== 401;
  }

  fileInput.addEventListener("change", function () {
    if (fileInput.files && fileInput.files[0]) {
      setSelectedFile(fileInput.files[0]);
    }
  });

  drop.addEventListener("click", function (event) {
    if (event.target.closest("button") || isAnalyzing) return;
    fileInput.click();
  });

  drop.addEventListener("keydown", function (event) {
    if (isAnalyzing || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    fileInput.click();
  });

  ["dragenter", "dragover"].forEach(function (eventName) {
    drop.addEventListener(eventName, function (event) {
      event.preventDefault();
      if (!isAnalyzing) drop.classList.add("is-dragging");
    });
  });

  ["dragleave", "drop"].forEach(function (eventName) {
    drop.addEventListener(eventName, function (event) {
      event.preventDefault();
      drop.classList.remove("is-dragging");
    });
  });

  drop.addEventListener("drop", function (event) {
    if (!isAnalyzing && event.dataTransfer.files[0]) {
      setSelectedFile(event.dataTransfer.files[0]);
    }
  });

  if (removeButton) {
    removeButton.addEventListener("click", resetPage);
  }
  var scanAnotherButton = byId("scan-another");
  if (scanAnotherButton) {
    scanAnotherButton.addEventListener("click", resetPage);
  }

  exampleButtons.forEach(function (button) {
    button.addEventListener("click", async function () {
      if (isAnalyzing) return;
      setUploadError("");
      try {
        var response = await fetch(button.dataset.src);
        if (!response.ok) {
          throw new Error(
            "Could not load this example. Please choose a photo instead.",
          );
        }
        var blob = await response.blob();
        var mimeType = blob.type;
        if (!allowedTypes.includes(mimeType)) {
          mimeType = /\.png$/i.test(button.dataset.name || "")
            ? "image/png"
            : "image/jpeg";
        }
        var file = new File([blob], button.dataset.name || "leaf-example.jpg", {
          type: mimeType,
        });
        setSelectedFile(file);
      } catch (error) {
        setUploadError(error.message);
      }
    });
  });

  diagnoseButton.addEventListener("click", async function () {
    if (!selectedFile || isAnalyzing) return;

    setUploadError("");
    hideDiagnosisStates();
    if (loadingState) loadingState.hidden = false;
    setAnalyzing(true);

    try {
      var formData = new FormData();
      formData.append("file", selectedFile, "leaf.jpg");
      formData.append("crop_type", byId("crop-type").value);
      var response = await fetch("/api/predict", {
        method: "POST",
        body: formData,
      });
      var data = await response.json();
      if (!response.ok) {
        showError(data.error, response.status);
        return;
      }
      showDiagnosis(data);
    } catch (error) {
      showError(error.message, 0);
    } finally {
      setAnalyzing(false);
    }
  });

  window.addEventListener("beforeunload", clearPreviewUrl);
})();
