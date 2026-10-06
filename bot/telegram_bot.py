"""Mizan Telegram bot (SPEC §10, AMENDMENT 12), webhook mode, same process as the API.

- Reads `message.text or message.caption` (forwarded media carry their text in the caption).
- Replies "⏳ جارٍ التحقق..." at once, runs the orchestrator, then edits that message.
- parse_mode=HTML: every user- or source-derived string is escaped (<, >, &).
- One line per claim (icon + label, short snippet, source); results longer than 4,096 characters are split on
  card boundaries, never mid-line.
- Buttons: ready reply (sent as a separate plain message), details (web result page /r/{check_id}), report.
- /start explains usage in Arabic, English and Urdu and states it is not a fatwa service.
- 10 messages / minute per user; user ids are kept only as a salted hash.
"""

from __future__ import annotations

import hashlib
import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.core import messages as M
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.ratelimit import KeyedLimiter
from app.models.result import CheckResult, ClaimResult

log = get_logger(__name__)

MAX_LEN = 4096
SNIPPET = 70
user_limiter = KeyedLimiter(10, 60.0)

ICONS = {"verified": "✓", "misquoted": "⚠", "not_established": "✗", "disputed": "⚖", "not_found": "?",
         "needs_review": "?"}
LABELS = {
    "ar": {"verified": "موثّق", "misquoted": "منقول بخطأ", "not_established": "لا يثبت", "disputed": "اختلف المحدثون",
           "not_found": "لم يُعثر عليه", "needs_review": "يحتاج مراجعة مختص"},
    "en": {"verified": "Verified", "misquoted": "Misquoted", "not_established": "Not established",
           "disputed": "Scholars differ", "not_found": "Not found", "needs_review": "Needs specialist review"},
    "ur": {"verified": "مستند", "misquoted": "غلط نقل", "not_established": "ثابت نہیں", "disputed": "محدثین میں اختلاف",
           "not_found": "نہیں ملا", "needs_review": "ماہر کی رائے درکار"},
}
UNAVAILABLE = {"ar": "المصدر لم يستجب، أعد المحاولة", "en": "The source did not respond; try again",
               "ur": "ذریعے نے جواب نہیں دیا، دوبارہ کوشش کریں"}
BUTTONS = {"ar": ("الرد الجاهز", "التفاصيل", "إبلاغ"), "en": ("Ready reply", "Details", "Report"),
           "ur": ("تیار جواب", "تفصیلات", "رپورٹ")}
START = (
    "مرحبًا بك في ميزان. أعد توجيه أي رسالة فيها آية أو حديث، وسأتحقق من نصها ومصدرها من المصادر المعتمدة.\n"
    "ميزان أداة للتحقق من المصادر وليست جهة فتوى.\n\n"
    "Welcome to Mizan. Forward any message that quotes a verse or a hadith and I will check its wording and source "
    "against approved sources. Mizan is a source-verification tool, not a fatwa service.\n\n"
    "میزان میں خوش آمدید۔ کوئی بھی پیغام جس میں آیت یا حدیث ہو، آگے بھیجیں، میں معتبر ذرائع سے اس کے الفاظ اور حوالے کی "
    "جانچ کروں گا۔ میزان ذرائع کی جانچ کا آلہ ہے، فتویٰ کی سروس نہیں۔"
)
WAIT = "⏳ جارٍ التحقق..."
RATE_LIMITED = "⏳ Too many messages, please wait a minute. / الرجاء الانتظار دقيقة."


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=False)


def user_key(user_id: int) -> str:
    salt = get_settings().telegram_webhook_secret or "mizan"
    return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:24]


def _source(c: ClaimResult) -> str:
    e = c.evidence
    if e.locations:
        loc = e.locations[0]
        return f"{loc.surah_name_ar} {loc.surah}:{loc.ayah}"
    if e.gradings:
        g = e.gradings[0]
        return f"{g.book} - {g.grade_text}".strip(" -")
    return ""


def card(c: ClaimResult, lang: str) -> str:
    labels = LABELS.get(lang, LABELS["ar"])
    snippet = c.span if len(c.span) <= SNIPPET else c.span[:SNIPPET].rsplit(" ", 1)[0] + "…"
    line = f"{ICONS[c.verdict]} <b>{esc(labels[c.verdict])}</b>: «{esc(snippet)}»"
    if c.source_status == "source_unavailable" and c.verdict == "not_found":
        line += f"\n    {esc(UNAVAILABLE.get(lang, UNAVAILABLE['ar']))}"
    src = _source(c)
    if src:
        line += f"\n    {esc(src)}"
    return line


