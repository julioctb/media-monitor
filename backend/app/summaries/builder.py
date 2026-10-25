"""Daily digest builder (T11 -> digest v2).

Pipeline, always run:

  1. day window in the settings timezone (zoneinfo) over mentions.published_at,
  2. deterministic facts via summaries.digest.build_digest_facts (events,
     personas, topics, rectora slice, redes counts, gaps),
  3. silent keywords become the PENDIENTES section,
  4. LLM narrative pass: the model ONLY fills headline / per-item
     summary+why_it_matters / rectora tone+watch, merged by
     digest.apply_narrative; any failure keeps the heuristic mode,
  5. digest.render_plain_text stores the sectioned plain text as
     content["plain_text"] for RAG and quick reading.

The structured content never depends on the LLM, which is also skipped for
empty days (nothing to summarize); mode stays ``heuristic`` then.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select

from app.enrich.llm import strip_code_fence

from app.ingest.events import similarity_with_suffix_variants, strip_outlet_suffix
from app.models import AgendaItem, DailySummary, FieldReport, Mention, queries
from app.models.settings import DEFAULT_OPENAI_BASE_URL
from app.settings_runtime import EffectiveSettings, resolve_effective_settings
from app.summaries.agenda_detect import normalize_title, parse_spanish_date
from app.summaries.digest import (
    CONFIDENCE_SCALE,
    DIGEST_SCHEMA_VERSION,
    apply_brief,
    apply_narrative,
    build_digest_facts,
    confidence_for,
    render_plain_text,
)
from app.summaries.digest_schema import BRIEF_BUCKETS, narrative_response_schema

log = logging.getLogger("summaries.builder")

#: Spanish month names for the heuristic headline.
MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

#: Silent keywords shown inside the heuristic headline.
MAX_KEYWORDS_NARRATIVE = 5

# Chat-completions transport constants, mirroring app.sentiment.api_analyzer.
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
TIMEOUT_S = 60.0  # digest narrative is a long prompt+completion; 20s timed out under load
ATTEMPTS = 2
BACKOFF_S = 0.5

SYSTEM_PROMPT = (
    "Eres editor de monitoreo de medios. Recibes los HECHOS verificados del "
    "día en JSON (noticias, rectora, redes, personas). Devuelve EXCLUSIVAMENTE "
    "un objeto JSON con: headline (1-3 oraciones que tejen el día; el tono "
    "de cada noticia via facts.noticias[i].tone — dedica énfasis explícito "
    "a las de tono negativo dominante: nómbralas y explica la razón de su "
    "tono según sus hechos; las positivas y neutras se subordinan), items "
    "[{index, summary, why_it_matters, confidence_note}] para las noticias "
    "que lo requieran: summary es el HECHO en 1 oración y why_it_matters el "
    "POR QUÉ IMPORTA en 1 oración; confidence_note justifica la confianza en"
    "<=6 palabras (ej. «fuente oficial directa») y es opcional; y seleccion: "
    "[{index, categoria, razon}] para el brief, eligiendo SOLO tarjetas ya "
    "existentes por su índice en noticias, con categoria decision (exige "
    "decisión o atención), riesgo (la lectura de tono negativo dominante), "
    "ruido o a_favor: la selección nunca introduce "
    "datos nuevos, solo referencia índices. Densidad editorial: marca "
    "mínimo tres decisiones cuando haya candidatas, y cada razon es una "
    "oración completa que explique la lectura editorial y su consecuencia, "
    "nunca una etiqueta de tres o cuatro palabras. El bloque dia_previo "
    "lista en compacto el día previo: úsalo para calibrar qué continúa y "
    "qué es ángulo nuevo; lo ya conocido se trata como continuidad. "
    "Además rectora {tone, watch, "
    "activity}: activity es el seguimiento narrativo de la persona focal, "
    "lista [{when, status, text, channel}] con cuándo/qué, estado y canal "
    "cuando aplique (omítela si no hay nada que vigilar). Incluye además "
    "agenda: lista [{when, status, title, source}] de eventos o citas futuras "
    "visibles en los datos (when y title literales, sin inventar fechas), y "
    "redes: {<fuente>: {note, cuentas}} donde note es la nota narrativa de la "
    "red y cuentas es la lista [{cuenta, nota}] con una entrada POR CUENTA "
    "rastreada con datos o hallazgos (estado, pendientes de verificación). "
    "En facebook la nota describe los hallazgos SIN nombrar páginas, grupos "
    "ni fuentes (el lector ya sabe cuáles se siguen) y sin bloque de "
    "cuentas. En TODAS las redes la nota es paráfrasis editorial: NUNCA "
    "citas textuales, sin emojis, sin URLs ni acortadores, sin menciones @; "
    "redacta el hecho con palabras propias. "
    "Nota vacía o ausente cuando nada sea fechable, y omite cuentas "
    "sin nada que decir. Prohibido inventar datos, fuentes o títulos: usa "
    "únicamente los hechos. Español periodístico, máximo 2 oraciones por "
    "campo."
)


def _zone(tz_name: str) -> ZoneInfo:
    """ZoneInfo for the settings tz; UTC fallback when invalid."""
    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - a bad stored tz must not 500 the API
        log.warning("invalid timezone %r in settings; using UTC", tz_name)
        return ZoneInfo("UTC")


def today_in(tz_name: str) -> date:
    """Today's date as seen from the settings timezone."""
    return datetime.now(_zone(tz_name)).date()


