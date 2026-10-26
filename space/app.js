// Plant Disease Detection — runs a ResNet18 ONNX model in the browser with ONNX Runtime Web.
const $ = (id) => document.getElementById(id);
const MEAN = [0.485, 0.456, 0.406];
const STD = [0.229, 0.224, 0.225];
const PLACEHOLDER =
  "<b>Drop an image here or click to browse</b><span class='small'>JPG or PNG, one leaf, plain background works best</span>";

let blob = null;
let sessionPromise = null;
let classes = null;
let info = null;

ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";

// ---------- model loading ----------
function loadModel() {
  if (!sessionPromise) {
    sessionPromise = (async () => {
      const [c, i] = await Promise.all([
        fetch("model/class_names.json").then((r) => {
          if (!r.ok) throw new Error("not-ready");
          return r.json();
        }),
        fetch("disease_info.json").then((r) => r.json()),
      ]);
      classes = c;
      info = i;
      return ort.InferenceSession.create("model/plant_resnet18.onnx", { executionProviders: ["wasm"] });
    })().catch((e) => {
      sessionPromise = null;
      throw e;
    });
  }
  return sessionPromise;
}

// ---------- image helpers ----------
function loadImage(b) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("That file isn't a readable image."));
    img.src = URL.createObjectURL(b);
  });
}

function pixels(img, size) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, 0, 0, size, size);
  return ctx.getImageData(0, 0, size, size).data;
}

// Same transform as training: resize 224x224, scale to [0,1], ImageNet normalize, NCHW
function toTensor(img) {
  const n = 224 * 224;
  const px = pixels(img, 224);
  const x = new Float32Array(3 * n);
  for (let i = 0; i < n; i++) {
    for (let ch = 0; ch < 3; ch++) x[ch * n + i] = (px[i * 4 + ch] / 255 - MEAN[ch]) / STD[ch];
  }
  return new ort.Tensor("float32", x, [1, 3, 224, 224]);
}

// Percent of leaf tissue that is discoloured (not green), via HSV segmentation
function severity(img) {
  const px = pixels(img, 256);
  let leaf = 0, bad = 0;
  for (let i = 0; i < px.length; i += 4) {
    const r = px[i] / 255, g = px[i + 1] / 255, b = px[i + 2] / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    const v = max, s = max === 0 ? 0 : d / max;
    let h = 0;
    if (d > 0) {
      if (max === r) h = 60 * (((g - b) / d) % 6);
      else if (max === g) h = 60 * ((b - r) / d + 2);
      else h = 60 * ((r - g) / d + 4);
      if (h < 0) h += 360;
    }
    if (s > 0.2 && v > 0.18 && h <= 185) {
      leaf++;
      if (!(h >= 65 && h <= 170)) bad++;
    }
  }
  return leaf < 500 ? 0 : Math.round((bad / leaf) * 1000) / 10;
}

function describe(label) {
  return info.classes[label] || { crop: label.split("_")[0], disease: label.replace(/_+/g, " "), ...info.default };
}

// ---------- UI ----------
function setImage(b) {
  blob = b;
  $("ph").innerHTML = `<img src="${URL.createObjectURL(b)}" alt="Selected leaf" />`;
  $("go").disabled = false;
  $("result").hidden = true;
  $("empty").hidden = false;
  $("err").innerHTML = "";
}

$("file").addEventListener("change", (e) => e.target.files[0] && setImage(e.target.files[0]));
const drop = $("drop");
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && setImage(e.dataTransfer.files[0]));
document.querySelectorAll(".ex button").forEach((b) =>
  b.addEventListener("click", async () => setImage(await (await fetch(b.dataset.src)).blob()))
);
$("clear").addEventListener("click", () => {
  blob = null;
  $("file").value = "";
  $("ph").innerHTML = PLACEHOLDER;
  $("go").disabled = true;
  $("result").hidden = true;
  $("empty").hidden = false;
  $("err").innerHTML = "";
});

$("go").addEventListener("click", async () => {
  if (!blob) return;
  $("go").disabled = true;
  $("err").innerHTML = "";
  try {
    $("go").textContent = sessionPromise ? "Analyzing…" : "Loading model…";
    const session = await loadModel();
    $("go").textContent = "Analyzing…";
    const img = await loadImage(blob);
    const out = await session.run({ input: toTensor(img) });
    const probs = Array.from(out.probs.data);
    const order = probs.map((p, i) => [p, i]).sort((a, b) => b[0] - a[0]).slice(0, 3);
    const label = classes[order[0][1]];
    const d = describe(label);
    const healthy = label.toLowerCase().includes("healthy");
    show({
      ...d,
      healthy,
      confidence: Math.round(order[0][0] * 1000) / 10,
      severity: healthy ? 0 : severity(img),
      top3: order.map(([p, i]) => ({ ...describe(classes[i]), p: Math.round(p * 1000) / 10 })),
    });
  } catch (e) {
    $("result").hidden = true;
    $("empty").hidden = true;
    const msg = e.message === "not-ready"
      ? "The model is still being trained and uploaded. Please check back soon."
      : e.message || "Prediction failed";
    $("err").innerHTML = `<div class="notice error">${msg}</div>`;
  } finally {
    $("go").disabled = false;
    $("go").textContent = "Analyze leaf";
  }
});

function show(d) {
  $("empty").hidden = true;
  $("result").hidden = false;
  const s = $("status");
  s.textContent = d.healthy ? "Healthy leaf" : "Disease detected";
  s.className = "badge " + (d.healthy ? "ok" : "bad");
  $("disease").textContent = d.disease;
  $("crop").textContent = "Crop: " + d.crop;
  $("conf").textContent = d.confidence + "%";
  $("confbar").style.width = d.confidence + "%";
  $("sev").textContent = d.healthy ? "None" : d.severity + "% of leaf";
  $("sevbar").style.width = (d.healthy ? 0 : Math.min(100, d.severity)) + "%";
  $("yield").textContent = d.yield_rate;
  $("sol").textContent = d.solution;
  $("top3").innerHTML =
    '<div class="small" style="color:var(--text-h);font-weight:500">Top predictions</div>' +
    d.top3
      .map((t) => `<div class="row"><div>${t.crop} — ${t.disease}<div class="bar"><i style="width:${t.p}%"></i></div></div><span>${t.p}%</span></div>`)
      .join("");
}

// show model accuracy and warm up the model in the background
fetch("model/metrics.json")
  .then((r) => (r.ok ? r.json() : null))
  .then((m) => {
    if (m && m.val_accuracy) {
      $("acc").textContent = `Validation accuracy: ${(m.val_accuracy * 100).toFixed(1)}% on ${m.val_images.toLocaleString()} images.`;
      setTimeout(() => loadModel().catch(() => {}), 800);
    }
  })
  .catch(() => {});
