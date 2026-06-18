// Wires the page together: load the model output, build the diorama and the headway panel, and
// run a clock that replays the simulated peak window on a loop. Each time the window comes
// round, it swaps in a different genuine run of the 400.
// There is no scrubber by design; the cars just run, and the Today / Proposed toggle changes.

import { MetricsChart } from "./charts.js";
import { Diorama } from "./scene.js";

const LOOP_SECONDS = 60; // real seconds to replay the whole window once

const els = {
  scene: document.getElementById("scene"),
  labels: document.getElementById("labels"),
  metrics: document.getElementById("metrics"),
  play: document.getElementById("play"),
  modeButtons: [...document.querySelectorAll(".modepick button")],
};

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} returned ${r.status}`);
  return r.json();
}

async function main() {
  let route, sim;
  try {
    [route, sim] = await Promise.all([
      getJSON("assets/route.json"),
      getJSON("assets/sim.json"),
    ]);
  } catch (err) {
    // a failed data load otherwise leaves a silent blank panel; say what happened instead
    console.error("Could not load the model output:", err);
    els.scene.innerHTML =
      '<p style="font:14px/1.5 Inter,sans-serif;color:#6f6a60;padding:24px">' +
      "The animation data could not be loaded. Please refresh the page.</p>";
    return;
  }

  const diorama = new Diorama(els.scene);
  diorama.setRoute(route, els.labels);
  diorama.setData(sim);
  diorama.setMode("today");
  requestAnimationFrame(() => diorama.resize());

  const chart = new MetricsChart(els.metrics).data(sim.summary);
  chart.draw();

  // Lead the page with the result. pull the reliability gain and the ensemble size straight
  // from the model output so the dek can never drift from what the simulation produced.
  const cv = Object.fromEntries(
    sim.summary.map((r) => [r.scenario, r.headway_cv]),
  );
  setText("dek-reliable", Math.round((1 - cv.proposed / cv.baseline) * 100));
  setText("dek-nreps", sim.n_reps ?? 400);

  let mode = "today";
  let runIndex = 0;
  pickRun();

  const windowS = sim.window_s;
  setText("dek-speed", Math.round(windowS / LOOP_SECONDS)); // keep the caption honest to the clock
  let tp = 0;
  let playing = true;
  let last = performance.now();

  function loop(now) {
    const dt = (now - last) / 1000;
    last = now;
    if (playing) {
      tp += dt * (windowS / LOOP_SECONDS);
      if (tp > windowS) {
        tp -= windowS;
        pickRun(); // a fresh genuine run each time the window comes round
      }
    }
    diorama.frame(tp);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame((t) => {
    last = t;
    loop(t);
  });

  els.play.addEventListener("click", () => {
    playing = !playing;
    els.play.textContent = playing ? "Pause" : "Play";
  });

  for (const btn of els.modeButtons) {
    btn.addEventListener("click", () => {
      els.modeButtons.forEach((b) => b.classList.toggle("active", b === btn));
      mode = btn.dataset.mode;
      diorama.setMode(mode);
      chart.setMode(mode);
      pickRun();
    });
  }

  // pick a different run from the current scenario's set and hand it to the diorama
  function pickRun() {
    const runs = sim.scenarios[mode].runs;
    let i = Math.floor(Math.random() * runs.length);
    if (runs.length > 1 && i === runIndex) i = (i + 1) % runs.length;
    runIndex = i;
    diorama.setRun(runIndex);
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  // combine resize bursts to one redraw per frame would be not very efficient to redraw
  let chartResizePending = false;
  window.addEventListener("resize", () => {
    if (chartResizePending) return;
    chartResizePending = true;
    requestAnimationFrame(() => {
      chartResizePending = false;
      chart.draw();
    });
  });
}

main();