def day_window(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """``[start, next_start)`` bounds for the client-day.

    Computed in the settings timezone so "the day" means the client's day,
    not the server's or UTC's.
    """
    tz = _zone(tz_name)
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    return start, start + timedelta(days=1)


#: Hours after midnight whose first cut reaches back into the previous
#: evening, rescuing notes published after that day's last digest cut.
MORNING_CUTOVER_HOUR = 12
PREVIOUS_EVENING_HOURS = 3  # 21:00 the day before


def resolve_digest_window(
    session,
    *,
    client_id: int,
    day: date,
    tz_name: str,
) -> tuple[datetime, datetime, bool]:
    """Window for the day's digest, stable across the day's cuts.

    First generation during the morning (before ``MORNING_CUTOVER_HOUR``)
    extends three hours into the previous evening so notes published after
    that day's last cut are not orphaned between digests. The choice is
    persisted on the stored row (``content.window_start``) so later cuts
    rebuild with the same bounds instead of dropping the tail.
    """
    start, end = day_window(day, tz_name)
    existing = queries.get_daily_summary(session, client_id, day)
    if existing is not None:
        stored = (existing.content or {}).get("window_start")
        if stored:
            try:
                return datetime.fromisoformat(stored), end, True
            except ValueError:
                pass
        return start, end, False
    now_hour = datetime.now(_zone(tz_name)).hour
    if now_hour < MORNING_CUTOVER_HOUR:
        return start - timedelta(hours=PREVIOUS_EVENING_HOURS), end, True
    return start, end, False


def _noun(count: int) -> str:
    return "mención" if count == 1 else "menciones"


def _human_day(day: date) -> str:
    return f"{day.day} de {MONTHS_ES[day.month - 1]} de {day.year}"


# ----------------------------------------------------------- digest-brief-v3
# T2 facts: everything the brief esqueleto shows is DERIVED here (delta,
# tono, fechas, campo); the model only writes prose and picks indices.


#: A future date within this many days counts as «próxima»; at/before the
#: digest day it already «caducó».
FECHAS_PROXIMAS_DIAS = 7

#: Wording that makes a dated compromiso semantically «en duda» (F2b): the
#: stems cover aplazada/cancelada/suspendida/vencida and inflections.
FECHA_DUDA_STEMS = ("aplazad", "cancelad", "suspendid", "vencid")


def fecha_en_duda(*textos: object) -> bool:
    """True when any text carries deferral/cancellation wording (F2b)."""
    haystack = " ".join(str(t) for t in textos if t).lower()
    return any(stem in haystack for stem in FECHA_DUDA_STEMS)


def descarte_label(descarte: object) -> str | None:
    """«Descartado: N actualizaciones cosméticas, M historias fundidas».

    F3: the pre-card discard is visible, never silent. Only the clauses
    with actual discards render; None when there is nothing to report.
    """
    if not isinstance(descarte, dict):
        return None
    cosmeticas = descarte.get("cosmeticas") or 0
    fundadas = descarte.get("fundadas") or 0
    if not isinstance(cosmeticas, int) or not isinstance(fundadas, int):
        return None
    if cosmeticas <= 0 and fundadas <= 0:
        return None
    partes: list[str] = []
    if cosmeticas > 0:
        partes.append(
            f"{cosmeticas} "
            + ("actualización cosmética" if cosmeticas == 1 else "actualizaciones cosméticas")
        )
    if fundadas > 0:
        partes.append(f"{fundadas} " + ("historia fundida" if fundadas == 1 else "historias fundidas"))
    return f"Descartado: {', '.join(partes)}"


#: Field-report statuses the campo section shows, with their UI label.
CAMPO_ESTADOS = {"published": "publicada", "review": "en revisión"}


def tone_label(tone: dict | None) -> str | None:
    """Aggregated story tone: the dominant sentiment, never a raw count."""
    if not isinstance(tone, dict):
        return None
    neg = tone.get("negative", 0) or 0
    pos = tone.get("positive", 0) or 0
    neu = tone.get("neutral", 0) or 0
    if neg <= 0 and pos <= 0 and neu <= 0:
        return None
    if neg > max(pos, neu, 0):
        return "negativo"
    if pos > max(neg, neu, 0):
        return "positivo"
    if neg == 0 and pos == 0:
        return "neutral"
    return "mixto"


def _delta_key(noticia: dict):
    """Match key for the day-over-day comparison: event id, else title."""
    event_id = noticia.get("event_id")
    if event_id is not None:
        return ("id", event_id)
    title = noticia.get("title")
    if title:
        return ("titulo", normalize_title(title))
    return None


def _delta_label(title: str | None) -> str:
    """Sobrio, clipped label for a delta entry — never a raw dumped title."""
    clean = display_title(title)
    if not clean:
        return "(sin título)"
    if len(clean) <= DELTA_CLIP:
        return clean
    return f"{clean[:DELTA_CLIP].rsplit(' ', 1)[0]}…"


#: Tope duro del delta (T8.D) y recorte de la etiqueta sobria.
DELTA_MAX = 5
DELTA_CLIP = 60


def brief_delta(prev_noticias: list, noticias: list) -> list[str]:
    """Qué cambió vs el día hábil previo: nuevas historias y giros de tono.

    Matching by event id first, normalized title as fallback (loose rows
    carry no id). Densa por contrato (T8.D): los giros van primero (son el
    delta verdad), las nuevas después; tope duro :data:`DELTA_MAX` y
    etiqueta sobria recortada — nunca el volcado de titles crudos.
    """
    prev_by_key: dict = {}
    for noticia in prev_noticias or []:
        if not isinstance(noticia, dict):
            continue
        key = _delta_key(noticia)
        if key is not None:
            prev_by_key.setdefault(key, noticia)
    giros: list[str] = []
    nuevas: list[str] = []
    for noticia in noticias or []:
        if not isinstance(noticia, dict):
            continue
        label = _delta_label(noticia.get("title"))
        key = _delta_key(noticia)
        prev = prev_by_key.get(key) if key else None
        if prev is None:
            nuevas.append(f"Nueva historia: {label}")
            continue
        before = tone_label(prev.get("tone"))
        after = tone_label(noticia.get("tone"))
        if before and after and before != after:
            giros.append(f"{label}: el tono pasa de {before} a {after}")
    return (giros + nuevas)[:DELTA_MAX]


def brief_fechas(agenda: list, day: date) -> list[dict]:
    """Fechas que obligan, por regla: caducó (<= hoy) o próxima (<= 7 días).

    Parsed with the agenda detector's Spanish parser against the DIGEST day
    (never now(), so regenerating an old day stays stable). Undatable whens
    and far-future dates stay out of the section. Semantic estado (F2b):
    wording about postponements/cancellations makes the date «en duda»
    even when it sits in the future — a deferred date is not a commitment.
    """
    fechas: list[dict] = []
    for item in agenda or []:
        if not isinstance(item, dict):
            continue
        when, title = item.get("when"), item.get("title")
        if not when or not title:
            continue
        parsed = parse_spanish_date(when, day.year)
        if parsed is None:
            continue
        if parsed <= day:
            estado = "caducada"
        elif (parsed - day).days <= FECHAS_PROXIMAS_DIAS:
            estado = "proxima"
        else:
            continue
        if fecha_en_duda(title, when, item.get("status")):
            estado = "en duda"
        fechas.append(
            {"title": title, "when": when, "estado": estado, "fecha": parsed.isoformat()}
        )
    return fechas


def augment_fechas_from_agenda(session, client_id: int, day: date, fechas: list) -> list:
    """Fechas que obligan desde la tabla agenda_items (T8.D).

    El brief nunca dependió de que el narrador recuerde listar la agenda:
    las filas reales con ``event_date`` en ``[day, day + FECHAS_PROXIMAS_DIAS]``
    entran como «proxima» con su date_label. Homónimas (título normalizado)
    ya presentes en la ventana narrativa no se duplican. Determinista.
    """
    out = list(fechas or [])
    known = set()
    for f in out:
        if isinstance(f, dict) and f.get("title"):
            known.add(normalize_title(f["title"]))
    limit = day + timedelta(days=FECHAS_PROXIMAS_DIAS)
    rows = session.scalars(
        select(AgendaItem)
        .where(
            AgendaItem.client_id == client_id,
            AgendaItem.event_date.is_not(None),
            AgendaItem.event_date >= day,
            AgendaItem.event_date <= limit,
        )
        .order_by(AgendaItem.event_date, AgendaItem.id)
    ).all()
    for row in rows:
        key = normalize_title(row.title or "")
        if not key or key in known:
            continue
        known.add(key)
        estado = "en duda" if fecha_en_duda(row.title, row.date_label, row.notes) else "proxima"
        out.append(
            {
                "title": row.title,
                "when": row.date_label or row.event_date.isoformat(),
                "estado": estado,
                "fecha": row.event_date.isoformat(),
            }
        )
    return out


#: Piso de calidad (digest-brief-v3): una historia cuyo único contenido es una
#: actualización cosmética de red social (foto de portada/perfil, avatar) no
#: merece tarjeta. Heurística determinística sobre el título; la mención sigue
#: contando en cobertura y en el log por fuente de redes.
COSMETIC_TITLE_RE = re.compile(
    r"\b(?:actualiz|cambi|renov)[oó]\s+(?:su\s+)?(?:foto|imagen|portada|avatar|perfil)\b",
    re.I,
)


def is_cosmetic_story(title: str | None) -> bool:
    """True when the title is a social-profile cosmetic update and nothing
    else (no editorial text detectable from the title itself)."""
    if not title:
        return False
    return bool(COSMETIC_TITLE_RE.search(title))


# --------------------------------------------------- T8.A merge editorial
# Umbral del merge en la capa digest: MÁS agresivo que el de ingest (0.5,
# events.py) porque aquí solo se juega la presentación — la clusterización
# canónica sigue en ingest. Una misma historia parafraseada por outlets
# distintos diluye el Jaccard; calibrado con la regen 24-oct: la saga
# consulta/pensiones colapsa a UNA tarjeta, los posts X de la misma noticia
# se fundan entre sí, y ningún par entre historias distintas alcanza el
# umbral.
TWIN_STORY_SIMILARITY = 0.2

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
HANDLE_RE = re.compile(r"(?<![a-z0-9])@[a-z0-9_]+", re.I)
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # symbols, pictographs, emoji blocks
    "\U00002600-\U000027BF"  # misc symbols and dingbats
    "\U0001F1E6-\U0001F1FF"  # flags
    "\U00002B00-\U00002BFF"  # arrows and stars
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"  # zero-width joiner
    "]+"
)
HASHTAG_RE = re.compile(r"#\w+")
#: X-post separator chrome: «🏀 || nota», «#Entérate || nota» — the pipes
#: never carry meaning once emoji/hashtag chrome is gone.
_SEPARATOR_CHROME_RE = re.compile(r"\s*\|\|+\s*")


