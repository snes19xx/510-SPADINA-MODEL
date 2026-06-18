// A single headline number under the animation, drawn with D3 (my one true love): the headway variability current
// against the proposed line. Lower is more reliable. Keep the bar for whichever scenario is on
// screen at full strength and dim the other.

import * as d3 from "d3";

const current = "#db1a1acb";
const PROPOSED = "#4a6038";
const INK = "#1a1a1a";
const MUTED = "#6f6a60";

export class MetricsChart {
  constructor(svgEl) {
    this.svg = d3.select(svgEl);
    this.node = svgEl;
    this.mode = "current";
  }

  data(summary) {
    const by = Object.fromEntries(summary.map((r) => [r.scenario, r]));
    this.current = by.baseline.headway_cv;
    this.proposed = by.proposed.headway_cv;
    this.reliablePct = Math.round((1 - this.proposed / this.current) * 100);
    return this;
  }

  setMode(mode) {
    this.mode = mode;
    this.draw();
  }

  draw() {
    const w = this.node.clientWidth || 520;
    const labelW = 96,
      valueW = 56;
    const x = d3
      .scaleLinear()
      .domain([0, this.current * 1.12])
      .range([labelW, w - valueW]);

    this.svg.selectAll("*").remove();

    this.svg
      .append("text")
      .attr("x", 0)
      .attr("y", 14)
      .attr("font-family", "Inter, sans-serif")
      .attr("font-size", 11)
      .attr("font-weight", 600)
      .attr("letter-spacing", "0.06em")
      .attr("fill", MUTED)
      .attr("text-transform", "uppercase")
      .text("HEADWAY VARIABILITY (CV), LOWER IS MORE RELIABLE");

    const rows = [
      {
        name: "Current",
        val: this.current,
        color: current,
        active: this.mode === "current",
      },
      {
        name: "Proposed",
        val: this.proposed,
        color: PROPOSED,
        active: this.mode === "proposed",
      },
    ];
    const bandH = 18,
      top = 30,
      gap = 12;

    rows.forEach((r, i) => {
      const y = top + i * (bandH + gap);
      this.svg
        .append("text")
        .attr("x", 0)
        .attr("y", y + bandH / 2)
        .attr("dominant-baseline", "middle")
        .attr("font-family", "Newsreader, Georgia, serif")
        .attr("font-size", 14)
        .attr("fill", r.active ? INK : MUTED)
        .text(r.name);
      this.svg
        .append("rect")
        .attr("x", labelW)
        .attr("y", y)
        .attr("height", bandH)
        .attr("width", Math.max(1, x(r.val) - labelW))
        .attr("fill", r.color)
        .attr("opacity", r.active ? 1 : 0.3);
      this.svg
        .append("text")
        .attr("x", x(r.val) + 8)
        .attr("y", y + bandH / 2)
        .attr("dominant-baseline", "middle")
        .attr("font-family", "Inter, sans-serif")
        .attr("font-size", 12)
        .attr("font-weight", r.active ? 600 : 400)
        .attr("fill", r.active ? INK : MUTED)
        .text(r.val.toFixed(2));
    });
  }
}
