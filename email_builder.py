"""Builds the HTML digest (table layout, inline CSS) and its plain-text twin."""
from datetime import datetime
from html import escape
from urllib.parse import quote

import arxiv_categories
import config
from summarizer import NOT_STATED

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
TEXT = "#374151"
MUTED = "#6B7280"


def e(value) -> str:
    """Escape any dynamic text (and attribute values) for HTML."""
    return escape(str(value or ""), quote=True)


def chat_url(paper_id: str) -> str:
    """Deep link into the Streamlit chat app, or '' when CHAT_APP_URL is unset."""
    if not config.CHAT_APP_URL:
        return ""
    sep = "&" if "?" in config.CHAT_APP_URL else "?"
    return f"{config.CHAT_APP_URL.rstrip('/')}{sep}paper={quote(paper_id)}"


def authors_line(authors: list[str], limit: int = 4) -> str:
    return ", ".join(authors[:limit]) + (" et al." if len(authors) > limit else "")


def short_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y")
    except ValueError:
        return iso[:10]


# --- small HTML pieces -----------------------------------------------------------
def _button(label: str, href: str, bg: str, fg: str = "#FFFFFF", border: str | None = None) -> str:
    border = border or bg
    return (f'<a href="{e(href)}" target="_blank" style="display:inline-block;margin:0 6px 6px 0;'
            f'padding:8px 14px;background:{bg};color:{fg};border:1px solid {border};border-radius:6px;'
            f'font-family:{FONT};font-size:13px;font-weight:600;text-decoration:none;">{e(label)}</a>')


def _chip(text: str, bg: str = "#F3F4F6", fg: str = TEXT, href: str = "") -> str:
    style = (f"display:inline-block;margin:0 6px 6px 0;padding:3px 10px;background:{bg};color:{fg};"
             f"border-radius:999px;font-family:{FONT};font-size:12px;text-decoration:none;")
    if href:
        return f'<a href="{e(href)}" target="_blank" style="{style}">{e(text)}</a>'
    return f'<span style="{style}">{e(text)}</span>'


def _label(text: str, accent: str) -> str:
    return (f'<div style="margin:14px 0 4px;font-family:{FONT};font-size:11px;font-weight:700;'
            f'letter-spacing:.08em;text-transform:uppercase;color:{accent};">{e(text)}</div>')


def _para(text: str) -> str:
    color = MUTED if text == NOT_STATED else TEXT
    return (f'<div style="font-family:{FONT};font-size:14px;line-height:1.55;color:{color};">'
            f'{e(text)}</div>')


def _paper_card(p: dict, d: dict) -> str:
    ins = p.get("insight") or {}
    accent, tint = d["accent"], d["tint"]
    cat = p["category"]
    if cat in arxiv_categories.NAMES:
        cat = f"{cat} ({arxiv_categories.NAMES[cat]})"
    meta = " · ".join(x for x in [authors_line(p["authors"]), short_date(p["published"]), cat] if x)
    findings = "".join(f'<li style="margin:0 0 4px;">{e(f)}</li>' for f in ins.get("key_findings", []))
    tags = "".join(_chip("#" + t, tint, accent) for t in ins.get("tags", []))
    buttons = _button("Abstract", p["abs_url"], accent) + _button("PDF", p["pdf_url"], "#FFFFFF", accent, accent)
    if chat_url(p["id"]):
        buttons += _button("💬 Chat with this paper", chat_url(p["id"]), "#111827")
    links = p.get("links") or []
    code = ""
    if links:
        chips = "".join(_chip(f"{l['host']} · {l['title'][:48]}", "#F9FAFB", TEXT, l["url"]) for l in links)
        code = _label("Code & discussion", MUTED) + f"<div>{chips}</div>"
    note = ""
    if ins.get("source") == "abstract":
        note = (f'<div style="margin-top:8px;font-family:{FONT};font-size:12px;color:{MUTED};">'
                f'Auto-summary from the abstract (LLM unavailable).</div>')
    return f"""
<tr><td style="padding:0 0 18px;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:#FFFFFF;border:1px solid #E5E7EB;border-top:4px solid {accent};border-radius:10px;">
 <tr><td style="padding:20px 22px;">
  <a href="{e(p['abs_url'])}" target="_blank" style="font-family:{FONT};font-size:18px;line-height:1.35;
   font-weight:700;color:#111827;text-decoration:none;">{e(p['title'])}</a>
  <div style="margin:6px 0 14px;font-family:{FONT};font-size:12px;color:{MUTED};">{e(meta)}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
   <tr><td style="background:{tint};border-left:3px solid {accent};border-radius:6px;padding:12px 14px;
    font-family:{FONT};font-size:14px;line-height:1.55;color:#111827;">
    <strong style="color:{accent};">TL;DR</strong>&nbsp; {e(ins.get('tldr'))}</td></tr>
  </table>
  {_label('Problem', accent)}{_para(ins.get('problem'))}
  {_label('Approach', accent)}{_para(ins.get('approach'))}
  {_label('Key findings', accent)}
  <ul style="margin:0;padding-left:20px;font-family:{FONT};font-size:14px;line-height:1.55;color:{TEXT};">{findings}</ul>
  {_label('Limitations', accent)}{_para(ins.get('limitations'))}
  {_label('Why it matters', accent)}{_para(ins.get('why_it_matters'))}
  <div style="margin-top:14px;">{tags}</div>
  <div style="margin-top:8px;">{buttons}</div>
  {code}{note}
 </td></tr></table>
</td></tr>"""