def display_title(title: str | None) -> str:
    """Sobrio presentation title: sin emojis, hashtags, URLs ni @handles.

    The RAW title always survives on the sources; this is the presentation
    (and twin-comparison) layer. Idempotent, like strip_fb_chrome. The
    X-post separator chrome («🏀 || nota») and the trailing outlet
    signature («... - atiemponoticias.mx») are chrome too: the medium
    lives on the source line, never in the headline.
    """
    if not title:
        return ""
    out = _URL_RE.sub(" ", title)
    out = HANDLE_RE.sub(" ", out)
    out = _EMOJI_RE.sub(" ", out)
    out = HASHTAG_RE.sub(" ", out)  # el hashtag completo se va, es metadata
    out = _SEPARATOR_CHROME_RE.sub(" ", out)
    out = strip_outlet_suffix(out)
    out = re.sub(r"\s+", " ", out).strip()
    return out or title.strip()


def _noticia_strength(nota: dict) -> tuple:
    """Best-source ranking: more outlets first, then confidence scale."""
    confidence = nota.get("confidence")
    rank = (
        CONFIDENCE_SCALE.index(confidence)
        if confidence in CONFIDENCE_SCALE
        else len(CONFIDENCE_SCALE)
    )
    return (-len(nota.get("sources") or []), rank)


def merge_twin_noticias(noticias: list) -> list:
    """Post-agregación editorial: misma historia, UNA tarjeta (T8.A).

    Single-linkage sobre la similitud de títulos limpios de chrome con
    umbral digest (:data:`TWIN_STORY_SIMILARITY`); la tarjeta fundida hereda
    hecho/por_que de la mejor fuente (más outlets, mejor confianza) y lista
    TODAS las fuentes de los miembros. El resto de los agregados es la
    unión: tono se suma, ``repeat`` es OR, ``person_ids`` se combina, y los
    ids de evento persisten en ``event_ids`` (``event_id`` queda el de la
    mejor fuente) para el delta y la herencia de prosa. Determinista.
    """
    notas = [n for n in noticias or [] if isinstance(n, dict)]
    total = len(notas)
    parent = list(range(total))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    cleaned = [display_title(nota.get("title")) for nota in notas]
    for a in range(total):
        if not cleaned[a]:
            continue
        for b in range(a + 1, total):
            if not cleaned[b]:
                continue
            if (
                similarity_with_suffix_variants(cleaned[a], cleaned[b])
                >= TWIN_STORY_SIMILARITY
            ):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)

    groups: dict[int, list[int]] = {}
    for index in range(total):
        groups.setdefault(find(index), []).append(index)
    merged: list[dict] = []
    for root in sorted(groups):
        members = groups[root]
        if len(members) == 1:
            merged.append(notas[members[0]])
            continue
        by_strength = sorted(members, key=lambda i: (_noticia_strength(notas[i]), i))
        card = dict(notas[by_strength[0]])
        event_ids: list = []
        for index in members:
            event_id = notas[index].get("event_id")
            if event_id is not None and event_id not in event_ids:
                event_ids.append(event_id)
        if event_ids:
            card["event_ids"] = event_ids
        seen: set = set()
        fuentes: list = []
        for index in members:
            for source in notas[index].get("sources") or []:
                key = (source.get("source"), source.get("url"))
                if key in seen:
                    continue
                seen.add(key)
                fuentes.append(source)
        card["sources"] = fuentes
        # hecho/por_que from the best source that has them.
        for field in ("summary", "why_it_matters"):
            if not card.get(field):
                fallback = next(
                    (notas[i].get(field) for i in by_strength if notas[i].get(field)),
                    None,
                )
                if fallback:
                    card[field] = fallback
        tone: dict = {}
        for index in members:
            for key, value in (notas[index].get("tone") or {}).items():
                tone[key] = tone.get(key, 0) + (value or 0)
        card["tone"] = tone
        card["confidence"] = confidence_for(len({s.get("source") for s in fuentes}))
        card["person_ids"] = sorted(
            {p for i in members for p in notas[i].get("person_ids") or []}
        )
        card["repeat"] = any(notas[i].get("repeat") for i in members)
        if not card.get("topic"):
            card["topic"] = next(
                (notas[i].get("topic") for i in by_strength if notas[i].get("topic")),
                None,
            )
        merged.append(card)
    return merged


