#!/usr/bin/env python3
"""
build-paper.py — render the whitepaper markdown into site/paper.html.

Dependency-free (Python 3.9 stdlib only). Handles the subset of Markdown the
whitepaper uses: ATX headings, GFM pipe tables, fenced code, blockquotes,
ordered/unordered lists, thematic breaks, and inline code/links/bold/italic.

PRODUCT-NAME COHERENCE (identity-brief.md §7, non-negotiable for apex coherence):
the source paper still carries the working name "Elk OS"; the resolved product
noun is "Muster". We token-swap the standalone product name "Elk OS" -> "Muster"
at render time. We deliberately do NOT touch:
  - "Analog Elk"  (the origin / case study, must remain)
  - "bin/elk-os"  (the literal binary/command name)
This is the {{PRODUCT}} token swap the brief prescribes; meaning is preserved.

Run:  python3 site/build-paper.py
Commits the BUILT site/paper.html so Caddy can serve it as a plain file.
"""
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "docs", "whitepaper", "elk-os-whitepaper.md"))
OUT = os.path.join(HERE, "paper.html")

PORTAL = "https://app.34.220.64.149.sslip.io"
BOARD = "https://cms.34.220.64.149.sslip.io"


def product_swap(text: str) -> str:
    """Swap the working name 'Elk OS' -> 'Muster' without hitting 'Analog Elk'
    or the lowercase 'bin/elk-os' command."""
    return re.sub(r"\bElk OS\b", "Muster", text)


def inline(text: str) -> str:
    """Escape HTML, then apply inline markdown. Code spans are protected first."""
    placeholders = []

    def stash(htmlfrag: str) -> str:
        placeholders.append(htmlfrag)
        return "\x00%d\x00" % (len(placeholders) - 1)

    # inline code first (content escaped, not further processed)
    def code_sub(m):
        return stash("<code>" + html.escape(m.group(1)) + "</code>")
    text = re.sub(r"`([^`]+)`", code_sub, text)

    # escape the rest
    text = html.escape(text)

    # links [text](url)  (text/url already escaped above)
    def link_sub(m):
        label, url = m.group(1), m.group(2)
        return stash('<a href="%s">%s</a>' % (url, label))
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link_sub, text)

    # bold then italic
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)

    # restore protected fragments
    for i, frag in enumerate(placeholders):
        text = text.replace("\x00%d\x00" % i, frag)
    return text


def slugify(text: str) -> str:
    s = re.sub(r"<[^>]+>", "", text)
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).strip().lower()
    return re.sub(r"\s+", "-", s)[:60]


