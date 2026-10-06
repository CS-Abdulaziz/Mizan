"""Orchestrator (SPEC §7.7, §8.3): intake -> extract -> per-claim match / retrieve / verify / decide in parallel
-> assemble -> store 24 h -> metrics -> return. Never logs message text.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from langdetect import DetectorFactory, LangDetectException, detect

from app.core import messages as M
from app.core.cache import TTLCache
from app.core.config import get_settings
from app.core.logging import check_id_var, get_logger, stage_var
from app.llm.client import LLMError, LLMUsage
from app.models import result as R
from app.pipeline import decide, grades, hadith_retrieve, quran_match, verify
from app.pipeline.extract import ExtractedClaim, extract, is_arabic, script_lang
from app.pipeline.normalize import normalize_ar
from app.sources.quranenc import aya_url

log = get_logger(__name__)
DetectorFactory.seed = 0

_cache: TTLCache[R.CheckResult] = TTLCache(256, 24 * 3600)
_by_id: TTLCache[R.CheckResult] = TTLCache(1024, 24 * 3600)
_pending: set[asyncio.Task] = set()
_metrics: TTLCache[dict] = TTLCache(2048, 24 * 3600)  # per-check telemetry for the bench (no text)


VERSE_LIKE_RAW = 90.0  # D-23: an Arabic quote this close to a verse never falls through to the hadith path


class InputTooLong(Exception):
    pass


class ServiceUnavailable(Exception):
    pass


@dataclass
class ClaimTrace:
    usage: LLMUsage = field(default_factory=LLMUsage)
    embed_tokens: int = 0


# --------------------------------------------------------------------------- helpers


def message_lang(text: str, hint: str | None) -> str:
    if hint in ("ar", "en", "ur"):
        return hint
    sl = script_lang(text)
    if sl in ("ar", "ur"):
        return sl
    try:
        code = detect(text)
    except LangDetectException:
        return "en"
    return code if code in ("ar", "en", "ur") else "en"


def _ui_lang(lang: str) -> str:
    return lang if lang in ("ar", "en", "ur") else "en"


def _tr_lang(lang: str) -> str | None:
    """Language of the approved translation to show (None for Arabic messages)."""
    return lang if lang in ("en", "ur") else None


def verse_location(v: quran_match.Verse, lang: str) -> R.Location:
    s = get_settings()
    key = s.quranenc_key_ur if lang == "ur" else s.quranenc_key_en
    url = aya_url(key, v.surah, v.ayah).replace("/en/browse/", f"/{_ui_lang(lang)}/browse/")
    return R.Location(surah=v.surah, ayah=v.ayah, surah_name_ar=v.surah_name_ar, surah_name_en=v.surah_name_en,
                      url=url)


def verse_id(index: quran_match.QuranIndex, verses: tuple[int, ...]) -> str:
    a, b = index.verses[verses[0]], index.verses[verses[-1]]
    return f"quran:{a.surah}:{a.ayah}" + (f"-{b.ayah}" if len(verses) > 1 else "")


def verse_translation(verses: tuple[int, ...], lang: str) -> str | None:
    ti = quran_match.get_translations()
    tl = _tr_lang(lang)
    if ti is None or tl is None or tl not in ti.texts:
        return None
    return " ".join(ti.texts[tl][vi] for vi in verses if ti.texts[tl][vi]) or None


def verse_evidence(index: quran_match.QuranIndex, locations: list[tuple[int, ...]], lang: str,
                   best: quran_match.Candidate | None) -> R.Evidence:
    locs = [verse_location(index.verses[vi], lang) for loc in locations for vi in loc]
    first = locations[0]
    text = quran_match.uthmani_span(index, best) if best and best.verses == first else " ".join(
        index.verses[vi].uthmani for vi in first)
    return R.Evidence(source="quran", text_arabic=text, translation=verse_translation(first, lang),
                      locations=locs, url=locs[0].url if locs else None)


def _ops(c: quran_match.Candidate | None) -> list[R.DiffOp]:
    return [R.DiffOp(op=o.op, quoted=o.quoted, source=o.source) for o in (c.ops if c else [])]


def _base(i: int, c: ExtractedClaim, msg_lang: str) -> dict:
    return {"index": i, "type": c.type, "span": c.span, "span_start": c.span_start, "span_end": c.span_end,
            "lang": c.lang or msg_lang}


# --------------------------------------------------------------------------- verse decisions


async def _verse_verify(span: str, lang: str, index: quran_match.QuranIndex, spans: list[tuple[int, ...]],
                        trace: ClaimTrace) -> tuple[verify.VerifyResult, dict[str, tuple[int, ...]]]:
    by_id = {verse_id(index, vs): vs for vs in spans}
    cands = [verify.VerifyCandidate(vid, quran_match.candidate_text_clean(index, quran_match.Candidate(
        vs, 0, 0, "imlaei", False, [], 0, 0)), verse_translation(vs, lang)) for vid, vs in by_id.items()]
    res = await verify.verify(span, lang, "quran", cands)
    trace.usage = trace.usage + res.usage
    return res, by_id


async def decide_quran(i: int, c: ExtractedClaim, msg_lang: str, trace: ClaimTrace) -> R.ClaimResult | None:
    """Verse claim (or verse match for another type). None = no verse match (caller tries hadiths)."""
    index = quran_match.get_index()
    if index is None:
        raise ServiceUnavailable("Mushaf index not loaded")
    base = _base(i, c, msg_lang)
    lang = base["lang"]
    if is_arabic(c.span):
        vm = await asyncio.to_thread(quran_match.match_arabic, c.span, c.claimed_source, index)
        if vm.status == "too_short":
            return R.ClaimResult(**base, verdict="not_found", notes=["too_short"])
        if vm.status in ("verified", "attribution"):
            ev = verse_evidence(index, vm.locations, lang, vm.best)
            notes = ["multiple_locations"] if len(vm.locations) > 1 else []
            if vm.status == "attribution":
                cited = f"{vm.cited[0]}:{vm.cited[1]}" if vm.cited and vm.cited[1] else str(vm.cited[0] if vm.cited else "")
                return R.ClaimResult(**base, verdict="misquoted", relation="exact", confidence=1.0, evidence=ev,
                                     diff=R.Diff(kind="attribution", details=f"cited {cited}; found at "
                                                 + ", ".join(f"{x.surah}:{x.ayah}" for x in ev.locations)),
                                     notes=notes)
            return R.ClaimResult(**base, verdict="verified", relation="exact", confidence=1.0, evidence=ev, notes=notes)
        if vm.status in ("misquoted_candidate", "needs_verifier"):
            spans = [cd.verses for cd in vm.candidates[:3]]
            res, by_id = await _verse_verify(c.span, lang, index, spans, trace)
            if res.matched:
                matched = [by_id[x] for x in res.match_ids]
                best = vm.best if vm.best and vm.best.verses in matched else None
                ev = verse_evidence(index, matched, lang, best)
                # D-23: the verifier only confirms WHICH verse it is. When the deterministic word diff found
                # changed / missing / added words, the verdict is misquoted whatever relation the model says
                # (deterministic before LLM; a missed spelling variant errs towards misquoted, never verified).
                if (vm.status == "misquoted_candidate" and best is not None and best.ops) or res.relation == "altered":
                    return R.ClaimResult(**base, verdict="misquoted", relation="altered", confidence=res.confidence,
                                         evidence=ev, diff=R.Diff(kind="wording", ops=_ops(best),
                                                                  details=res.altered_details))
                return _with_cited_check(R.ClaimResult(**base, verdict="verified", relation=res.relation,
                                                       confidence=res.confidence, evidence=ev), vm.cited, index, matched)
            if vm.best is not None and vm.best.raw >= VERSE_LIKE_RAW:
                # clearly verse-like text the verifier would not confirm: abstain rather than call it a hadith
                return R.ClaimResult(**base, verdict="not_found")
        return None
    # non-Arabic quote (B12)
    cands = await quran_match.match_translation(c.span, lang, c.ar_queries, index)
    if not cands:
        return None
    res, by_id = await _verse_verify(c.span, lang, index, [cd.verses for cd in cands], trace)
    if not res.matched:
        return None
    matched = [by_id[x] for x in res.match_ids]
    ev = verse_evidence(index, matched, lang, None)
    from app.pipeline import surah_parse

    cited = surah_parse.parse(c.claimed_source)
    if res.relation == "altered":
        return R.ClaimResult(**base, verdict="misquoted", relation="altered", confidence=res.confidence, evidence=ev,
                             diff=R.Diff(kind="wording", details=res.altered_details))
    return _with_cited_check(R.ClaimResult(**base, verdict="verified", relation=res.relation,
                                           confidence=res.confidence, evidence=ev), cited, index, matched)


def _with_cited_check(cr: R.ClaimResult, cited, index, matched: list[tuple[int, ...]]) -> R.ClaimResult:
    if cited and not any(quran_match.cited_matches(cited, loc, index) for loc in matched):
        cr.verdict = "misquoted"
        cr.diff = R.Diff(kind="attribution", details="cited location differs; found at "
                         + ", ".join(f"{x.surah}:{x.ayah}" for x in cr.evidence.locations))
    return cr


# --------------------------------------------------------------------------- hadith decisions


async def decide_hadith(i: int, c: ExtractedClaim, msg_lang: str, trace: ClaimTrace) -> R.ClaimResult:
    base = _base(i, c, msg_lang)
    lang = base["lang"]
    ret = await hadith_retrieve.retrieve(c.span, lang, c.ar_queries)
    trace.embed_tokens += ret.embed_tokens
    if not ret.candidates:
        verdict, status = decide.unmatched_verdict(ret.source_status)
        return R.ClaimResult(**base, verdict=verdict, source_status=status)
    by_id = {h.id: h for h in ret.candidates}
    vcands = [verify.VerifyCandidate(h.id, h.text_ar, h.translation) for h in ret.candidates]
    res = await verify.verify(c.span, lang, "hadith", vcands)
    trace.usage = trace.usage + res.usage
    if not res.matched:
        verdict, status = decide.unmatched_verdict(ret.source_status)
        return R.ClaimResult(**base, verdict=verdict, source_status=status)

    matched = [by_id[x] for x in res.match_ids]
    if not any(h.source == "hadeethenc" for h in matched):
        for h in list(matched):
            linked = hadith_retrieve.hadeethenc_for_matn(h.text_clean, lang)
            if linked is not None and linked.id not in {x.id for x in matched}:
                matched.append(linked)
                break
    gradings: list[R.Grading] = []
    grade_in: list[decide.GradeIn] = []
    source_texts: list[str] = []
    for h in matched:
        if h.source == "hadeethenc":
            gradings.append(R.Grading(mohaddith="", book=h.attribution or "", page="", grade_text=h.grade or "",
                                      grade_class="accepted"))
            grade_in.append(decide.GradeIn("accepted", h.attribution or "", from_hadeethenc=True))
            source_texts.append(h.attribution or "")
        for m in h.members:
            cls = grades.classify(m.book, m.grade_text)
            gradings.append(R.Grading(mohaddith=m.mohaddith, book=m.book, page=m.page, grade_text=m.grade_text,
                                      grade_class=cls))
            grade_in.append(decide.GradeIn(cls, m.book))
            source_texts += [m.book, m.mohaddith]

    verdict = decide.hadith_verdict(grade_in) or "needs_review"
    verdict = decide.apply_relation(verdict, res.relation)
    he = next((h for h in matched if h.source == "hadeethenc"), None)
    shown = he or matched[0]
    ev = R.Evidence(source=shown.source, text_arabic=shown.text_ar,
                    translation=shown.translation if lang != "ar" else None, gradings=gradings, url=shown.url)
    notes: list = []
    diff = None
    if res.relation == "altered":
        diff = R.Diff(kind="wording", details=res.altered_details)
    if verdict == "verified" and decide.attribution_mismatch(c.claimed_source, source_texts):
        verdict = "misquoted"
        diff = R.Diff(kind="attribution", details="the cited book is not among the sources of this hadith")
    if verdict in ("verified", "misquoted") and decide.has_weak_chains(grade_in):
        notes.append("takhrij_has_weak_chains")
    alt = None
    if verdict == "not_established":  # §8.5: only for not_established, labelled as a different hadith
        from app.pipeline.alternative import find_alternative

        exclude = {int(h.id[3:]) for h in matched if h.source == "hadeethenc"}
        alt = await find_alternative(c.span, lang, exclude)
    return R.ClaimResult(**base, verdict=verdict, relation=res.relation, confidence=res.confidence, evidence=ev,
                         diff=diff, alternative=alt, notes=notes, source_status=ret.source_status)


# --------------------------------------------------------------------------- per-claim routing (D-4)


async def process_claim(i: int, c: ExtractedClaim, msg_lang: str, trace: ClaimTrace) -> R.ClaimResult:
    stage_var.set("claim")
    if c.type == "quran":
        verse = await decide_quran(i, c, msg_lang, trace)
        if verse is not None:
            return verse
        hadith = await decide_hadith(i, c, msg_lang, trace)  # people often attribute hadith to the Quran
        if hadith.verdict != "not_found":
            hadith.type = "quran"
            if hadith.verdict == "verified":
                hadith.verdict = "misquoted"
            hadith.diff = R.Diff(kind="wrong_type", details="This is a hadith, not a verse of the Quran.")
            return hadith
        return R.ClaimResult(**_base(i, c, msg_lang), verdict="not_found", source_status=hadith.source_status)

    # hadith / attributed saying: the deterministic verse matcher runs on every Arabic claim (D-4)
    if is_arabic(c.span):
        index = quran_match.get_index()
        if index is not None:
            vm = await asyncio.to_thread(quran_match.match_arabic, c.span, None, index)
            if vm.status == "verified":
                ev = verse_evidence(index, vm.locations, _base(i, c, msg_lang)["lang"], vm.best)
                return R.ClaimResult(**_base(i, c, msg_lang), verdict="misquoted", relation="exact", confidence=1.0,
                                     evidence=ev, diff=R.Diff(kind="wrong_type",
                                                              details="This is a verse of the Quran, not a hadith."))
    if c.type == "attributed_saying":
        verdict, notes = decide.out_of_scope_attribution()
        return R.ClaimResult(**_base(i, c, msg_lang), verdict=verdict, notes=notes)
    return await decide_hadith(i, c, msg_lang, trace)


# --------------------------------------------------------------------------- run_check


def _cache_key(text: str, channel: str) -> str:
    return hashlib.sha1((" ".join(text.split()) + "|" + channel).encode("utf-8")).hexdigest()


def metrics_for(check_id: str) -> dict | None:
    return _metrics.get(check_id)


def get_cached(check_id: str) -> R.CheckResult | None:
    return _by_id.get(check_id)


async def run_check(text: str, channel: str = "web", lang_hint: str | None = None) -> R.CheckResult:
    s = get_settings()
    if len(text) > s.max_input_chars:
        raise InputTooLong()
    key = _cache_key(text, channel)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    check_id = uuid.uuid4().hex
    check_id_var.set(check_id)
    t0 = time.perf_counter()
    lang = message_lang(text, lang_hint)

    stage_var.set("extract")
    ex = await extract(text)
    if not ex.llm_ok and not ex.claims:
        raise ServiceUnavailable("extraction unavailable")
    status = decide.message_status(ex.intent, ex.personal_ruling_request, len(ex.claims))

    traces = [ClaimTrace() for _ in ex.claims]
    outcomes = await asyncio.gather(
        *(process_claim(i, c, lang, traces[i]) for i, c in enumerate(ex.claims)), return_exceptions=True
    )
    claims: list[R.ClaimResult] = []
    for i, (c, out) in enumerate(zip(ex.claims, outcomes, strict=True)):
        if isinstance(out, BaseException):
            log.warning("claim_failed", extra={"claim_index": i, "error": type(out).__name__})
            claims.append(R.ClaimResult(**_base(i, c, lang), verdict="not_found", source_status="source_unavailable"))
        else:
            claims.append(out)

    ui = _ui_lang(lang)
    message = None
    if status == "no_claims":
        message = M.localized(M.NO_CLAIMS, ui)
    elif status == "evidence_request":
        message = M.localized(M.EVIDENCE_REQUEST, ui)
    referral = R.Referral(text=M.localized(M.REFERRAL, ui)) if status == "referral" else None
    expires = datetime.now(timezone.utc) + timedelta(hours=s.result_ttl_hours)
    result = R.CheckResult(
        check_id=check_id, status=status, lang=lang, referral=referral, message=message, claims=claims,
        disclaimer=M.localized(M.DISCLAIMER, ui), reply_available=bool(claims),
        expires_at=expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    usage = ex.usage
    for tr in traces:
        usage = usage + tr.usage
    latency_ms = int((time.perf_counter() - t0) * 1000)
    log.info("check_done", extra={"status": status, "n_claims": len(claims), "latency_ms": latency_ms,
                                  "verdicts": [c.verdict for c in claims], "providers": usage.providers})
    _cache.put(key, result)
    _by_id.put(check_id, result)
    _metrics.put(check_id, {"latency_ms": latency_ms, "tokens_in": usage.input_tokens,
                            "tokens_out": usage.output_tokens, "providers": usage.providers,
                            "embed_tokens": sum(t.embed_tokens for t in traces)})
    task = asyncio.create_task(_persist(result, expires, channel, latency_ms, usage,
                                        sum(t.embed_tokens for t in traces)))
    _pending.add(task)  # keep a reference until done; storage must not delay the response
    task.add_done_callback(_pending.discard)
    return result


async def _persist(result: R.CheckResult, expires: datetime, channel: str, latency_ms: int, usage: LLMUsage,
                   embed_tokens: int) -> None:
    from app.db import queries

    try:
        await queries.save_check_result(result.check_id, result.model_dump(mode="json"), expires)
        await queries.insert_check_metrics(
            check_id=result.check_id, channel=channel, lang=result.lang, n_claims=len(result.claims),
            status=result.status, latency_ms=latency_ms, llm_tokens_in=usage.input_tokens,
            llm_tokens_out=usage.output_tokens, embed_tokens=embed_tokens, llm_providers=usage.providers,
        )
    except Exception as e:  # noqa: BLE001 - storage failure must not fail the check
        log.warning("persist_failed", extra={"error": type(e).__name__})


async def load_result(check_id: str) -> R.CheckResult | None:
    cached = _by_id.get(check_id)
    if cached is not None:
        return cached
    from app.db import queries

    try:
        row = await queries.get_check_result(check_id)
    except Exception:  # noqa: BLE001
        return None
    return R.CheckResult.model_validate(row["result"]) if row else None


def normalize_for_cache(text: str) -> str:  # kept for tests / bench
    return normalize_ar(text)