# --------------------------------------------------- T8.B orden por impacto

#: Tarjeta compilada que absorbe la cola menor (T8.B): preserva cobertura
#: sin robar tarjetas al top editorial.
TAMBIEN_HOY = "También hoy"

#: Piso editorial aprobado: la página de perfil alto muestra 9-14 tarjetas.
#: La fusión de cola nunca baja del piso cuando hay material.
TARJETAS_MIN = 9

#: Una tarjeta de cola lista <=2 fuentes; más fuentes = historia con cuerpo.
COLA_MAX_FUENTES = 2


def _impact_rank(nota: dict) -> tuple:
    """Descending impact: fuentes, menciones clasificadas, tono negativo."""
    sources, classified = _impact(nota)
    tone = nota.get("tone") if isinstance(nota.get("tone"), dict) else {}
    return (-sources, -classified, -(tone.get("negative") or 0))


def _brief_indices(brief: dict, bucket: str) -> list[int]:
    """Validated indices a brief bucket references, in declared order."""
    entries = brief.get(bucket) if isinstance(brief, dict) else None
    if not isinstance(entries, list):
        return []
    return [
        e["index"]
        for e in entries
        if isinstance(e, dict) and isinstance(e.get("index"), int)
    ]


def _unique(indices: list[int]) -> list[int]:
    seen: set = set()
    out: list = []
    for index in indices:
        if index not in seen:
            seen.add(index)
            out.append(index)
    return out


def apply_impact_order(content: dict) -> None:
    """F5: orden editorial — riesgo, decision, resto por impacto, ruido al final.

    Permuta ``noticias`` y ``tarjetas`` juntas (el índice sigue compartido) y
    remapea los índices de TODOS los buckets del brief. Determinista: el
    orden dentro de cada bloque es el del brief (la prioridad del modelo) y
    el empate en impacto conserva el orden previo (sort estable).
    """
    noticias = content.get("noticias")
    tarjetas = content.get("tarjetas")
    if not (isinstance(noticias, list) and isinstance(tarjetas, list)):
        return
    total = min(len(noticias), len(tarjetas))
    if total == 0:
        return
    raw_brief = content.get("brief")
    brief: dict = raw_brief if isinstance(raw_brief, dict) else {}
    riesgos = [i for i in _brief_indices(brief, "riesgos") if 0 <= i < total]
    decisiones = [i for i in _brief_indices(brief, "decisiones") if 0 <= i < total]
    ruido = [i for i in _brief_indices(brief, "ruido") if 0 <= i < total]
    marked = set(riesgos) | set(decisiones) | set(ruido)
    resto = [i for i in range(total) if i not in marked]
    resto.sort(
        key=lambda i: _impact_rank(noticias[i])
        if isinstance(noticias[i], dict)
        else (0, 0, 0)
    )
    # Una tarjeta marcada en dos buckets entra una sola vez (precede el
    # bloque más alto); el orden final es SIEMPRE una permutación 0..total-1.
    seen: set = set()
    order: list = []
    for index in _unique(riesgos) + _unique(decisiones) + resto + _unique(ruido):
        if index not in seen:
            seen.add(index)
            order.append(index)
    for index in range(total):
        if index not in seen:
            seen.add(index)
            order.append(index)
    if order == list(range(total)):
        return
    position = {old: new for new, old in enumerate(order)}
    content["noticias"] = [noticias[i] for i in order] + list(noticias[total:])
    content["tarjetas"] = [tarjetas[i] for i in order] + list(tarjetas[total:])
    for bucket in BRIEF_BUCKETS:
        entries = brief.get(bucket)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("index") in position:
                entry["index"] = position[entry["index"]]


def _es_tarjeta_cola(tarjeta: dict) -> bool:
    """Cola menor: pocas fuentes, tono neutro, sin por_que que la sostenga."""
    if len(tarjeta.get("fuentes") or []) > COLA_MAX_FUENTES:
        return False
    if tarjeta.get("tono") not in (None, "neutral"):
        return False
    if tarjeta.get("por_que"):
        return False
    return True


def compile_tail_cards(content: dict) -> bool:
    """Funde la cola menor en UNA tarjeta compilada «También hoy» (T8.B).

    Camina la cola del ranking ya ordenado y absorbe la corrida final de
    tarjetas menores (<=2 fuentes, tono neutro, sin por_que) en una sola
    tarjeta con bullets; el piso :data:`TARJETAS_MIN` nunca se perfora
    cuando hay material. Las noticias conservan TODAS las historias (la
    cobertura vive en el detalle); los índices del brief que apuntaban a
    tarjetas absorbadas se descartan (la info queda en los bullets) y los
    restantes siguen válidos porque la fusión es un sufijo.
    """
    tarjetas = content.get("tarjetas")
    if not isinstance(tarjetas, list) or not tarjetas:
        return False
    total = len(tarjetas)
    if total <= TARJETAS_MIN:
        # En días cortos la cola ES la página: nada que fundar.
        return False
    run = 0
    for tarjeta in reversed(tarjetas):
        if not isinstance(tarjeta, dict) or not _es_tarjeta_cola(tarjeta):
            break
        run += 1
    max_take = max(0, total - (TARJETAS_MIN - 1))
    take = min(run, max_take)
    if take <= 0:
        return False
    swallowed = tarjetas[total - take :]
    notas: list = []
    fuentes: list = []
    for tarjeta in swallowed:
        label = tarjeta.get("titulo") or tarjeta.get("hecho") or "(sin título)"
        names = [f for f in tarjeta.get("fuentes") or [] if f]
        if names:
            label = f"{label} ({', '.join(names)})"
        notas.append(label)
        for name in names:
            if name not in fuentes:
                fuentes.append(name)
    compiled = {
        "titulo": TAMBIEN_HOY,
        "hecho": None,
        "por_que": None,
        "notas": notas,
        "fuentes": fuentes,
        "tono": None,
        "repeat": any(
            t.get("repeat") for t in swallowed if isinstance(t, dict)
        ),
        "angulo_nuevo": None,
    }
    content["tarjetas"] = tarjetas[: total - take] + [compiled]
    valid = total - take
    brief = content.get("brief")
    if isinstance(brief, dict):
        for bucket in BRIEF_BUCKETS:
            entries = brief.get(bucket)
            if isinstance(entries, list):
                brief[bucket] = [
                    e
                    for e in entries
                    if not (
                        isinstance(e, dict) and isinstance(e.get("index"), int)
                    )
                    or e["index"] < valid
                ]
    return True


