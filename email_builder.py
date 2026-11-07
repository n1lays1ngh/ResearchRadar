"""Builds the digest as a broadsheet-style newspaper (table layout, inline CSS) plus plain text.

Design: newsprint background, serif type, black rules, square edges and a single
deep-red spot colour. No rounded cards, gradients or emoji.
"""
import re
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote, urlparse

import arxiv_categories
import config
from summarizer import NOT_STATED

# --- house style -------------------------------------------------------------------
SERIF = "Georgia,serif"
SANS = "Helvetica,Arial,sans-serif"
PAGE = "#E8E3D7"      # desk behind the paper
PAPER = "#FBF8F1"     # newsprint
INK = "#151515"
INK_2 = "#363636"
MUTED = "#6E6758"
HAIR = "#CBC3B0"
RED = "#9E1B1E"       # the one spot colour
PAPER_W = 1000      # wide broadsheet; columns stack on phones
PAD_PX = 32
PAD = f"{PAD_PX}px"
CONTENT_W = PAPER_W - 2 - 2 * PAD_PX   # inside the 1px border and gutters


def e(value) -> str:
    """Escape any dynamic text (and attribute values) for HTML."""
    return escape(str(value or ""), quote=True)


def chat_url(paper_id: str) -> str:
    """The paper's page on the web app (with chat), or '' when SITE_URL is unset."""
    return config.site_url(f"paper/{quote(paper_id)}")


def byline(authors: list[str], limit: int = 3) -> str:
    """'A, B and C' or 'A, B, C and others'."""
    if not authors:
        return "Unknown authors"
    if len(authors) > limit:
        return ", ".join(authors[:limit]) + " and others"
    return authors[0] if len(authors) == 1 else ", ".join(authors[:-1]) + " and " + authors[-1]


def long_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%-d %B %Y")
    except ValueError:
        return iso[:10]


def _roman(n: int) -> str:
    out = ""
    for value, sym in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out, n = out + sym, n - value
    return out or "I"


def _edition(meta: dict) -> tuple[str, str]:
    """('VOL. I · NO. 45', 'Monday, 9 November 2026') from the issue date."""
    issued = meta.get("issued") or datetime.now(timezone.utc)
    return (f"Vol. {_roman(issued.year - 2025)} · No. {issued.isocalendar().week}",
            issued.strftime("%A, %-d %B %Y"))


# --- type primitives ----------------------------------------------------------------
def _caps(text: str, color: str = MUTED, size: int = 10, weight: int = 700, spacing: str = ".14em") -> str:
    return (f'<span style="font:{weight} {size}px {SANS};letter-spacing:{spacing};color:{color};">'
            f'{e(str(text).upper())}</span>')


def _rule(weight: int = 1, color: str = INK, margin: str = "0") -> str:
    return (f'<div style="border-top:{weight}px solid {color};height:0;line-height:0;font-size:0;'
            f'margin:{margin};">&nbsp;</div>')


def _double_rule(margin: str = "0") -> str:
    return (f'<div style="margin:{margin};border-top:3px solid {INK};height:2px;line-height:0;font-size:0;'
            f'border-bottom:1px solid {INK};">&nbsp;</div>')


def _p(html_text: str, size: int = 15, color: str = INK_2, margin: str = "0 0 12px", style: str = "") -> str:
    return f'<p style="margin:{margin};font:{size}px/1.62 {SERIF};color:{color};{style}">{html_text}</p>'


def _runin(label: str, text: str) -> str:
    """Newspaper run-in head: bold small caps label, then the paragraph."""
    color = MUTED if text == NOT_STATED else INK_2
    body = e(text) if color == INK_2 else f'<span style="color:{color};">{e(text)}</span>'
    return _p(f'{_caps(label, INK, 10.5, 700, ".12em")}&nbsp; {body}')


def _dropcap_para(label: str, text: str) -> str:
    """Opening paragraph with a drop cap (degrades to a plain paragraph in Outlook)."""
    text = text or NOT_STATED
    if text == NOT_STATED:
        return _runin(label, text)
    first, rest = text[0], text[1:]
    cap = (f'<span style="float:left;font:52px/44px {SERIF};font-weight:700;'
           f'color:{INK};padding:5px 8px 0 0;">{e(first)}</span>')
    head = f'<div style="margin:0 0 6px;">{_caps(label.rstrip("."), INK, 10.5, 700, ".12em")}</div>'
    return head + _p(f"{cap}{e(rest)}")