def format_result(res: CheckResult) -> list[str]:
    """Cards joined into messages of at most MAX_LEN characters, split only between cards."""
    lang = res.lang if res.lang in LABELS else "ar"
    parts: list[str] = []
    if res.message:
        parts.append(esc(res.message))
    if res.referral:
        parts.append("ℹ️ " + esc(res.referral.text))
    parts += [card(c, lang) for c in res.claims]
    parts.append(f"<i>{esc(res.disclaimer)}</i>")
    return split_cards(parts)


def split_cards(parts: list[str], limit: int = MAX_LEN) -> list[str]:
    chunks: list[str] = []
    cur = ""
    for p in parts:
        if len(p) > limit:  # a single oversized card: split on line boundaries
            for line in p.split("\n"):
                piece = line[:limit]
                if cur and len(cur) + 1 + len(piece) > limit:
                    chunks.append(cur)
                    cur = ""
                cur = f"{cur}\n{piece}" if cur else piece
            continue
        sep = "\n\n" if cur else ""
        if len(cur) + len(sep) + len(p) > limit:
            chunks.append(cur)
            cur = p
        else:
            cur += sep + p
    if cur:
        chunks.append(cur)
    return chunks


def keyboard(res: CheckResult) -> InlineKeyboardMarkup | None:
    lang = res.lang if res.lang in BUTTONS else "ar"
    reply_t, details_t, report_t = BUTTONS[lang]
    row = []
    if res.reply_available:
        row.append(InlineKeyboardButton(reply_t, callback_data=f"r:{res.check_id}"))
    base = get_settings().public_web_url.rstrip("/")
    if base:
        row.append(InlineKeyboardButton(details_t, url=f"{base}/r/{res.check_id}"))
    if res.claims:
        row.append(InlineKeyboardButton(report_t, callback_data=f"f:{res.check_id}"))
    return InlineKeyboardMarkup([row]) if row else None


# --------------------------------------------------------------------------- handlers


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(START)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.pipeline import orchestrator

    msg = update.effective_message
    if msg is None:
        return
    text = msg.text or msg.caption
    if not text:
        return
    uid = update.effective_user.id if update.effective_user else 0
    if user_limiter.hit(user_key(uid)) > 0:
        await msg.reply_text(RATE_LIMITED)
        return
    waiting = await msg.reply_text(WAIT)
    try:
        res = await orchestrator.run_check(text[: get_settings().max_input_chars], "telegram")
    except orchestrator.InputTooLong:
        await waiting.edit_text("الرسالة أطول من 4000 حرف. / Message longer than 4,000 characters.")
        return
    except Exception as e:  # noqa: BLE001
        log.warning("bot_check_failed", extra={"error": type(e).__name__})
        await waiting.edit_text("تعذّر التحقق الآن، أعد المحاولة. / Could not check now, please retry.")
        return
    chunks = format_result(res)
    kb = keyboard(res)
    await waiting.edit_text(chunks[0], parse_mode=ParseMode.HTML, reply_markup=kb if len(chunks) == 1 else None,
                            disable_web_page_preview=True)
    for k, chunk in enumerate(chunks[1:], start=2):
        await msg.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
                             reply_markup=kb if k == len(chunks) else None)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.pipeline import orchestrator
    from app.pipeline.reply import make_reply

    q = update.callback_query
    if q is None or not q.data:
        return
    kind, _, check_id = q.data.partition(":")
    res = await orchestrator.load_result(check_id)
    if res is None:
        await q.answer("انتهت صلاحية النتيجة (24 ساعة). / Result expired (24 h).", show_alert=True)
        return
    if kind == "r":
        await q.answer()
        text, err = await make_reply(res)
        if q.message:
            await q.message.reply_text(text or "تعذّر إنشاء الرد. / Could not build the reply.")  # plain, easy to copy
    elif kind == "f":
        from app.db import queries

        try:
            await queries.insert_feedback(check_id, 0, "other", "telegram report")
        except Exception:  # noqa: BLE001
            pass
        await q.answer("شكرًا، وصل البلاغ. / Thanks, report received.")


def build_application() -> Application | None:
    token = get_settings().telegram_bot_token
    if not token:
        return None
    app = Application.builder().token(token).updater(None).build()
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, on_message))
    return app