def build_tarjetas(noticias: list) -> list[dict]:
    """One tarjeta per noticia, index-aligned; prose fields mirror the row.

    ``hecho``/``por_que`` read the narrative fields so the inheritance path
    (failed regen keeps previous prose) flows into the card for free. The
    heuristic esqueleto and the LLM fill the SAME shape.
    """
    tarjetas: list[dict] = []
    for nota in noticias or []:
        if not isinstance(nota, dict):
            continue
        tarjetas.append(
            {
                # T8.C: título sobrio para presentación; el crudo vive en la
                # noticia y en las fuentes.
                "titulo": display_title(nota.get("title")) or nota.get("title"),
                "hecho": nota.get("summary"),
                "por_que": nota.get("why_it_matters"),
                "fuentes": [
                    fuente.get("source")
                    for fuente in nota.get("sources") or []
                    if isinstance(fuente, dict) and fuente.get("source")
                ],
                "tono": tone_label(nota.get("tone")),
                "repeat": bool(nota.get("repeat")),
                # The new angle of a repeated story is narrative (T3); the
                # esqueleto always carries the key so the render is fixed.
                "angulo_nuevo": None,
            }
        )
    return tarjetas


def previous_day_noticias(session, client_id: int, day: date) -> list[dict]:
    """Noticias of the latest summary STRICTLY before ``day`` (día hábil previo).

    Weekends/holidays with no summary are skipped by construction: the
    comparison is against the last published editorial cut.
    """
    row = session.scalar(
        select(DailySummary)
        .where(
            DailySummary.client_id == client_id,
            DailySummary.summary_date < day,
        )
        .order_by(DailySummary.summary_date.desc())
        .limit(1)
    )
    if row is None:
        return []
    noticias = (row.content or {}).get("noticias")
    return noticias if isinstance(noticias, list) else []


def build_campo(session, client_id: int, utc_start, utc_end) -> list[dict]:
    """Field reports of the window: published siempre; review, marcado.

    Window over ``created_at`` (the intake instant); draft/rejected never
    show. Absence of rows degrades to an empty list — the section is
    gated on real data, never rendered empty.
    """
    rows = session.scalars(
        select(FieldReport).where(
            FieldReport.client_id == client_id,
            FieldReport.status.in_(tuple(CAMPO_ESTADOS)),
            FieldReport.created_at >= utc_start,
            FieldReport.created_at < utc_end,
        )
    ).all()
    return [
        {
            "titulo": row.title,
            "contenido": row.content,
            "lugar": row.place,
            "cuando": row.happened_at.isoformat() if row.happened_at else None,
            "estado": CAMPO_ESTADOS[row.status],
        }
        for row in rows
    ]


def _heuristic_headline(
    day: date,
    total: int,
    silent: list[str],
    by_source: dict,
    negative_events: int = 0,
    noticias: list | None = None,
) -> str:
    """Fixed-template Spanish headline; deterministic for a given input.

    digest-brief-v3: the lead names the dominant event by COMPUTED impact
    (sources, then classified mentions) — never mere volume ordering.
    """
    human = _human_day(day)
    if total == 0:
        sentence = f"Hoy {human} no se registraron menciones."
        if silent:
            shown = ", ".join(silent[:MAX_KEYWORDS_NARRATIVE])
            sentence += f" Sin cobertura para: {shown}."
        return sentence

    parts = []
    dominant = None
    for nota in noticias or []:
        if not isinstance(nota, dict) or not nota.get("title"):
            continue
        if dominant is None or _impact(nota) > _impact(dominant):
            dominant = nota
    if dominant is not None:
        sobrio = display_title(dominant["title"]) or dominant["title"]
        parts.append(f"{sobrio} encabeza la cobertura del día.")
    parts.append(f"Se registraron {total} {_noun(total)}.")
    if by_source:
        dominant_source = max(by_source.items(), key=lambda kv: (kv[1], kv[0]))[0]
        parts.append(f"La fuente con más notas fue {dominant_source}.")
    if negative_events:
        parts.append(
            f"{negative_events} {'nota' if negative_events == 1 else 'notas'} con tono "
            "negativo dominante."
        )
    if silent:
        shown = ", ".join(silent[:MAX_KEYWORDS_NARRATIVE])
        parts.append(f"Sin menciones: {shown}.")
    return " ".join(parts)


def _impact(nota: dict) -> tuple[int, int]:
    """Editorial impact: reach (sources) first, classified volume second."""
    if not isinstance(nota, dict):
        return (0, 0)
    tone = nota.get("tone")
    classified = (
        sum(v or 0 for v in tone.values()) if isinstance(tone, dict) else 0
    )
    return (len(nota.get("sources") or []), classified)


#: Bucket caps keep the heuristic brief as short as the LLM one.
MAX_RUIDO = 3

#: Razón estándar del piso de riesgo (F5). El cap de decisiones es solo del
#: bucket decisión: los negativos dejan de competir ahí y llenan el suyo,
#: sin tope — el piso cubre TODAS las negativas no referenciadas.
RIESGO_RAZON = "tono negativo dominante"


def _heuristic_brief_sections(noticias: list) -> tuple[list, list, list]:
    """Heuristic fill of the SAME esqueleto the LLM completes: tono/conteo.

    Positive-dominant stories go to a_favor; repeated single-source items
    are ruido. The negative floor is NOT here anymore (F5): :func:`ensure_riesgos`
    owns every negative-dominant card in BOTH paths, so positives and the
    top-impact fallback shape the decision bucket.
    """
    decisiones: list[dict] = []
    ruido: list[dict] = []
    a_favor: list[dict] = []
    for index, nota in enumerate(noticias or []):
        if not isinstance(nota, dict):
            continue
        label = tone_label(nota.get("tone"))
        fuentes = len(nota.get("sources") or [])
        if label == "positivo":
            a_favor.append({"index": index, "razon": "tono positivo dominante"})
        elif nota.get("repeat") and fuentes < 2 and len(ruido) < MAX_RUIDO:
            ruido.append({"index": index, "razon": "reiteración sin datos nuevos"})
    if not decisiones and noticias:
        top = max(range(len(noticias)), key=lambda i: _impact(noticias[i]))
        decisiones.append({"index": top, "razon": "mayor cobertura del día"})
    return decisiones, ruido, a_favor