def _button(label: str, href: str, solid: bool = False) -> str:
    bg, fg = (INK, PAPER) if solid else ("transparent", INK)
    return (f'<a href="{e(href)}" target="_blank" style="display:inline-block;margin:0 8px 8px 0;'
            f'padding:8px 14px;border:1px solid {INK};background:{bg};color:{fg};font:700 10.5px {SANS};'
            f'letter-spacing:.12em;text-decoration:none;">{e(label.upper())}</a>')


def _host(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


# --- columns -------------------------------------------------------------------------
def _cols(blocks: list[str], gap: int = 36) -> str:
    """Side-by-side columns that stack on narrow screens (fluid-hybrid: inline-blocks, no media queries)."""
    blocks = [b for b in blocks if b]
    if not blocks:
        return ""
    n = len(blocks)
    width = (CONTENT_W - gap * (n - 1)) // n - 1
    # class names are only used by the PDF print stylesheet (pdf_export.PRINT_CSS)
    col = (f'<div class="rc" style="display:inline-block;vertical-align:top;width:100%;max-width:{width}px;'
           f'font-size:15px;text-align:left;">')
    spacer = f'<div class="rg" style="display:inline-block;width:{gap}px;height:1px;font-size:0;">&nbsp;</div>'
    return f'<div class="rr" style="font-size:0;">' + spacer.join(col + b + "</div>" for b in blocks) + "</div>"


def _deal(items: list[str], n: int) -> list[str]:
    """Deal items round-robin into n column bodies (keeps columns roughly even)."""
    return ["".join(items[i::n]) for i in range(min(n, len(items)))]


# --- stories -----------------------------------------------------------------------
def _kicker(p: dict, lead: bool) -> str:
    cat = p.get("category", "")
    kicker = f"{'Lead story' if lead else 'Report'} · {cat}"
    if cat in arxiv_categories.NAMES:
        kicker += f" · {arxiv_categories.NAMES[cat]}"
    return kicker


def _story_head(p: dict, lead: bool) -> str:
    """Kicker, headline, standfirst and byline."""
    ins = p.get("insight") or {}
    head_size, deck_size = (40, 20) if lead else (24, 16)
    return f"""
 <div style="margin-bottom:8px;">{_caps(_kicker(p, lead), RED)}</div>
 <a href="{e(p['abs_url'])}" target="_blank" style="display:block;font:700 {head_size}px/1.12 {SERIF};color:{INK};text-decoration:none;letter-spacing:-.01em;">{e(p['title'])}</a>
 <div style="margin:10px 0 12px;font:{deck_size}px/1.45 {SERIF};font-style:italic;color:{INK_2};">{e(ins.get('tldr', ''))}</div>
 <div style="padding:7px 0;border-top:1px solid {HAIR};border-bottom:1px solid {HAIR};margin-bottom:14px;">
  {_caps('By ' + byline(p.get('authors', [])), INK, 10, 700, '.08em')}
  {_caps(f" · Submitted {long_date(p.get('published', ''))} · arXiv:{p['id']}", MUTED, 10, 400, '.08em')}
 </div>"""


def _story_main(ins: dict) -> str:
    """Problem (drop cap), approach and key findings."""
    findings = "".join(
        f'<p style="margin:0 0 6px;padding-left:16px;text-indent:-16px;font:15px/1.55 {SERIF};color:{INK_2};">'
        f'<span style="color:{RED};font-size:10px;">&#9632;</span>&nbsp;&nbsp; {e(f)}</p>'
        for f in ins.get("key_findings", []))
    return (_dropcap_para("The problem.", ins.get("problem", NOT_STATED))
            + _runin("The approach.", ins.get("approach", NOT_STATED))
            + f'<div style="margin:4px 0 8px;">{_caps("Key findings", INK, 10.5, 700, ".12em")}</div>'
            + f'<div style="margin-bottom:10px;">{findings}</div>')


def _story_side(p: dict, ins: dict, lead: bool) -> str:
    """Limitations, why it matters (pull quote on the lead), tags, buttons and web links."""
    why = ins.get("why_it_matters", NOT_STATED)
    if lead and why != NOT_STATED:
        why_html = (f'<div style="margin:6px 0 16px;padding:14px 6px;border-top:2px solid {INK};'
                    f'border-bottom:1px solid {INK};text-align:center;">'
                    f'<div style="margin-bottom:6px;">{_caps("Why it matters", RED)}</div>'
                    f'<div style="font:21px/1.4 {SERIF};font-style:italic;color:{INK};">&ldquo;{e(why)}&rdquo;</div></div>')
    else:
        why_html = _runin("Why it matters.", why)

    buttons = _button("Read the abstract", p["abs_url"], solid=True) + _button("Full paper (PDF)", p["pdf_url"])
    if chat_url(p["id"]):
        buttons += _button("Discuss this paper", chat_url(p["id"]))

    tags = ins.get("tags") or []
    filed = (f'<div style="margin:4px 0 12px;font:13px {SERIF};font-style:italic;color:{MUTED};">'
             f'Filed under: {e(" · ".join(tags))}</div>') if tags else ""

    links = p.get("links") or []
    online = ""
    if links:
        items = " &nbsp;·&nbsp; ".join(
            f'<a href="{e(l["url"])}" target="_blank" style="color:{INK};text-decoration:underline;">'
            f'{e(l["title"][:60])}</a>&nbsp;<span style="color:{MUTED};">({e(l.get("host") or _host(l["url"]))})</span>'
            for l in links)
        online = (f'<div style="margin-top:6px;padding-top:10px;border-top:1px solid {HAIR};'
                  f'font:13px/1.6 {SERIF};color:{INK_2};">{_caps("Also online", RED)}&nbsp; {items}</div>')

    note = ""
    if ins.get("source") == "abstract":
        note = (f'<div style="margin-top:8px;font:12px {SERIF};font-style:italic;color:{MUTED};">'
                f'Editor&rsquo;s note: this report was prepared from the abstract alone.</div>')

    limitations = _runin("Limitations.", ins.get("limitations", NOT_STATED))
    order = [why_html, limitations] if lead else [limitations, why_html]
    return "".join(order) + filed + f'<div style="margin-top:4px;">{buttons}</div>' + online + note


def _lead_story(p: dict) -> str:
    """Front-page lead: full-width headline, body set in two columns."""
    ins = p.get("insight") or {}
    return f"""
<tr><td style="padding:22px {PAD} 8px;">
 {_story_head(p, True)}
 {_cols([_story_main(ins), _story_side(p, ins, True)])}
</td></tr>"""


def _reports(papers: list[dict]) -> str:
    """Secondary reports, set side by side."""
    if not papers:
        return ""
    blocks = []
    for p in papers:
        ins = p.get("insight") or {}
        blocks.append(_story_head(p, False) + _story_main(ins) + _story_side(p, ins, False))
    return f"""
<tr><td style="padding:14px {PAD} 0;">{_rule(1, INK)}</td></tr>
<tr><td style="padding:20px {PAD} 8px;">{_cols(blocks, 40)}</td></tr>"""


def _briefs(title: str, papers: list[dict]) -> str:
    """'In brief': three columns (stacking on narrow screens)."""
    if not papers:
        return ""
    items = [
        f'<div style="padding:0 0 16px;">'
        f'<a href="{e(p["abs_url"])}" target="_blank" style="font:700 15px/1.35 {SERIF};color:{INK};text-decoration:none;">'
        f'{e(p["title"])}</a>'
        f'<div style="margin-top:4px;font:12.5px/1.45 {SERIF};font-style:italic;color:{MUTED};">'
        f'{e(byline(p.get("authors", []), 2))} &middot; {e(p.get("category", ""))} &middot; '
        f'{e(long_date(p.get("published", "")))}</div></div>'
        for p in papers]
    return f"""
<tr><td style="padding:22px {PAD} 0;">
 {_rule(3, INK)}
 <div style="padding:8px 0 14px;">{_caps(title, INK, 11, 700, ".16em")}</div>
 {_cols(_deal(items, 3), 30)}
</td></tr>"""


def _journals(results: list[dict]) -> str:
    """'Elsewhere in the journals' (Tavily 'Beyond arXiv' results), two columns."""
    if not results:
        return ""
    items = [
        f'<div style="padding:0 0 14px;margin-bottom:14px;border-bottom:1px solid {HAIR};">'
        f'<div style="margin-bottom:3px;">{_caps(r.get("host") or _host(r["url"]), RED, 9.5)}</div>'
        f'<a href="{e(r["url"])}" target="_blank" style="font:700 16px/1.35 {SERIF};color:{INK};text-decoration:none;">'
        f'{e(r["title"])}</a>'
        f'<div style="margin-top:4px;font:14px/1.55 {SERIF};color:{INK_2};">{e(r.get("snippet", ""))}</div></div>'
        for r in results]
    return f"""
<tr><td style="padding:10px {PAD} 0;">
 {_rule(3, INK)}
 <div style="padding:8px 0 4px;">{_caps("Elsewhere in the journals", INK, 11, 700, ".16em")}</div>
 <div style="padding:0 0 12px;font:13px {SERIF};font-style:italic;color:{MUTED};">
  Peer-reviewed and web sources from the past month, beyond arXiv.</div>
 {_cols(_deal(items, 2), 40)}
</td></tr>"""


def _section(s: dict) -> str:
    d = s["domain"]
    code = d["key"]
    name = arxiv_categories.NAMES.get(code, d["title"])
    also = [c for c in d["categories"] if c != code]
    scope = f"Also drawing on {', '.join(also)}. " if also else ""
    featured = s["featured"]
    if featured:
        stories = _lead_story(featured[0]) + _reports(featured[1:])
    else:
        stories = (f'<tr><td style="padding:18px {PAD};">'
                   f'{_p("No new preprints matched this section during the week.", style="font-style:italic;")}'
                   f'</td></tr>')
    overview = s.get("overview", "")
    note = ""
    if overview:
        note = f"""
<tr><td style="padding:16px {PAD} 0;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr><td style="padding:14px 0 6px;border-bottom:1px solid {HAIR};">
   <div style="margin-bottom:8px;">{_caps("The week in brief", RED)}</div>
   {_p(e(overview), 17, INK, "0 0 10px", "font-style:italic;")}
  </td></tr></table>
</td></tr>"""
    return f"""
<tr><td style="padding:40px {PAD} 0;">
 {_rule(4, INK)}
 <div style="padding-top:10px;">
  <a href="https://arxiv.org/list/{e(code)}/recent" target="_blank" style="text-decoration:none;">
   {_caps("Section · arXiv " + code, RED, 11, 700, ".1em")}</a>
  <div style="margin-top:4px;font:700 36px/1.1 {SERIF};color:{INK};">{e(name)}</div>
 </div>
 <div style="margin-top:8px;padding:6px 0;border-top:1px solid {INK};border-bottom:1px solid {INK};
  font:12.5px {SERIF};font-style:italic;color:{MUTED};">
  {e(scope)}Coverage: {e(d['focus'])}.</div>
</td></tr>
{note}
{stories}
{_briefs(f"In brief · more from {code}", s["more"])}
{_journals(s.get("beyond", []))}"""


def _index(sections: list[dict]) -> str:
    """'Inside this edition': one column per section on desktop, stacked on phones."""
    blocks = [
        f'<div style="padding:10px 0 12px;border-left:2px solid {INK};padding-left:10px;'
        f'word-break:normal;overflow-wrap:break-word;">'
        f'<div>{_caps(s["domain"]["key"], RED, 10)}</div>'
        f'<div style="margin-top:3px;font:700 15px/1.3 {SERIF};color:{INK};">'
        f'{e(arxiv_categories.NAMES.get(s["domain"]["key"], s["domain"]["title"]))}</div>'
        f'<div style="margin-top:2px;font:12px {SERIF};font-style:italic;color:{MUTED};">'
        f'{len(s["featured"])} reports, {len(s["more"])} in brief</div></div>'
        for s in sections]
    return f"""
<tr><td style="padding:0 {PAD};">
 <div style="border-bottom:1px solid {INK};padding-bottom:4px;">{_cols(blocks, 24)}</div>
</td></tr>"""


def _app_links(read_path: str = "", read_label: str = "Read online or download the PDF") -> str:
    """'Read online / PDF · Subscribe · Unsubscribe' line, when the site URL is configured."""
    if not config.SITE_URL:
        return ""
    style = f"color:{INK};text-decoration:underline;"
    links = [(read_label, config.site_url(read_path)),
             ("Subscribe", config.site_url("subscribe")),
             ("Unsubscribe or change", config.site_url("subscribe", action="unsubscribe"))]
    return (f'<div style="text-align:center;margin:0 0 12px;font:12.5px/1.6 {SERIF};color:{MUTED};">'
            + " &nbsp;·&nbsp; ".join(f'<a href="{e(u)}" style="{style}">{t}</a>' for t, u in links)
            + "</div>")


# --- public API ---------------------------------------------------------------------
def _minify(html: str) -> str:
    """Drop indentation and whitespace between tags so Gmail doesn't clip the email (~102 KB limit)."""
    html = re.sub(r">\s+<", "><", html)
    return re.sub(r"\n\s*", " ", html)


def build_html(sections: list[dict], meta: dict) -> str:
    """Full HTML email (minified). meta: week_range, scanned, picked, issued (datetime, optional)."""
    return _minify(_build_html(sections, meta))


def _build_html(sections: list[dict], meta: dict) -> str:
    vol, date_line = _edition(meta)
    leads = [s["featured"][0]["title"] for s in sections if s["featured"]]
    preheader = ("This week: " + "; ".join(leads))[:220] if leads else "This week's research from arXiv."
    body = "".join(_section(s) for s in sections)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light">
<title>The Rinfo · Weekly Edition · {e(date_line)}</title></head>
<body style="margin:0;padding:0;background:{PAGE};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all;">
 {e(preheader)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAGE};">
<tr><td align="center" style="padding:24px 8px;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="max-width:{PAPER_W}px;width:100%;background:{PAPER};border:1px solid {HAIR};word-break:break-word;overflow-wrap:anywhere;">

  <!-- masthead -->
  <tr><td style="padding:16px {PAD} 0;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td align="left">{_caps(vol, INK, 9.5)}</td>
    <td align="right">{_caps(date_line, INK, 9.5)}</td>
   </tr></table>
   {_rule(1, INK, "8px 0 0")}
   <div style="padding:18px 0 6px;text-align:center;font:58px/1.02 {SERIF};
    font-weight:700;letter-spacing:-.01em;color:{INK};">The Rinfo</div>
   <div style="padding:0 0 14px;text-align:center;font:16px {SERIF};font-style:italic;color:{INK_2};">
    Research, in brief &middot; the weekly review of new preprints from arXiv</div>
   {_double_rule()}
   <div style="padding:7px 0;text-align:center;line-height:1.7;">
    {_caps(f"Weekly edition · {meta['week_range']} · {meta['scanned']} preprints read · "
           f"{meta['picked']} selected", INK, 9.5)}</div>
   {_rule(1, INK)}
   <div style="padding:10px 0 0;">{_caps("Inside this edition", MUTED, 9.5)}</div>
  </td></tr>
  {_index(sections)}

  {body}

  <!-- colophon -->
  <tr><td style="padding:34px {PAD} 30px;">
   {_double_rule("0 0 14px")}
   <div style="text-align:center;margin-bottom:10px;">{_caps("Colophon", INK, 10)}</div>
   {_p("The Rinfo is compiled automatically each Sunday from the arXiv preprint server. "
       "Reports are written by a language model from each paper&rsquo;s own text and have not been "
       "reviewed by a human editor; they may contain errors. Preprints are not peer-reviewed. "
       "Consult the original paper before citing any claim. Links under &ldquo;Also online&rdquo; and "
       "&ldquo;Elsewhere in the journals&rdquo; are supplied by web search and do not imply endorsement.",
       12.5, MUTED, "0 0 10px", "text-align:center;font-style:italic;")}
   {_app_links()}
   <div style="text-align:center;">{_caps(f"The Rinfo · {vol}", MUTED, 9)}</div>
  </td></tr>
 </table>
</td></tr></table>
</body></html>"""


def build_text(sections: list[dict], meta: dict) -> str:
    """Plain-text edition for clients that don't render HTML."""
    vol, date_line = _edition(meta)
    out = ["THE RINFO: WEEKLY EDITION",
           "Research, in brief: the weekly review of new preprints from arXiv",
           f"{vol.upper()} | {date_line} | {meta['week_range']}",
           f"{meta['scanned']} preprints read, {meta['picked']} selected", "=" * 64, ""]
    for s in sections:
        d = s["domain"]
        name = arxiv_categories.NAMES.get(d["key"], d["title"])
        out += [f"{name.upper()} (arXiv {d['key']})", "-" * 64, f"Coverage: {d['focus']}."]
        if s.get("overview"):
            out += ["", "THE WEEK IN BRIEF", s["overview"]]
        for i, p in enumerate(s["featured"]):
            ins = p.get("insight") or {}
            out += ["", ("LEAD STORY: " if i == 0 else "REPORT: ") + p["title"],
                    ins.get("tldr", ""),
                    f"By {byline(p.get('authors', []))} | Submitted {long_date(p.get('published', ''))} | arXiv:{p['id']}",
                    "", f"The problem. {ins.get('problem', '')}", f"The approach. {ins.get('approach', '')}",
                    "Key findings:"]
            out += [f"  - {f}" for f in ins.get("key_findings", [])]
            out += [f"Limitations. {ins.get('limitations', '')}",
                    f"Why it matters. {ins.get('why_it_matters', '')}",
                    f"Abstract: {p['abs_url']}", f"PDF: {p['pdf_url']}"]
            if chat_url(p["id"]):
                out.append(f"Discuss this paper: {chat_url(p['id'])}")
            out += [f"Also online: {l['title']} <{l['url']}>" for l in p.get("links") or []]
        if s["more"]:
            out += ["", f"IN BRIEF: MORE FROM {d['key']}"]
            out += [f"  - {p['title']} <{p['abs_url']}>" for p in s["more"]]
        if s.get("beyond"):
            out += ["", "ELSEWHERE IN THE JOURNALS"]
            out += [f"  - {r['title']} <{r['url']}>" for r in s["beyond"]]
        out += ["", "=" * 64, ""]
    out.append("Reports are written by a language model from each paper's own text and may contain errors. "
               "Preprints are not peer-reviewed; consult the original paper before citing.")
    if config.SITE_URL:
        out += ["", f"Read online or download the PDF: {config.site_url()}",
                f"Unsubscribe: {config.site_url('subscribe', action='unsubscribe')}"]
    return "\n".join(out)


# --- daily brief ----------------------------------------------------------------------------------
BRIEF_W = 680   # a single readable column: the brief is a quick morning read


def _brief_item(i: int, p: dict) -> str:
    links = [f'<a href="{e(p["abs_url"])}" style="color:{INK};">Abstract</a>',
             f'<a href="{e(p["pdf_url"])}" style="color:{INK};">PDF</a>']
    if chat_url(p["id"]):
        links.append(f'<a href="{e(chat_url(p["id"]))}" style="color:{INK};">Discuss</a>')
    cross = " · cross-listed" if p.get("announce_type") == "cross" else ""
    return f"""
<tr><td style="padding:14px 0;border-bottom:1px solid {HAIR};">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
  <td valign="top" width="34" style="font:700 22px/1 {SERIF};color:{RED};padding-top:2px;">{i}</td>
  <td valign="top">
   <div style="font:700 18px/1.3 {SERIF};color:{INK};">
    <a href="{e(chat_url(p['id']) or p['abs_url'])}" style="color:{INK};text-decoration:none;">{e(p['title'])}</a></div>
   <div style="margin-top:6px;font:15px/1.55 {SERIF};color:{INK_2};">{e(p.get('summary', ''))}</div>
   <div style="margin-top:6px;font:12px/1.5 {SANS};color:{MUTED};">
    {e(byline(p.get('authors', []), 2))} · {e(", ".join(p.get('categories', [])[:3]))}{cross}
    &nbsp;·&nbsp; {" &nbsp;·&nbsp; ".join(links)}</div>
  </td></tr></table>
</td></tr>"""


def _brief_words(meta: dict) -> dict:
    """Wording for the daily brief, or for Saturday's Week in Review (meta['kind'] == 'review')."""
    if meta.get("kind") == "review":
        days = len(meta.get("covered", []))
        return {"label": "Week in review", "title": "Week in Review", "when": "this week", "lead": "This week",
                "tagline": "the week&rsquo;s best new preprints from arXiv",
                "stats": f"the best from {days} daily brief{'s' if days != 1 else ''} · "
                         f"{meta['total']} announcements this week"}
    count = sum(len(s["papers"]) for s in meta.get("sections", []))
    return {"label": "Daily brief", "title": "Daily Brief", "when": "today", "lead": "Today",
            "tagline": "the day&rsquo;s new preprints from arXiv",
            "stats": f"{count} selected from {meta['total']} new announcements"}


def _brief_section(s: dict, when: str = "today") -> str:
    d = s["domain"]
    name = arxiv_categories.NAMES.get(d["key"], d["title"])
    if not s["papers"]:
        body = _p(f"No new preprints matched this section {when}.", 14, MUTED, "8px 0 0", "font-style:italic;")
        items = ""
    else:
        body = _p(e(s.get("lede", "")), 15, INK_2, "8px 0 4px", "font-style:italic;") if s.get("lede") else ""
        items = ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
                 + "".join(_brief_item(i, p) for i, p in enumerate(s["papers"], 1)) + "</table>")
    return f"""
<tr><td style="padding:22px {PAD} 4px;">
 {_rule(3, INK, "0 0 10px")}
 <div>{_caps(f"arXiv {d['key']}", RED, 10)}</div>
 <div style="margin-top:2px;font:700 26px/1.15 {SERIF};color:{INK};">{e(name)}</div>
 {body}{items}
</td></tr>"""


