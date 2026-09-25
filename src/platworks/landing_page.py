"""Standalone product landing page for the platworks umbrella.

Renders a single self-contained HTML file (inline CSS, no external
assets, no CDN) directly from ``platworks.catalog`` and
``platworks.tools`` so the page cannot drift from the verified data:

- Public components render with their verified GitHub links and
  descriptions (copied from the catalog at render time).
- Private components render by name only, explicitly marked private —
  no repo link, no invented description.
- The MCP tool list is rendered from the tool registry, so the page
  advertises exactly the tools the server ships.
- No external requests of any kind: the only outbound URLs are the
  verified repo links themselves.
"""

import html as html_module
import os

from platworks import __version__, catalog, tools


class LandingOutputExistsError(FileExistsError):
    """Raised when the landing page file exists and overwrite=False."""

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  margin: 0; background: #10141c; color: #e6e9f0; line-height: 1.55;
}
.wrap { max-width: 980px; margin: 0 auto; padding: 48px 24px 96px; }
header h1 { font-size: 2.6rem; margin: 0 0 10px; letter-spacing: -0.5px; }
header p.tagline { font-size: 1.2rem; color: #9fb0c8; margin: 0 0 6px; }
header p.sub { color: #7484a0; margin: 0; }
section { margin-top: 52px; }
h2 { font-size: 1.35rem; border-bottom: 1px solid #263041; padding-bottom: 8px; }
p.lead { color: #b8c2d4; font-size: 1.0rem; max-width: 72ch; }
.principle {
  background: #171e2a; border: 1px solid #2a3a5c; border-radius: 10px;
  padding: 16px 20px; margin-top: 18px; font-size: 1.05rem;
}
.principle strong { color: #7ab8ff; }
.steps { display: grid; gap: 14px; margin-top: 20px; }
.step {
  display: flex; gap: 16px; align-items: baseline;
  background: #171e2a; border: 1px solid #263041; border-radius: 10px;
  padding: 16px 20px;
}
.step .num {
  font-size: 1.4rem; font-weight: 700; color: #7ab8ff; min-width: 2ch;
}
.step h3 { margin: 0 0 4px; font-size: 1.0rem; }
.step p { margin: 0; font-size: 0.88rem; color: #b8c2d4; }
.tool-list { display: grid; gap: 8px; margin-top: 20px; }
.tool {
  background: #171e2a; border: 1px solid #263041; border-radius: 8px;
  padding: 10px 14px; font-size: 0.88rem;
}
.tool code {
  color: #7ab8ff; font-size: 0.85rem; font-family: ui-monospace,
  "SF Mono", Menlo, Consolas, monospace;
}
.tool span { color: #b8c2d4; }
.install {
  background: #0d1117; border: 1px solid #263041; border-radius: 10px;
  padding: 16px 20px; margin-top: 20px; font-family: ui-monospace,
  "SF Mono", Menlo, Consolas, monospace; font-size: 0.85rem;
  color: #b8c2d4; white-space: pre; overflow-x: auto;
}
.grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px; margin-top: 20px;
}
.card {
  background: #171e2a; border: 1px solid #263041; border-radius: 10px;
  padding: 18px 20px;
}
.card h3 { margin: 0 0 6px; font-size: 1.02rem; }
.card h3 a { color: #7ab8ff; text-decoration: none; }
.card h3 a:hover { text-decoration: underline; }
.card .meta { font-size: 0.78rem; color: #7484a0; margin-bottom: 8px; }
.card p { margin: 0; font-size: 0.88rem; color: #b8c2d4; }
.card.private { background: #141821; border-style: dashed; }
.card.private p { color: #6a7688; font-style: italic; }
.badge {
  display: inline-block; font-size: 0.68rem; padding: 1px 8px;
  border-radius: 999px; border: 1px solid #33405a; color: #9fb0c8;
  margin-right: 6px;
}
.faq { margin-top: 20px; }
.faq details {
  background: #171e2a; border: 1px solid #263041; border-radius: 10px;
  padding: 14px 20px; margin-bottom: 10px;
}
.faq summary { font-size: 0.95rem; color: #e6e9f0; cursor: pointer; }
.faq details p { margin: 10px 0 0; font-size: 0.88rem; color: #b8c2d4; }
footer { margin-top: 64px; color: #6a7688; font-size: 0.8rem; }
footer p { margin: 4px 0; }
"""


def _esc(text):
    return html_module.escape(text, quote=True)


def _component_card(entry):
    name = _esc(entry["name"])
    meta = (
        f'<span class="badge">{_esc(entry["category"])}</span>'
        f'<span class="badge">{_esc(entry["language"])}</span>'
        f'<span class="badge">{_esc(entry["license"])}</span>'
    )
    if entry["public"]:
        repo = _esc(entry["repo"])
        desc = _esc(entry["description"])
        return (
            f'<div class="card">'
            f'<h3><a href="{repo}">{name}</a></h3>'
            f'<div class="meta">{meta}</div>'
            f"<p>{desc}</p></div>"
        )
    return (
        f'<div class="card private">'
        f"<h3>{name}</h3>"
        f'<div class="meta">{meta}</div>'
        f"<p>Private component &mdash; no public repository yet.</p></div>"
    )


def build_html():
    """Render the full product landing page HTML from the verified catalog."""
    entries = catalog.list_components()
    private = [e for e in entries if not e["public"]]
    counts = catalog.counts()
    cards = "".join(_component_card(e) for e in entries)
    tool_rows = "".join(
        f'<div class="tool"><code>{_esc(name)}</code> &mdash; '
        f"<span>{_esc(purpose)}</span></div>"
        for name, purpose in tools.TOOL_SPECS
    )
    private_note = ""
    if private:
        names = ", ".join(_esc(e["name"]) for e in private)
        private_note = (
            f"<p>{len(private)} further component(s) are private and not "
            f"yet published: {names}.</p>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>platworks — the plat ecosystem, one MCP server</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
<header>
<h1>platworks</h1>
<p class="tagline">The plat ecosystem for commercial real estate, wired
into your editor as one MCP server: verified underwriting engines,
agent control planes, market studies, and asset operations.</p>
<p class="sub">{counts['public']} public repositories &middot; {counts['total']}
catalogued components &middot; {tools.TOOL_COUNT} MCP tools &middot; umbrella
package v{_esc(__version__)} &middot; Apache-2.0</p>
</header>

<section>
<h2>The principle</h2>
<div class="principle">
<strong>{_esc(tools.PRINCIPLE)}</strong><br>
Every component in this ecosystem is a deterministic engine or a
harness around one. Language models arrange the work; certified numbers
always come from the tools.
</div>
</section>

<section>
<h2>How it works</h2>
<div class="steps">
<div class="step"><div class="num">1</div><div>
<h3>Install the umbrella</h3>
<p>One pip package stands in front of the whole ecosystem: the verified
component catalog, the MCP server, a synthetic demo, and this landing
page — all generated from one source of truth.</p>
</div></div>
<div class="step"><div class="num">2</div><div>
<h3>Wire it into any MCP client</h3>
<p>The server speaks MCP over stdio, so any MCP-capable editor or
assistant can browse the catalog, search it, and pull install guidance
without a browser.</p>
</div></div>
<div class="step"><div class="num">3</div><div>
<h3>Compose the engines on real work</h3>
<p>Underwrite with the deterministic engine, wrap agents with the
harness, study markets with verified data separation, and keep NOI
variance honest month over month — one component per job, numbers
from the engine every time.</p>
</div></div>
</div>
</section>

<section>
<h2>What the server knows</h2>
<p class="lead">Eleven read-only tools over the verified catalog. No
network calls, no private data, typed refusals instead of crashes.</p>
<div class="tool-list">
{tool_rows}
</div>
</section>

<section>
<h2>Get started</h2>
<div class="install">pip install platworks

# MCP client config (stdio):
{{
  "mcpServers": {{
    "platworks": {{
      "command": "platworks-mcp"
    }}
  }}
}}

# or try the whole thing locally:
platworks catalog        # browse the verified catalog
platworks demo &amp;&amp; python platworks-demo/run_demo.py   # real MCP round-trip
platworks landing        # render this page from the catalog</div>
</section>

<section>
<h2>Components</h2>
<p class="lead">Public components link to their verified repositories;
private ones are listed by name and make no public claims.</p>
<div class="grid">
{cards}
</div>
{private_note}
</section>

<section>
<h2>Questions</h2>
<div class="faq">
<details>
<summary>Is any of the data real?</summary>
<p>No. The demo portfolio is fabricated end to end — invented
properties, cities, and numbers — and is labeled synthetic everywhere
it appears. The catalog itself carries only public repository
metadata, verified against the GitHub API on 2026-09-24.</p>
</details>
<details>
<summary>What if a tool is given a bad name or category?</summary>
<p>It never crashes and never guesses. Every tool returns JSON, and
failures come back as typed refusals inside the payload —
<code>{{"error": {{"type": ..., "message": ...}}}}</code> — naming the
valid options so a client can self-correct.</p>
</details>
<details>
<summary>Why do private components have no links or descriptions?</summary>
<p>Because the catalog refuses to make unverified public claims. A
private component ships only its name and category; when it is
published and verified, the catalog — and every tool and this page —
updates from the same source of truth.</p>
</details>
</div>
</section>

<footer>
<p>All repositories are Apache-2.0. All sample and demo data in the
ecosystem is synthetic; no real deal, tenant, or portfolio data ships in
any public repository.</p>
<p>Descriptions on this page are copied from each repository&rsquo;s
verified GitHub metadata (verified 2026-09-24).</p>
</footer>
</div>
</body>
</html>
"""


def render_page(output_path, overwrite=False):
    """Write the landing page to OUTPUT_PATH; return the absolute path."""
    output_path = os.path.abspath(output_path)
    if os.path.exists(output_path) and not overwrite:
        raise LandingOutputExistsError(
            f"landing page already exists: {output_path} "
            "(pass overwrite=True to replace)"
        )
    with open(output_path, "w") as fh:
        fh.write(build_html())
    return output_path