def ensure_riesgos(content: dict) -> None:
    """Piso determinístico de negativas (F5), en AMBOS caminos.

    Toda tarjeta de tono negativo dominante NO referenciada en ningún bucket
    entra a ``riesgos`` con la razón estándar, sin cap. Corre antes del piso
    de densidad: lo ya marcado por el modelo (o por esta pasada) no se
    duplica, y el topup de decisiones completa con lo restante. Determinista.
    """
    brief = content.get("brief")
    noticias = content.get("noticias")
    if not (isinstance(brief, dict) and isinstance(noticias, list)):
        return
    riesgos = brief.get("riesgos")
    if not isinstance(riesgos, list):
        riesgos = []
        brief["riesgos"] = riesgos
    marked: set = set()
    for bucket in BRIEF_BUCKETS:
        for entry in brief.get(bucket) or []:
            if isinstance(entry, dict) and isinstance(entry.get("index"), int):
                marked.add(entry["index"])
    for index, nota in enumerate(noticias):
        if index in marked or not isinstance(nota, dict):
            continue
        if tone_label(nota.get("tone")) != "negativo":
            continue
        riesgos.append({"index": index, "razon": RIESGO_RAZON})


def digest_prompt_view(facts: dict, dia_previo: list | None = None) -> dict:
    """Lean facts projection for the narrative prompt.

    Everything the SYSTEM_PROMPT instructions can reference, nothing the
    merge re-derives: no ids, no urls, no coverage/pendientes (deterministic
    sections the model never writes). Order is the content's own, so
    ``items[i].index`` keeps matching ``noticias[i]``. Titles travel sobrios
    (T8.C): the chrome never reaches the model. ``dia_previo`` (T8.D) is the
    compact previous-day context the density rules calibrate against.
    """
    noticias = []
    for noticia in facts.get("noticias", []):
        view = {
            key: noticia[key]
            for key in ("title", "summary", "topic", "confidence", "tone", "when_label")
            if key in noticia
        }
        if "title" in view:
            view["title"] = display_title(view["title"]) or view["title"]
        if "repeat" in noticia:
            view["repeat"] = noticia["repeat"]
        view["sources"] = [
            {
                key: (display_title(source[key]) or source[key]) if key == "title" else source[key]
                for key in ("source", "title")
                if key in source
            }
            for source in noticia.get("sources", [])
        ]
        noticias.append(view)

    rectora = {
        key: value for key, value in facts.get("rectora", {}).items() if key != "person_id"
    }
    if "actions" in rectora:
        rectora["actions"] = [
            {key: action[key] for key in ("title", "sentiment", "role", "org") if key in action}
            for action in rectora["actions"]
        ]

    personas = [
        {key: person[key] for key in person if key != "person_id"}
        for person in facts.get("personas", [])
    ]

    view = {
        "noticias": noticias,
        "rectora": rectora,
        "redes": facts.get("redes", {}),
        "personas": personas,
    }
    if dia_previo:
        compacto = []
        for nota in dia_previo[:DIA_PREVIO_MAX]:
            if not isinstance(nota, dict):
                continue
            compacto.append(
                {
                    "title": display_title(nota.get("title")),
                    "tono": tone_label(nota.get("tone")),
                }
            )
        view["dia_previo"] = compacto
    return view


#: Tope del resumen compacto del día previo en el prompt (T8.D).
DIA_PREVIO_MAX = 12

#: Densidad (T8.D): el brief muestra mínimo tres decisiones cuando hay
#: candidatas. El modelo marca; el builder completa el piso con las de mayor
#: impacto NO marcadas (la selección del modelo nunca se recorta).
DECISION_MIN = 3
DECISION_TOPUP_RAZON = "mayor impacto del día"


def ensure_decision_density(content: dict) -> None:
    """Completa el piso de decisiones del brief (T8.D) sin tocar el modelo.

    Con menos de :data:`DECISION_MIN` decisiones marcadas y tarjetas sin
    marcar disponibles, las de mayor impacto entran como decisión con la
    razón estándar del heurístico. Las entradas del modelo van primero y
    jamás se recortan: el piso es aditivo. Determinista.
    """
    brief = content.get("brief")
    noticias = content.get("noticias")
    if not (isinstance(brief, dict) and isinstance(noticias, list)):
        return
    decisiones = brief.get("decisiones")
    if not isinstance(decisiones, list):
        return
    total = len(noticias)
    if len(decisiones) >= DECISION_MIN or total < DECISION_MIN:
        return
    marked: set = set()
    for bucket in BRIEF_BUCKETS:
        for entry in brief.get(bucket) or []:
            if isinstance(entry, dict) and isinstance(entry.get("index"), int):
                marked.add(entry["index"])
    candidatos = [i for i in range(total) if i not in marked]
    candidatos.sort(
        key=lambda i: _impact_rank(noticias[i])
        if isinstance(noticias[i], dict)
        else (0, 0, 0)
    )
    for index in candidatos[: DECISION_MIN - len(decisiones)]:
        decisiones.append({"index": index, "razon": DECISION_TOPUP_RAZON})


def _digest_prompt(day: date, facts: dict, dia_previo: list | None = None) -> str:
    repeats = any(n.get("repeat") for n in facts.get("noticias", []))
    extra = (
        "\nLas notas con repeat=true ya fueron cubiertas en ediciones "
        "anteriores: trátalas como reiteración breve, destacando solo el "
        "ángulo nuevo. En el summary de esas notas indica explícitamente que "
        "la historia se repite nuevamente respecto a ediciones previas. "
        "Destaca explícitamente los cambios de tono negativos del día."
        if repeats
        else ""
    )
    return (
        f"Digest del {day.isoformat()} (todas las cifras y títulos son datos "
        f"verificados; el items[i].index corres a noticias[i]):\n"
        f"{json.dumps(digest_prompt_view(facts, dia_previo), ensure_ascii=False, default=str)}"
        f"{extra}"
    )


