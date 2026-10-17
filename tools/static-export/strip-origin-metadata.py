#!/usr/bin/env python3
"""strip-origin-metadata.py: scrub Analog Elk SEO metadata from the static
app.musterr.dev export.

The demo portal image is the Analog Elk portal rebranded in the UI. Its root
layout still ships the agency's SEO head: rel=canonical and og:url pointing at
https://analogelk.com, og/twitter images on analogelk.com, three JSON-LD blocks
(@id https://analogelk.com/#organization|#website|#localbusiness), and preconnect
hints to cms.analogelk.com. A shared app.musterr.dev link previews as the agency.

Next.js App Router emits every one of these twice per page: once as HTML and
once inside the RSC flight payload (self.__next_f.push([1,"..."]) chunks) that
React hydrates from. Rewriting only the HTML would cause a hydration mismatch and
the client could re-render the old values back in, so this rewrites both layers
to the same values. Elements are rewritten in place, never removed, so the
element tree stays identical for hydration.

Usage: strip-origin-metadata.py <export-app-dir> [--check]
  --check   report remaining origin metadata, change nothing (exit 1 if any)

Idempotent: a second run finds nothing to change.
"""
import json
import pathlib
import re
import sys

APP_ORIGIN = "https://app.musterr.dev"
HOME_ORIGIN = "https://musterr.dev"
CMS_ORIGIN = "https://cms.musterr.dev"
OLD_SITE = "https://analogelk.com"
OLD_CMS = "https://cms.analogelk.com"
OG_IMAGE = HOME_ORIGIN + "/assets/muster-board.png"
OG_W, OG_H = "1440", "900"
OG_ALT = "The Muster task board: rows grouped by status, in the team portal."

ORG = {"@context": "https://schema.org", "@type": "Organization",
       "@id": HOME_ORIGIN + "/#organization", "name": "Muster", "url": HOME_ORIGIN}
WEBSITE = {"@context": "https://schema.org", "@type": "WebSite",
           "@id": APP_ORIGIN + "/#website", "url": APP_ORIGIN + "/", "name": "Muster demo",
           "publisher": {"@id": HOME_ORIGIN + "/#organization"}}
APP = {"@context": "https://schema.org", "@type": "WebApplication",
       "@id": APP_ORIGIN + "/#app", "name": "Muster demo", "url": APP_ORIGIN + "/",
       "applicationCategory": "BusinessApplication",
       "publisher": {"@id": HOME_ORIGIN + "/#organization"}}


def scrubbed_ld(raw):
    """Return replacement JSON-LD text for an origin-branded block, else None."""
    if "analogelk.com" not in raw:
        return None
    try:
        kind = json.loads(raw).get("@type")
    except (ValueError, AttributeError):
        kind = None
    obj = ORG if kind == "Organization" else WEBSITE if kind == "WebSite" else APP
    return json.dumps(obj, separators=(",", ":"))


def head_values(route_url):
    """(property-or-name, old value, new value) for meta/link rewrites."""
    return [
        ("og:url", OLD_SITE, route_url),
        ("og:image", OLD_SITE + "/og-image.png", OG_IMAGE),
        ("og:image:width", "1200", OG_W),
        ("og:image:height", "630", OG_H),
        ("og:image:alt", "Muster preview image", OG_ALT),
        ("twitter:image", OLD_SITE + "/og-image.png", OG_IMAGE),
    ]


def rewrite_html_layer(html, route_url, ld_map):
    n = 0
    # rel=canonical
    html, k = re.subn(r'(<link rel="canonical" href=")' + re.escape(OLD_SITE) + r'/?(")',
                      lambda m: m.group(1) + route_url + m.group(2), html)
    n += k
    # og:* / twitter:* (only when the image is the origin's; alt/size follow it)
    if OLD_SITE + "/og-image.png" in html or 'content="' + OLD_SITE + '"' in html:
        for prop, old, new in head_values(route_url):
            attr = "name" if prop.startswith("twitter:") else "property"
            pat = '<meta %s="%s" content="%s"/>' % (attr, prop, old)
            rep = '<meta %s="%s" content="%s"/>' % (attr, prop, new)
            k = html.count(pat)
            html = html.replace(pat, rep)
            n += k
    # preconnect / dns-prefetch
    for rel in ("preconnect", "dns-prefetch"):
        pat = '<link rel="%s" href="%s"' % (rel, OLD_CMS)
        k = html.count(pat)
        html = html.replace(pat, '<link rel="%s" href="%s"' % (rel, CMS_ORIGIN))
        n += k

    # JSON-LD blocks (HTML layer)
    def ld(m):
        nonlocal n
        new = scrubbed_ld(m.group(2))
        if new is None:
            return m.group(0)
        ld_map[m.group(2)] = new
        n += 1
        return m.group(1) + new + m.group(3)

    html = re.sub(r'(<script type="application/ld\+json">)(.*?)(</script>)', ld, html, flags=re.S)
    return html, n


