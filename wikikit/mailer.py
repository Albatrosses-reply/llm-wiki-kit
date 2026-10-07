"""아침 메일: 묶음 → 저널 → 논문(⭐·최신순). Gmail SMTP(앱 비밀번호)로 보낸다.

각 논문의 '📥 위키 후보로' 버튼은 내 Gmail로 '<키워드> <hash>' 제목의 메일을 쓴다. 보내면 다음 확인 때 후보로 등록된다.
"""
from __future__ import annotations

import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from html import escape
from urllib.parse import quote

from . import config as C

log = logging.getLogger("wikikit")
MAILTO_BATCH_CAP = 30
NAVY = "#1a3d7c"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Apple SD Gothic Neo','Malgun Gothic',sans-serif"


def doi_url(doi: str) -> str:
    return "https://doi.org/" + quote(doi, safe="/:;()._-")


def grouped(papers: list, cfg: dict) -> list:
    """[(label, [(journal, abbrev, [papers])])]"""
    out = []
    for g, label in C.group_order(cfg):
        by_j: dict[tuple, list] = {}
        for p in papers:
            if p.group == g:
                by_j.setdefault((p.journal, p.abbrev), []).append(p)
        if by_j:
            out.append((label, [(j, a, sorted(ps, key=lambda p: (p.score or 0, p.pub_date or ""), reverse=True))
                                for (j, a), ps in by_j.items()]))
    return out