def is_table_sep(line: str) -> bool:
    return bool(re.match(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$", line)) and "-" in line


def split_row(line: str):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def render(md: str) -> str:
    md = product_swap(md)
    lines = md.split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        line = raw.strip()

        if line == "":
            i += 1
            continue

        if line == "---" or line == "***" or line == "___":
            out.append("<hr>")
            i += 1
            continue

        # fenced code
        if line.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence
            out.append('<pre class="code"><code>%s</code></pre>'
                       % html.escape("\n".join(buf)))
            continue

        # headings
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            content = inline(m.group(2))
            if level <= 3:
                out.append('<h%d id="%s">%s</h%d>'
                           % (level, slugify(m.group(2)), content, level))
            else:
                out.append("<h%d>%s</h%d>" % (level, content, level))
            i += 1
            continue

        # tables
        if "|" in raw and i + 1 < n and is_table_sep(lines[i + 1]):
            header = split_row(raw)
            i += 2  # skip header + separator
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            thead = "".join("<th>%s</th>" % inline(c) for c in header)
            body = ""
            for r in rows:
                body += "<tr>" + "".join("<td>%s</td>" % inline(c) for c in r) + "</tr>"
            out.append('<div class="table-wrap"><table class="proof"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
                       % (thead, body))
            continue

        # blockquote
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = inline(" ".join(b.strip() for b in buf if b.strip()))
            out.append("<blockquote><p>%s</p></blockquote>" % inner)
            continue

        # unordered list
        if re.match(r"^[-*]\s+", line):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append("<li>%s</li>" % inline(re.sub(r"^[-*]\s+", "", lines[i].strip())))
                i += 1
            out.append("<ul>%s</ul>" % "".join(items))
            continue

        # ordered list
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append("<li>%s</li>" % inline(re.sub(r"^\d+\.\s+", "", lines[i].strip())))
                i += 1
            out.append("<ol>%s</ol>" % "".join(items))
            continue

        # paragraph
        buf = [raw]
        i += 1
        while i < n:
            nxt = lines[i]
            s = nxt.strip()
            if (s == "" or s.startswith("#") or s.startswith(">")
                    or s == "---" or s.startswith("```")
                    or re.match(r"^[-*]\s+", s) or re.match(r"^\d+\.\s+", s)
                    or ("|" in nxt and i + 1 < n and is_table_sep(lines[i + 1]))):
                break
            buf.append(nxt)
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(b.strip() for b in buf)))

    return "\n".join(out)


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Muster — the whitepaper · The Task Record Is the Coordination Substrate</title>
<meta name="description" content="A field report by Mike Walliser. How a governed fleet of AI agents built, and publicly shipped, the product that packages its own governance, in roughly 2.5 hours on a $3-a-month box.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 64'%3E%3Cpolyline points='6,58 18,58 18,44 30,44 30,30 42,30' fill='none' stroke='%2325402F' stroke-width='5' stroke-linecap='square'/%3E%3Cpolyline points='30,30 30,16 42,16' fill='none' stroke='%23DE7330' stroke-width='5' stroke-linecap='square'/%3E%3Ccircle cx='42' cy='16' r='5' fill='%23DE7330'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Hanken+Grotesk:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
<style>
  .paper-doc {{ max-width: 70ch; margin: 0 auto; padding: 0 1.4rem; }}
  .paper-doc h1 {{ font-size: clamp(2.1rem,5.5vw,3rem); line-height:1.08; letter-spacing:-0.02em; margin: 0 0 0.6rem; }}
  .paper-doc h2 {{ font-size: clamp(1.5rem,4vw,1.95rem); margin: 2.6rem 0 0.6rem; letter-spacing:-0.01em; }}
  .paper-doc h3 {{ font-family: var(--body); font-weight:600; font-size:1.3rem; margin: 2rem 0 0.4rem; }}
  .paper-doc p {{ font-size: 1.125rem; line-height: 1.7; margin: 0 0 1.1rem; }}
  .paper-doc blockquote {{ margin: 1.6rem 0; padding: 0.2rem 0 0.2rem 1.1rem; border-left: 3px solid var(--ember); }}
  .paper-doc blockquote p {{ font-family: var(--display); font-size: 1.3rem; line-height: 1.35; color: var(--pine); margin: 0; }}
  .paper-doc ul, .paper-doc ol {{ padding-left: 1.3rem; }}
  .paper-doc li {{ margin: 0.4rem 0; line-height: 1.6; }}
  .paper-doc hr {{ border:0; border-top:1px solid var(--bone-rule); margin: 2.4rem 0; }}
  .paper-doc code {{ font-family: var(--mono); font-size: 0.9em; background: var(--paper-2); padding: 0.08em 0.34em; border-radius: 3px; }}
  .paper-doc pre.code code {{ background: transparent; padding: 0; }}
  .paper-hd {{ padding: 1.2rem 0 0; }}
  .backhome {{ display:inline-flex; gap:0.4rem; align-items:center; font-family:var(--mono); font-size:0.82rem; text-decoration:none; color:var(--pine); }}
  .paper-doc table.proof {{ font-size: 0.92rem; }}
</style>
</head>
<body>
<a class="skip" href="#paper-main">Skip to the paper</a>
<header class="topbar is-visible" style="transform:none;">
  <a class="topbar__brand" href="index.html" aria-label="Muster — home">
    <svg viewBox="0 0 48 64" aria-hidden="true"><polyline points="6,58 18,58 18,44 30,44 30,30 42,30" fill="none" stroke="var(--pine)" stroke-width="4.5" stroke-linecap="square"/><polyline points="30,30 30,16 42,16" fill="none" stroke="var(--ember)" stroke-width="4.5" stroke-linecap="square"/><circle cx="42" cy="16" r="4.5" fill="var(--ember)"/></svg>
    Muster
  </a>
  <span class="topbar__spacer"></span>
  <div class="topbar__cta">
    <a class="btn btn--live btn--sm" href="{portal}" target="_blank" rel="noopener">Live portal ↗</a>
    <a class="btn btn--sm" href="index.html">← The build log</a>
  </div>
</header>

<main class="band band-paper" id="paper-main">
  <div class="paper-doc paper-hd">
    <a class="backhome" href="index.html">← back to the build log</a>
  </div>
  <article class="paper-doc">
{body}
  </article>
  <div class="paper-doc" style="margin-top:3rem;">
    <hr>
    <p class="fineprint">Live exhibits: <a class="livechip" href="{portal}" target="_blank" rel="noopener">app.34.220.64.149.sslip.io</a> &nbsp; <a class="livechip" href="{board}" target="_blank" rel="noopener">cms.34.220.64.149.sslip.io</a></p>
    <p class="fineprint">sslip.io demo cert — your browser will warn once; it's a $3/mo box. Treat the TLS as "reachable," not "trusted." &nbsp;·&nbsp; <a href="#" onclick="window.print();return false;">Print / PDF</a></p>
    <p class="fineprint">Rendered from <code>docs/whitepaper/elk-os-whitepaper.md</code>. Product name resolved to <strong>Muster</strong> per the identity brief; "Analog Elk" (origin/case study) and <code>bin/elk-os</code> (command) are preserved verbatim.</p>
  </div>
</main>
</body>
</html>
"""


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        md = f.read()
    body = render(md)
    page = TEMPLATE.format(body=body, portal=PORTAL, board=BOARD)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print("wrote %s (%d bytes)" % (OUT, len(page)))


if __name__ == "__main__":
    main()