LD_KEY = '"type":"application/ld+json","dangerouslySetInnerHTML":{"__html":'
DEC = json.JSONDecoder()


def rewrite_flight_text(text, route_url):
    """Rewrite one decoded flight chunk. Returns (text, changes)."""
    n = 0
    reps = [
        ('"rel":"canonical","href":"%s"' % OLD_SITE, '"rel":"canonical","href":"%s"' % route_url),
        ('"rel":"canonical","href":"%s/"' % OLD_SITE, '"rel":"canonical","href":"%s"' % route_url),
        ('"rel":"preconnect","href":"%s"' % OLD_CMS, '"rel":"preconnect","href":"%s"' % CMS_ORIGIN),
        ('"rel":"dns-prefetch","href":"%s"' % OLD_CMS, '"rel":"dns-prefetch","href":"%s"' % CMS_ORIGIN),
    ]
    if OLD_SITE + "/og-image.png" in text or '"content":"%s"' % OLD_SITE in text:
        for prop, old, new in head_values(route_url):
            attr = "name" if prop.startswith("twitter:") else "property"
            reps.append(('"%s":"%s","content":"%s"' % (attr, prop, old),
                         '"%s":"%s","content":"%s"' % (attr, prop, new)))
    for a, b in reps:
        k = text.count(a)
        if k:
            text = text.replace(a, b)
            n += k
    # JSON-LD inside dangerouslySetInnerHTML
    out, pos = [], 0
    while True:
        i = text.find(LD_KEY, pos)
        if i < 0:
            break
        j = i + len(LD_KEY)
        try:
            val, end = DEC.raw_decode(text, j)
        except ValueError:
            break  # value split across chunks; reported by --check
        new = scrubbed_ld(val) if isinstance(val, str) else None
        out.append(text[pos:j])
        if new is None:
            out.append(text[j:end])
        else:
            out.append(json.dumps(new, ensure_ascii=False))
            n += 1
        pos = end
    out.append(text[pos:])
    return "".join(out), n


PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')


def encode_js_string(s):
    enc = json.dumps(s, ensure_ascii=False)
    return (enc.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def rewrite_flight_layer(html, route_url):
    total = 0

    def push(m):
        nonlocal total
        decoded = json.loads(m.group(1))
        new, k = rewrite_flight_text(decoded, route_url)
        if not k:
            return m.group(0)
        total += k
        return "self.__next_f.push([1,%s])" % encode_js_string(new)

    return PUSH.sub(push, html), total


# What --check counts as remaining origin metadata (both layers).
LEFTOVER = [
    re.compile(r'rel\\?"?[=:]\\?"canonical\\?",?\\?"?\s?href\\?"?[=:]\\?"https://analogelk\.com'),
    re.compile(r'og:url\\?"?[,\s]*\\?"?content\\?"?[=:]\\?"https://analogelk\.com'),
    re.compile(r'https://analogelk\.com/og-image'),
    re.compile(r'https://analogelk\.com/#(organization|website|localbusiness)'),
    re.compile(r'(preconnect|dns-prefetch)\\?"?[,\s]*\\?"?href\\?"?[=:]\\?"https://cms\.analogelk\.com'),
]


def route_for(app_dir, f):
    rel = "/" + str(f.relative_to(app_dir)).replace("\\", "/")
    if rel.endswith("/index.html"):
        rel = rel[: -len("index.html")]
    return APP_ORIGIN + rel


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if len(args) != 1:
        print(__doc__.strip().splitlines()[-4])
        sys.exit(2)
    app_dir = pathlib.Path(args[0]).resolve()
    files = sorted(app_dir.rglob("*.html"))
    changed = changes = left_files = 0
    for f in files:
        html = f.read_text(encoding="utf-8")
        if not check:
            url = route_for(app_dir, f)
            new, n1 = rewrite_html_layer(html, url, {})
            new, n2 = rewrite_flight_layer(new, url)
            if n1 + n2:
                f.write_text(new, encoding="utf-8")
                changed += 1
                changes += n1 + n2
                html = new
        if any(p.search(html) for p in LEFTOVER):
            left_files += 1
            if check or left_files <= 5:
                print("origin metadata remains:", f.relative_to(app_dir))
    print("html files: %d | rewritten: %d (%d edits) | still carrying origin metadata: %d"
          % (len(files), changed, changes, left_files))
    sys.exit(1 if left_files else 0)


if __name__ == "__main__":
    main()