def wiki_line() -> str:
    try:
        d = json.loads(C.LAST_RUN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    parts = [f"새 위키 페이지 {len(d.get('new', []))}"]
    if d.get("redone"):
        parts.append(f"PDF로 다시 {len(d['redone'])}")
    if d.get("waiting"):
        parts.append(f"대기 {d['waiting']}")
    if d.get("failed"):
        parts.append(f"실패 {len(d['failed'])}")
    if d.get("pdf_needed"):
        parts.append(f"PDF 있으면 더 좋음 {d['pdf_needed']}")
    return f"위키 ({d.get('date', '')}): " + " · ".join(parts)


class Mailer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.sender = cfg.get("gmail", "")
        self.recipient = cfg.get("recipient") or self.sender
        self.password = C.secret("GMAIL_APP_PASSWORD")
        self.kw = cfg.get("star_keyword", "WIKI-STAR")

    @property
    def ready(self) -> bool:
        return bool(self.sender and self.password and self.recipient)

    def _message(self, subject: str, plain: str, html: str) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr(("LLM Wiki 논문 알림", self.sender), charset="utf-8")
        msg["To"] = self.recipient
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        return msg

    def deliver(self, msg) -> bool:
        if not self.ready:
            log.error("메일 설정 부족: settings.toml의 gmail과 .env의 GMAIL_APP_PASSWORD가 필요 (python wiki.py secrets)")
            return False
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as s:
                s.starttls()
                s.login(self.sender, self.password)
                s.send_message(msg, from_addr=self.sender, to_addrs=[self.recipient])
            log.info(f"메일 발송 → {self.recipient}")
            return True
        except smtplib.SMTPAuthenticationError:
            log.error("Gmail 로그인 실패: 앱 비밀번호(16자리)와 Gmail 주소를 확인하세요. 일반 비밀번호로는 안 됩니다.")
        except Exception as e:  # noqa: BLE001
            log.error(f"메일 발송 실패: {e}")
        return False

    def send_digest(self, papers: list, day: str) -> bool:
        subject = f"[논문 알림] {day} · {len(papers)}편" + (f" · ⭐ {sum(1 for p in papers if p.score)}" if any(p.score for p in papers) else "")
        return self.deliver(self._message(subject, self.render_plain(papers, day), self.render_html(papers, day)))

    def send_status(self, day: str, text: str) -> bool:
        html = (f'<div style="font-family:{FONT};max-width:680px;margin:0 auto;padding:20px;">'
                f'<h2 style="color:{NAVY};">논문 알림 {escape(day)}</h2>'
                + "".join(f"<p>{escape(x)}</p>" for x in text.split("\n") if x) + "</div>")
        return self.deliver(self._message(f"[논문 알림] {day} · 새 논문 없음", text, html))

    def send_test(self) -> bool:
        text = ("LLM Wiki 시험 메일입니다. 이 메일이 보이면 Gmail 설정이 끝난 것입니다.\n"
                "아래 버튼(또는 회신)으로 위키 후보를 고르는 방식도 이 주소로 동작합니다.")
        return self.deliver(self._message("[논문 알림] 시험 메일", text, f"<p>{escape(text)}</p>"))

    # ── 버튼 ──
    def _mailto(self, subject: str, body: str) -> str:
        return f"mailto:{self.sender}?subject={quote(subject)}&body={quote(body)}"

    def _star_button(self, h: str) -> str:
        href = escape(self._mailto(f"{self.kw} {h}", f"hash:{h}\n이 메일을 그대로 보내면 위키 후보로 등록됩니다."))
        return (f'<a href="{href}" style="display:inline-block;background:{NAVY};color:#fff;text-decoration:none;'
                f'font-size:11px;padding:3px 9px;border-radius:4px;margin-left:4px;white-space:nowrap;">📥 위키 후보로</a>')

    def _master(self, flat: list) -> str:
        capped = flat[:MAILTO_BATCH_CAP]
        lines = ["위키에 넣을 항목의 [ ] 를 [x] 로 바꾼 뒤 그대로 보내 주세요.", ""]
        lines += [f"- [ ] hash:{p.item_hash}  [{p.abbrev}] {p.title[:60]}" for p in capped]
        href = escape(self._mailto(f"{self.kw} BATCH", "\n".join(lines)))
        cap = f" (앞 {MAILTO_BATCH_CAP}편)" if len(flat) > MAILTO_BATCH_CAP else ""
        return (f'<div style="background:#fffbe6;border:1px solid #ffd54f;padding:10px 14px;border-radius:6px;margin:0 0 16px;'
                f'font-size:13px;line-height:1.5;"><b>📥 여러 편 한꺼번에 위키 후보로{cap}</b><br>'
                f'<span style="font-size:12px;color:#666;">버튼을 누르면 목록이 채워진 메일이 열립니다. 원하는 줄만 [x]로 바꿔 보내세요. '
                f'Obsidian의 inbox/alerts 파일에서 체크해도 됩니다.</span><br>'
                f'<a href="{href}" style="display:inline-block;margin-top:8px;background:#f9a825;color:#fff;text-decoration:none;'
                f'font-size:12px;padding:6px 14px;border-radius:4px;">📥 목록 메일 작성</a></div>')

    def _card(self, p) -> str:
        url = escape(doi_url(p.doi))
        badge = ('<span style="background:#fff3e0;color:#e65100;font-size:11px;padding:2px 6px;border-radius:4px;'
                 'margin-left:6px;">⭐ 관심</span>') if p.score else ""
        if p.kr_summary:
            body = (f'<div style="background:#fff8e1;padding:9px 11px;border-radius:6px;margin-top:6px;font-size:13px;'
                    f'line-height:1.55;color:#333;border-left:3px solid #f9a825;">{escape(p.kr_summary)}</div>')
        elif p.abstract:
            snip = p.abstract[:420] + ("…" if len(p.abstract) > 420 else "")
            body = f'<div style="font-size:12px;line-height:1.5;color:#555;margin-top:6px;">{escape(snip)}</div>'
        else:
            body = '<div style="font-size:12px;color:#999;margin-top:6px;">초록 미제공</div>'
        meta = " · ".join(x for x in (escape(p.authors_str), escape(p.pub_date or "")) if x)
        return (f'<div style="border-left:3px solid {NAVY};padding:8px 12px;margin:10px 0;">'
                f'<div style="font-size:14px;font-weight:600;line-height:1.4;"><a href="{url}" style="color:#1a1a1a;'
                f'text-decoration:none;">{escape(p.title)}</a>{badge}</div>'
                f'<div style="font-size:12px;color:#666;margin-top:4px;">{meta} · <a href="{url}" style="color:{NAVY};">DOI</a> '
                f'{self._star_button(p.item_hash)}</div>{body}</div>')

    def render_html(self, papers: list, day: str) -> str:
        groups = grouped(papers, self.cfg)
        flat = [p for _, js in groups for _, _, ps in js for p in ps]
        parts = ['<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
                 f'<body style="margin:0;background:#f5f6f8;"><div style="font-family:{FONT};max-width:720px;margin:0 auto;padding:20px;'
                 f'color:#1a1a1a;background:#fff;"><div style="background:{NAVY};color:#fff;padding:16px 20px;border-radius:8px;margin-bottom:18px;">'
                 f'<div style="font-size:20px;font-weight:700;">저널 신간</div><div style="font-size:13px;opacity:.9;margin-top:4px;">'
                 f'{escape(day)} · {len(papers)}편</div></div>']
        wl = wiki_line()
        if wl:
            parts.append(f'<div style="border:1px solid #c5d3ea;background:#f3f6fb;border-radius:6px;padding:8px 14px;margin-bottom:16px;'
                         f'font-size:13px;color:{NAVY};">📚 {escape(wl)}</div>')
        stars = [p for p in flat if p.score]
        if stars:
            items = "".join(f'<li><a href="{escape(doi_url(p.doi))}" style="color:{NAVY};text-decoration:none;">{escape(p.title)}</a> '
                            f'<span style="color:#888;font-size:12px;">{escape(p.abbrev)}</span></li>' for p in stars[:15])
            parts.append(f'<div style="border:1px solid #ffe0b2;background:#fff8f0;border-radius:6px;padding:10px 14px;margin-bottom:16px;">'
                         f'<b style="color:#e65100;font-size:13px;">⭐ 관심 키워드 논문 {len(stars)}편</b>'
                         f'<ul style="margin:6px 0 0;padding-left:18px;font-size:13px;line-height:1.45;">{items}</ul></div>')
        parts.append(self._master(flat))
        for label, journals in groups:
            n = sum(len(ps) for _, _, ps in journals)
            parts.append(f'<h2 style="font-size:16px;color:{NAVY};border-bottom:2px solid {NAVY};padding-bottom:4px;margin:26px 0 6px;">'
                         f'{escape(label)} <span style="font-weight:400;color:#666;">({n})</span></h2>')
            for jname, ab, ps in journals:
                parts.append(f'<h3 style="font-size:14px;color:#333;margin:16px 0 4px;">{escape(ab)} <span style="font-weight:400;'
                             f'color:#888;font-size:12px;">{escape(jname)} · {len(ps)}편</span></h3>')
                parts.extend(self._card(p) for p in ps)
        parts.append(f'<div style="font-size:11px;color:#888;line-height:1.7;margin-top:28px;padding-top:10px;border-top:1px solid #eee;">'
                     f'📥 버튼은 {escape(self.sender)} 로 메일을 씁니다. 보내면 30분 안에 Obsidian 보관소 <code>inbox/starred/</code>에 후보 노트가 생기고, '
                     f'다음 날 아침 자동 처리에서 위키 페이지가 만들어집니다. 같은 목록이 <code>inbox/alerts/{escape(day)}.md</code>에 체크박스로 있습니다.</div>'
                     '</div></body></html>')
        return "".join(parts)

    def render_plain(self, papers: list, day: str) -> str:
        out = [f"저널 신간 {day} · {len(papers)}편", ""]
        if wiki_line():
            out += [wiki_line(), ""]
        for label, journals in grouped(papers, self.cfg):
            out.append(f"## {label}")
            for jname, ab, ps in journals:
                out.append(f"### {ab} · {jname}")
                for p in ps:
                    out += [f"- {'⭐ ' if p.score else ''}{p.title}", f"  {p.authors_str} · {p.pub_date} · {doi_url(p.doi)}"]
                    if p.kr_summary or p.abstract:
                        out.append(f"  {p.kr_summary or p.abstract[:240]}")
                    out += [f'  위키 후보로: 제목 "{self.kw} {p.item_hash}" 메일을 {self.sender} 로', ""]
        return "\n".join(out)