def build_brief_html(sections: list[dict], meta: dict) -> str:
    """The daily brief email (or Saturday's Week in Review). sections: [{domain, lede, papers: [... with
    'summary']}]; meta: issued (datetime), total (announcements in these categories), kind, covered."""
    issued = meta["issued"]
    date_line = issued.strftime("%A, %-d %B %Y")
    w = _brief_words({**meta, "sections": sections})
    leads = [s["papers"][0]["title"] for s in sections if s["papers"]]
    preheader = (f"{w['lead']}: " + "; ".join(leads))[:220] if leads else "New research from arXiv."
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light">
<title>The Rinfo · {w['title']} · {e(date_line)}</title></head>
<body style="margin:0;padding:0;background:{PAGE};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all;">
 {e(preheader)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAGE};">
<tr><td align="center" style="padding:20px 8px;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="max-width:{BRIEF_W}px;width:100%;background:{PAPER};border:1px solid {HAIR};word-break:break-word;overflow-wrap:anywhere;">
  <tr><td style="padding:16px {PAD} 0;text-align:center;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td align="left">{_caps(w["label"], RED, 9.5)}</td>
    <td align="right">{_caps(date_line, INK, 9.5)}</td>
   </tr></table>
   {_rule(1, INK, "8px 0 0")}
   <div style="padding:14px 0 4px;font:40px/1.05 {SERIF};font-weight:700;letter-spacing:-.01em;color:{INK};">
    The Rinfo</div>
   <div style="padding:0 0 12px;font:15px {SERIF};font-style:italic;color:{INK_2};">
    Research, in brief &middot; {w["tagline"]}</div>
   {_double_rule()}
   <div style="padding:7px 0;line-height:1.7;">
    {_caps(w["stats"], INK, 9.5)}</div>
   {_rule(1, INK)}
  </td></tr>
  {"".join(_brief_section(s, w["when"]) for s in sections)}
  <tr><td style="padding:26px {PAD} 26px;">
   {_double_rule("0 0 12px")}
   {_p("Summaries are written by a language model from each paper&rsquo;s abstract and may contain errors. "
       "Preprints are not peer-reviewed. The full weekly edition, with in-depth reports, arrives on Sundays.",
       12.5, MUTED, "0 0 10px", "text-align:center;font-style:italic;")}
   {_app_links("brief", "Read online")}
  </td></tr>
 </table>