def _openai_generator(effective: EffectiveSettings) -> Callable[[str], str]:
    """Callable prompt->payload for the configured provider.

    Same request shape as the sentiment analyzer: POST {base}/chat/
    completions, Bearer key, model from settings, temperature 0. Raises on
    any failure; the caller owns the heuristic fallback.
    """
    base_url = (effective.ai_base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    model = effective.ai_model or DEFAULT_OPENAI_MODEL
    api_key = effective.ai_api_key or ""

    def generate(prompt: str) -> str:
        payload: str | None = None
        last_error: Exception | None = None
        for attempt in range(ATTEMPTS):
            if attempt:
                time.sleep(BACKOFF_S * attempt)
            body: dict = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
            }
            if attempt == 0:
                # Guided generation (docs/contrato-narrativa-del-digest.md
                # §4). Retries go plain: a provider without json_schema
                # support degrades to the old behavior instead of failing.
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "digest_narrative",
                        "schema": narrative_response_schema(),
                    },
                }
            try:
                resp = httpx.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                    timeout=TIMEOUT_S,
                )
                resp.raise_for_status()
                raw_content = resp.json()["choices"][0]["message"]["content"]
                if not isinstance(raw_content, str) or not raw_content.strip():
                    # content:null becomes str "None" and breaks json.loads
                    # upstream; treat it as a failed attempt instead.
                    raise ValueError("empty summary content")
                # Models wrap the JSON in ``` fences; the digest json.loads
                # chokes on the leading backtick otherwise.
                payload = strip_code_fence(raw_content)
                break
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
            ) as exc:
                last_error = exc
                log.debug("summary llm attempt %d/%d failed", attempt + 1, ATTEMPTS)
                log.debug("error: %s", exc)
        if payload is None:
            raise RuntimeError(f"summary ll failed after {ATTEMPTS} attempts: {last_error}")
        return payload

    return generate


def summary_generator(effective: EffectiveSettings) -> Callable[[str], str] | None:
    """LLM narrative callable for the effective settings, else None.

    None is the documented 'no provider' state (local sentiment models
    cannot generate text), not an error.
    """
    provider = (effective.ai_provider or "").strip().lower()
    if provider != "openai" or not (effective.ai_api_key or "").strip():
        return None
    return _openai_generator(effective)


