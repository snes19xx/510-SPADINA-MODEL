"""Render the executed notebook as a clean, self-contained article for the webapp.

Hide the code and the prompts and keep the prose, the figures, the printed results, and the
results table, then wrap the whole thing in an editorial stylesheet so the right-hand
panel reads like a printed page rather than a Jupyter export. The figures are already embedded
as images in the notebook, so the output is a single standalone file I can drop straight into
an iframe.
"""

from __future__ import annotations

import pathlib

import nbformat
from nbconvert import HTMLExporter

ROOT = pathlib.Path(__file__).resolve().parent.parent
NB = ROOT / "notebooks" / "510_spadina.ipynb"
OUT = ROOT / "notebook" / "510_spadina.html"

CSS = """
:root {
  --paper: #faf8f3;
  --ink: #1a1a1a;
  --muted: #6f6a60;
  --rule: #ddd6c9;
  --accent: #b03a2e;
  --proposed: #2c6e63;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--paper); color: var(--ink); }
body {
  font-family: "Newsreader", Georgia, "Times New Roman", serif;
  font-size: 18px;
  line-height: 1.68;
  -webkit-font-smoothing: antialiased;
}
.page { max-width: 1100px; margin: 0 auto; padding: 56px 48px 120px; }

h1 {
  font-family: "Newsreader", Georgia, serif;
  font-weight: 500;
  font-size: 2.35rem;
  line-height: 1.12;
  letter-spacing: -0.01em;
  margin: 0 0 0.2rem;
}
h2 {
  font-weight: 600;
  font-size: 1.05rem;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  margin: 3.2rem 0 0.4rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--rule);
}
h3 {
  font-weight: 600;
  font-size: 1.18rem;
  margin: 2.2rem 0 0.3rem;
  font-style: italic;
}
p { margin: 0 0 1.15rem; }
em { font-style: italic; }
a { color: var(--accent); text-decoration: none; border-bottom: 1px solid rgba(176,58,46,0.3); }

.rendered_html { color: var(--ink); }
.text_cell_render p:first-child { margin-top: 0; }

/* the very first paragraph after the title reads as a standfirst */
h1 + p, h1 + p + p {
  color: var(--muted);
  font-size: 1.12rem;
  line-height: 1.55;
}

/* figures */
img, .output_png img { display: block; margin: 1.6rem auto 0.6rem; max-width: 100%; height: auto; }
.output_subarea { max-width: 100% !important; }

/* printed results read as small monospace asides, set quietly on a faint panel */
pre, .output_text {
  font-family: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 0.78rem;
  line-height: 1.55;
  color: #4a463e;
  background: rgba(40, 34, 20, 0.035);
  border: 0;
  border-radius: 3px;
  padding: 0.8rem 1.1rem;
  margin: 1.2rem 0;
  overflow-x: auto;
  white-space: pre-wrap;
}
.output_text { border: 0 !important; }

/* results table */
table.dataframe {
  border-collapse: collapse;
  margin: 1.8rem auto;
  width: 100%;
  font-family: "Newsreader", Georgia, serif;
  font-size: 0.95rem;
  font-variant-numeric: tabular-nums;
}
table.dataframe th, table.dataframe td {
  padding: 0.5rem 0.7rem;
  text-align: right;
  border-bottom: 1px solid var(--rule);
}
table.dataframe thead th { border-bottom: 1.5px solid var(--ink); font-weight: 600; vertical-align: bottom; }
table.dataframe tbody th { text-align: left; font-weight: 600; }
table.dataframe tbody tr:last-child td, table.dataframe tbody tr:last-child th {
  border-bottom: none; color: var(--proposed);
}

/* hide every trace of the machinery */
.prompt, .input_prompt, .output_prompt, .anchor-link { display: none !important; }
.cell { margin: 0; padding: 0; border: none; }
.code_cell { margin: 0; }
.output_wrapper, .output, .output_area { border: none; box-shadow: none; }
.jp-OutputPrompt, .jp-InputPrompt { display: none !important; }
"""

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>510 Spadina</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=IBM+Plex+Mono:wght@400&display=swap" rel="stylesheet">
<style>%s</style>
</head>
<body><main class="page">%s</main></body>
</html>"""


def render() -> pathlib.Path:
    nb = nbformat.read(NB, as_version=4)
    body, _ = HTMLExporter(template_name="basic", exclude_input=True).from_notebook_node(nb)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(HEAD % (CSS, body), encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print("wrote", render())