</td></tr></table>
</body></html>"""
    return _minify(html)


def build_brief_text(sections: list[dict], meta: dict) -> str:
    issued = meta["issued"]
    w = _brief_words({**meta, "sections": sections})
    out = [f"THE RINFO: {w['title'].upper()}", issued.strftime("%A, %-d %B %Y"), w["stats"], "=" * 64]
    for s in sections:
        d = s["domain"]
        out += ["", f"{arxiv_categories.NAMES.get(d['key'], d['title']).upper()} (arXiv {d['key']})", "-" * 64]
        if not s["papers"]:
            out.append(f"No new preprints matched this section {w['when']}.")
            continue
        if s.get("lede"):
            out += [s["lede"], ""]
        for i, p in enumerate(s["papers"], 1):
            out += [f"{i}. {p['title']}", f"   {p.get('summary', '')}",
                    f"   {byline(p.get('authors', []), 2)} | {p['abs_url']}"]
            if chat_url(p["id"]):
                out.append(f"   Discuss: {chat_url(p['id'])}")
    out += ["", "Summaries are written by a language model from each paper's abstract and may contain errors."]
    if config.SITE_URL:
        out += [f"Read online: {config.site_url('brief')}",
                f"Unsubscribe or change what you get: {config.site_url('subscribe', action='unsubscribe')}"]
    return "\n".join(out)