def build_daily_summary(
    session,
    *,
    client_id: int,
    day: date,
    generate: Callable[[str], str] | None = None,
):
    """Assemble digest v2 and upsert the DailySummary row.

    ``generate`` overrides the settings-driven LLM callable (tests,
    tooling). Returns the stored row; ``mode`` is ``llm`` only when the
    narrative pass applied cleanly.
    """
    effective = resolve_effective_settings(session, client_id)
    start, end, window_extended = resolve_digest_window(
        session, client_id=client_id, day=day, tz_name=effective.timezone
    )
    # SQLite keeps datetimes as naive wall strings and compares them
    # lexically, so the bounds travel as UTC walls (the ingest pipeline
    # stores UTC); PostgreSQL compares true timestamps and reads the same
    # instants either way.
    utc_start = start.astimezone(timezone.utc)
    utc_end = end.astimezone(timezone.utc)
    mentions = list(
        session.scalars(
            select(Mention).where(
                Mention.client_id == client_id,
                Mention.published_at >= utc_start,
                Mention.published_at < utc_end,
            )
        )
    )
    total = len(mentions)

    # Silent keywords -> PENDIENTES (v1 semantics: an active keyword whose
    # row never appears in the day's mentions; renamed rows still count).
    all_keywords = list(queries.list_keywords(session, client_id, active_only=False))
    keyword_text_by_id = {k.id: k.text for k in all_keywords}
    mentioned = {
        keyword_text_by_id[m.keyword_id]
        for m in mentions
        if m.keyword_id and m.keyword_id in keyword_text_by_id
    }
    silent = sorted({k.text for k in all_keywords if k.is_active} - mentioned)

    facts = build_digest_facts(
        session,
        client_id=client_id,
        day=day,
        tz=effective.timezone,
        focus_person_id=effective.digest_focus_person_id,
        mentions=mentions,
        window_start=start if window_extended else None,
    )
    content = {
        **facts,
        "schema": DIGEST_SCHEMA_VERSION,
        "date": day.isoformat(),
        "timezone": effective.timezone,
    }
    content["temas_sin_nota"] = silent
    # Limitaciones: the coverage gaps (tracked sources silent in the window).
    # Silent keywords moved to temas_sin_nota (Noticias block); legacy rows
    # keep keywords here and render unchanged.
    content["pendientes"] = list(content["coverage"]["gaps"])
    if window_extended:
        # Persist the extended bounds: later cuts rebuild with the same
        # window instead of dropping the rescued late-evening tail.
        content["window_start"] = start.isoformat()

    # Repeat detection: events whose earliest mention predates this
    # window were already circulating in previous editions; the narrative
    # must treat them as reiterations, not new stories.
    window_start_utc = start.astimezone(timezone.utc)
    for noticia in content["noticias"]:
        eid = noticia.get("event_id")
        if not eid:
            continue
        earliest = session.scalar(
            select(func.min(Mention.published_at)).where(
                Mention.client_id == client_id, Mention.event_id == eid
            )
        )
        if earliest is not None:
            # SQLite returns naive walls; normalize for the comparison.
            if earliest.tzinfo is None:
                earliest = earliest.replace(tzinfo=timezone.utc)
            if earliest < window_start_utc:
                noticia["repeat"] = True

    # Piso de calidad (digest-brief-v3): una actualización cosmética de red
    # social (foto de portada/perfil sin texto editorial) no genera tarjeta.
    # Se funde en el log por fuente de redes —el conteo de cobertura la
    # incluye igual— y sale de noticias ANTES de prompt/tarjetas/brief para
    # mantener el índice noticias↔tarjetas alineado. F3: el descarte es
    # visible — los contadores viajan en brief.descarte.
    pre_cosmetic = len(content["noticias"])
    content["noticias"] = [
        nota
        for nota in content["noticias"]
        if not is_cosmetic_story(nota.get("title"))
    ]
    descartes_cosmeticas = pre_cosmetic - len(content["noticias"])
    # T8.A: la fusión editorial de gemelas va ANTES de prompt/tarjetas/brief
    # (índice noticias↔tarjetas↔brief único) — el resto del pipeline lee
    # historias, no menciones gemelas.
    pre_merge = len(content["noticias"])
    content["noticias"] = merge_twin_noticias(content["noticias"])
    historias_fundadas = pre_merge - len(content["noticias"])

    # Events whose mentions read negative-dominant, for the narrative emphasis
    # (the LLM gets tone per noticia; the heuristic names the count).
    negative_events = 0
    for noticia in content["noticias"]:
        tone = noticia.get("tone") or {}
        neg = tone.get("negative", 0)
        if neg > max(tone.get("positive", 0), tone.get("neutral", 0), 0):
            negative_events += 1

    narrative = _heuristic_headline(
        day,
        total,
        silent,
        content["coverage"]["by_source"],
        negative_events,
        content["noticias"],
    )
    mode = "heuristic"
    llm_ok = False
    brief_payload: dict | None = None
    if generate is None:
        generate = summary_generator(effective)
    if generate is not None and total > 0:
        try:
            prompt = _digest_prompt(
                day, content, dia_previo=previous_day_noticias(session, client_id, day)
            )
            payload = json.loads(generate(prompt))
        except Exception as exc:  # noqa: BLE001 - heuristic is the contract
            log.warning("digest llm failed for %s (%s); heuristic fallback", day, exc)
        else:
            errors = apply_narrative(content, payload)
            headline = payload.get("headline") if isinstance(payload, dict) else None
            if not errors and isinstance(headline, str) and headline.strip():
                narrative, mode, llm_ok = headline.strip(), "llm", True
                brief_payload = payload
            else:
                log.warning("digest llm payload rejected for %s: %s", day, errors)

    if not llm_ok:
        # Failed (or skipped) regen of a digest that was llm-authored: keep
        # the previous narrative instead of downgrading a good digest to
        # template prose. Facts stay fresh; only the prose is inherited.
        previous = queries.get_daily_summary(session, client_id, day)
        if previous is not None and previous.mode == "llm":
            prev_content = previous.content or {}
            # Merged cards (T8.A) carry several event ids: index and match by
            # ALL of them, so prose survives regens regardless of the split.
            prev_by_event: dict = {}
            for prev_nota in prev_content.get("noticias") or []:
                if not isinstance(prev_nota, dict):
                    continue
                lookup = list(prev_nota.get("event_ids") or [])
                if prev_nota.get("event_id") is not None:
                    lookup.append(prev_nota["event_id"])
                for event_id in lookup:
                    prev_by_event.setdefault(event_id, prev_nota)
            for nota in content["noticias"]:
                lookup = list(nota.get("event_ids") or [])
                if nota.get("event_id") is not None:
                    lookup.append(nota["event_id"])
                old = next(
                    (prev_by_event[eid] for eid in lookup if eid in prev_by_event),
                    None,
                )
                if old is None:
                    continue
                if not nota.get("summary") and old.get("summary"):
                    nota["summary"] = old["summary"]
                if not nota.get("why_it_matters") and old.get("why_it_matters"):
                    nota["why_it_matters"] = old["why_it_matters"]
            prev_rectora = prev_content.get("rectora") or {}
            rectora = content.get("rectora") or {}
            for key in ("tone", "watch"):
                if not rectora.get(key) and prev_rectora.get(key):
                    rectora[key] = prev_rectora[key]
            # home-digest-v2: the narrative blocks travel with the prose.
            prev_agenda = prev_content.get("agenda")
            if not content.get("agenda") and prev_agenda:
                content["agenda"] = prev_agenda
            prev_activity = prev_rectora.get("activity")
            if not rectora.get("activity") and prev_activity:
                rectora["activity"] = prev_activity
            for source, prev_data in (prev_content.get("redes") or {}).items():
                prev_note = prev_data.get("note") if isinstance(prev_data, dict) else None
                target = (content.get("redes") or {}).get(source)
                if prev_note and isinstance(target, dict) and not target.get("note"):
                    target["note"] = prev_note
            prev_plain = (prev_content.get("plain_text") or "").split("\n", 1)[0]
            if prev_plain:
                narrative = prev_plain
            mode = "llm"

    # digest-brief-v3: the deterministic esqueleto. Tarjetas mirror noticias
    # (index-aligned, prose included); delta/fechas/campo are pure facts. The
    # heuristic fills the buckets by tono/conteo; a valid LLM selection
    # replaces them wholesale (same esqueleto, one render path).
    content["tarjetas"] = build_tarjetas(content["noticias"])
    heu_decisiones, heu_ruido, heu_a_favor = _heuristic_brief_sections(
        content["noticias"]
    )
    content["brief"] = {
        "delta": brief_delta(
            previous_day_noticias(session, client_id, day), content["noticias"]
        ),
        "decisiones": heu_decisiones,
        "riesgos": [],
        "ruido": heu_ruido,
        "a_favor": heu_a_favor,
        "fechas": brief_fechas(content.get("agenda") or [], day),
    }
    # T8.D: la agenda REAL (tabla) alimenta fechas que obligan — el 28-oct a
    # 4 días entra aunque el narrador no haya listado agenda.
    content["brief"]["fechas"] = augment_fechas_from_agenda(
        session, client_id, day, content["brief"]["fechas"]
    )
    if brief_payload is not None:
        apply_brief(content, brief_payload)
    # F5: piso de riesgo — las negativas no referenciadas a su bucket, antes
    # del piso de densidad (T8.D completa decisiones con lo restante).
    ensure_riesgos(content)
    # T8.D: piso de densidad — mínimo tres decisiones cuando haya candidatas.
    ensure_decision_density(content)
    content["brief"]["headline"] = narrative
    if descartes_cosmeticas + historias_fundadas > 0:
        content["brief"]["descarte"] = {
            "cosmeticas": descartes_cosmeticas,
            "fundadas": historias_fundadas,
        }
    content["campo"] = build_campo(session, client_id, utc_start, utc_end)

    # T8.B: orden editorial (decision -> impacto -> ruido) y fusión de la
    # cola menor en «También hoy». Siempre POST-brief: los índices que
    # remapea son los definitivos.
    apply_impact_order(content)
    compile_tail_cards(content)

    content["plain_text"] = render_plain_text(content, narrative)
    row = queries.upsert_daily_summary(
        session,
        client_id=client_id,
        day=day,
        content=content,
        narrative=narrative,
        mode=mode,
    )
    # Narrative revisions (summary-revisions): EVERY build appends an
    # immutable copy, so no prose is ever lost to the next cut. Best-effort:
    # a logging failure must not fail the digest (agenda-hook contract).
    try:
        from app.models import DailySummaryRevision

        last_seq = session.scalar(
            select(func.max(DailySummaryRevision.seq)).where(
                DailySummaryRevision.client_id == client_id,
                DailySummaryRevision.summary_date == day,
            )
        )
        session.add(
            DailySummaryRevision(
                client_id=client_id,
                summary_date=day,
                seq=(last_seq or 0) + 1,
                narrative=narrative,
                mode=mode,
            )
        )
        session.commit()
    except Exception as exc:  # noqa: BLE001 - history is best-effort
        log.warning("summary revision log failed for %s (%s)", day, exc)
    # Agenda auto-detect (agenda-detect): promote the digest's agenda
    # entries to real rows on EVERY build path (worker cut + API regen).
    # Idempotent by normalized title; failures never fail the digest.
    try:
        from app.summaries.agenda_detect import sync_agenda_from_digest

        sync_agenda_from_digest(session, client_id, content, reference=day)
    except Exception as exc:  # noqa: BLE001 - detection is best-effort
        log.warning("agenda detect failed for %s (%s)", day, exc)
    return row