def _link_list(title: str, items: list[str]) -> str:
    if not items:
        return ""
    return (f'<tr><td style="padding:4px 0 14px;">'
            f'<div style="font-family:{FONT};font-size:15px;font-weight:700;color:#111827;margin-bottom:8px;">'
            f'{e(title)}</div>{"".join(items)}</td></tr>')


def _more_item(p: dict, accent: str) -> str:
    meta = f"{authors_line(p['authors'], 2)} · {short_date(p['published'])}"
    return (f'<div style="margin:0 0 10px;padding-left:10px;border-left:2px solid {accent};">'
            f'<a href="{e(p["abs_url"])}" target="_blank" style="font-family:{FONT};font-size:14px;'
            f'color:#111827;text-decoration:none;font-weight:600;">{e(p["title"])}</a>'
            f'<div style="font-family:{FONT};font-size:12px;color:{MUTED};">{e(meta)}</div></div>')


def _web_item(r: dict, accent: str) -> str:
    return (f'<div style="margin:0 0 12px;">'
            f'<a href="{e(r["url"])}" target="_blank" style="font-family:{FONT};font-size:14px;'
            f'color:{accent};text-decoration:none;font-weight:600;">{e(r["title"])}</a>'
            f'<div style="font-family:{FONT};font-size:12px;color:{MUTED};">{e(r["host"])}</div>'
            f'<div style="font-family:{FONT};font-size:13px;line-height:1.5;color:{TEXT};">{e(r["snippet"])}</div>'
            f'</div>')


def _section(s: dict) -> str:
    d = s["domain"]
    cards = "".join(_paper_card(p, d) for p in s["featured"])
    more = _link_list(f"More in {d['key']} this week", [_more_item(p, d["accent"]) for p in s["more"]])
    cats = "".join(_chip(c, "#FFFFFF", d["accent"], f"https://arxiv.org/list/{c}/recent")
                   for c in d["categories"])
    beyond = _link_list("🌐 Beyond arXiv", [_web_item(r, d["accent"]) for r in s.get("beyond", [])])
    empty = "" if s["featured"] else _para("No new papers matched this week.")
    return f"""
<tr><td style="padding:28px 24px 8px;" >
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr><td style="background:{d['tint']};border-left:5px solid {d['accent']};border-radius:8px;padding:14px 16px;">
   <div style="font-family:{FONT};font-size:20px;font-weight:800;color:{d['accent']};">{e(d['emoji'])} {e(d['title'])}</div>
   <div style="margin-top:8px;">{cats}</div>
   <div style="font-family:{FONT};font-size:12px;color:{MUTED};">
    <strong>Topic filter:</strong> {e(d['focus'])}</div>
   <div style="margin-top:10px;font-family:{FONT};font-size:14px;line-height:1.55;font-style:italic;color:{TEXT};">
    {e(s.get('overview'))}</div>
  </td></tr>
  <tr><td style="height:16px;line-height:16px;font-size:0;">&nbsp;</td></tr>
  {cards}{empty}{more}{beyond}
 </table>
</td></tr>"""


# --- public API ---------------------------------------------------------------------
def build_html(sections: list[dict], meta: dict) -> str:
    """Full HTML email. meta: week_range, scanned, picked."""
    preheader = " · ".join(f"{s['domain']['emoji']} {s['featured'][0]['title']}"
                           for s in sections if s["featured"])[:200]
    pills = "".join(_chip(f"{s['domain']['emoji']} {s['domain']['key']}", "#1F2937", "#E5E7EB")
                    for s in sections)
    body = "".join(_section(s) for s in sections)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar · {e(meta['week_range'])}</title></head>
<body style="margin:0;padding:0;background:#F3F4F6;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all;">
 {e(preheader)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F3F4F6;">
<tr><td align="center" style="padding:24px 10px;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="max-width:640px;width:100%;background:#F9FAFB;border-radius:14px;overflow:hidden;">
  <tr><td style="background:#0F172A;padding:30px 24px;">
   <div style="font-family:{FONT};font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#94A3B8;">
    Weekly research digest</div>
   <div style="margin-top:6px;font-family:{FONT};font-size:28px;font-weight:800;color:#FFFFFF;">📡 Research Radar</div>
   <div style="margin-top:6px;font-family:{FONT};font-size:14px;color:#CBD5E1;">{e(meta['week_range'])}</div>
   <div style="margin-top:4px;font-family:{FONT};font-size:13px;color:#94A3B8;">
    Scanned {e(meta['scanned'])} papers, picked {e(meta['picked'])}</div>
   <div style="margin-top:14px;">{pills}</div>
  </td></tr>
  {body}
  <tr><td style="padding:22px 24px 30px;border-top:1px solid #E5E7EB;">
   <div style="font-family:{FONT};font-size:12px;line-height:1.6;color:{MUTED};">
    Summaries are generated by an LLM from the paper text and may contain mistakes.
    Always check the original paper before citing or relying on a claim.
    Web links come from Tavily search and are not endorsed.<br>Sent by Research Radar.</div>
  </td></tr>
 </table>
</td></tr></table>
</body></html>"""


def build_text(sections: list[dict], meta: dict) -> str:
    """Plain-text alternative for clients that don't render HTML."""
    out = ["RESEARCH RADAR", meta["week_range"],
           f"Scanned {meta['scanned']} papers, picked {meta['picked']}", ""]
    for s in sections:
        d = s["domain"]
        out += ["=" * 60, f"{d['emoji']} {d['title']}",
                f"arXiv categories: {', '.join(d['categories'])} | Topic filter: {d['focus']}",
                "=" * 60, s.get("overview", ""), ""]
        for p in s["featured"]:
            ins = p.get("insight") or {}
            out += [f"* {p['title']}", f"  {authors_line(p['authors'])} · {short_date(p['published'])}",
                    f"  TL;DR: {ins.get('tldr', '')}", f"  Problem: {ins.get('problem', '')}",
                    f"  Approach: {ins.get('approach', '')}", "  Key findings:"]
            out += [f"   - {f}" for f in ins.get("key_findings", [])]
            out += [f"  Limitations: {ins.get('limitations', '')}",
                    f"  Why it matters: {ins.get('why_it_matters', '')}",
                    f"  Abstract: {p['abs_url']}", f"  PDF: {p['pdf_url']}"]
            if chat_url(p["id"]):
                out.append(f"  Chat: {chat_url(p['id'])}")
            out += [f"  Link: {l['url']}" for l in p.get("links") or []]
            out.append("")
        if s["more"]:
            out.append(f"More in {d['key']} this week:")
            out += [f"  - {p['title']} <{p['abs_url']}>" for p in s["more"]]
            out.append("")
        if s.get("beyond"):
            out.append("Beyond arXiv:")
            out += [f"  - {r['title']} <{r['url']}>" for r in s["beyond"]]
            out.append("")
    out.append("Summaries are LLM-generated and may contain mistakes; check the original papers.")
    return "\n".join(out)
