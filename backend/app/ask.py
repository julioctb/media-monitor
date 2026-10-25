"""F4: natural-language questions over the mention corpus (retrieval + cited LLM answer).

The retrieval pass is deliberately dumb and inspectable: significant tokens
from the question matched against title/body (ILIKE), plus person detection
against `persons`/aliases. The LLM never invents beyond the context block —
its instructions force [n] citations into that block, and the API returns
the very mentions cited so the UI can link them.

Graceful degradation: without a configured AI provider the endpoint answers
503 with a clear detail; retrieval itself never needs a model.
"""

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Mention, Person, MentionPerson

log = logging.getLogger("ask")

#: Question words too generic to discriminate retrieval on.
STOPWORDS = frozenset(
    """
    que cual cuales como cuando donde quien quienes sobre entre para por con
    del los las una unos unos este esta estos esas esos eso esa ese han ha hay
    fue son ser estan mas le les sus su al lo os me mi
    the and what when where who which how
    dijo dice decir hablo hablar creo opina piensa
    qué cómo dónde cuándo quién cuáles más también
    """.split()
)

#: Mentions handed to the model: enough breadth, bounded tokens.
MAX_CONTEXT_MENTIONS = 24
#: Candidates fetched before the in-memory relevance cut.
CANDIDATE_POOL = 80
#: Content chars per context block (token budget guard).
SNIPPET_CHARS = 420

ASK_SYSTEM_PROMPT = (
    "Eres el analista de un monitor de medios. Responde la pregunta del "
    "usuario usando EXCLUSIVAMENTE el contexto numerado; no inventes datos "
    "ni uses conocimiento externo. Si el contexto no alcanza para responder, "
    "dilo explícitamente. Menciona las notas que sustentan cada afirmación "
    "con su marcador [n]. Las afirmaciones basadas en el bloque de resumen "
    "del día no llevan [n]; indícalas como «según el resumen del día». "
    "Responde en español, máximo 6 líneas, directo."
)


class AskError(Exception):
    """User-facing ask failure (carries an HTTP-ish message)."""

    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class AskResult:
    answer: str
    citations: list[dict] = field(default_factory=list)
    person: dict | None = None
    matched_mentions: int = 0


def tokenize(question: str) -> list[str]:
    """Significant lowercase words; dedup, drop stopwords/short tokens."""
    words = re.findall(r"[a-z0-9áéíóúñü]+", question.lower())
    seen: list[str] = []
    for word in words:
        if len(word) < 3 or word in STOPWORDS or word in seen:
            continue
        seen.append(word)
    return seen


def token_variants(token: str) -> list[str]:
    """The token plus naive singular forms; substring match covers the rest.

    "becas" must reach notes written "beca": exact matching starved the
    context of morphological neighbours. Long es/s endings are stripped.
    """
    variants = [token]
    if len(token) > 3 and token.endswith("es"):
        variants.append(token[:-2])
    if len(token) > 3 and token.endswith("s"):
        variants.append(token[:-1])
    return list(dict.fromkeys(variants))


#: Question words that name a sentiment value; "notas negativas hacia X"
#: must reach the negative linked coverage, not the latest (positive) page.
SENTIMENT_WORDS = {
    "positiva": "positive",
    "positivo": "positive",
    "positivas": "positive",
    "positivos": "positive",
    "negativa": "negative",
    "negativo": "negative",
    "negativas": "negative",
    "negativos": "negative",
    "neutral": "neutral",
    "neutro": "neutral",
    "neutra": "neutral",
}


def requested_sentiment(tokens: list[str]) -> str | None:
    """The sentiment value named in the question, if any."""
    for token in tokens:
        for variant in token_variants(token):
            if variant in SENTIMENT_WORDS:
                return SENTIMENT_WORDS[variant]
    return None


def find_persons(session: Session, client_id: int, tokens: list[str]) -> list[Person]:
    """Persons whose name/alias tokens appear in the question."""
    if not tokens:
        return []
    token_set = set(tokens)
    matches: list[tuple[int, object]] = []
    for person in session.scalars(
        select(Person).where(Person.client_id == client_id)
    ):
        name_tokens = set(person.name_key.split())
        alias_tokens = set()
        for alias in person.aliases or []:
            alias_tokens.update(re.findall(r"[a-z0-9áéíóúñü]+", alias.lower()))
        overlap = len((name_tokens | alias_tokens) & token_set)
        if overlap:
            matches.append((overlap, person))
    matches.sort(key=lambda pair: (-pair[0], pair[1].id))
    return [person for _, person in matches[:3]]


def retrieve_mentions(
    session: Session,
    *,
    client_id: int,
    tokens: list[str],
    person_ids: list[int],
    limit: int = MAX_CONTEXT_MENTIONS,
) -> tuple[list[Mention], dict[int, str]]:
    """Token OR-match over title/content, precision-cut in memory.

    Person-linked mentions join the pool even when their text misses the
    tokens (asking about a person must surface their coverage).
    """
    conditions = []
    for token in tokens:
        for variant in token_variants(token):
            pattern = f"%{variant}%"
            conditions.append(Mention.title.ilike(pattern))
            conditions.append(Mention.content.ilike(pattern))
    if person_ids:
        conditions.append(Mention.id.in_(
            select(MentionPerson.mention_id).where(
                MentionPerson.person_id.in_(person_ids)
            )
        ))
    if not conditions:
        # Nothing to match on (e.g. question of only stopwords): the latest
        # coverage is the least-wrong context.
        query = select(Mention).where(Mention.client_id == client_id)
        sentiment = requested_sentiment(tokens)
        if sentiment:
            query = query.where(Mention.sentiment == sentiment)
        return session.scalars(
            query.order_by(
                Mention.published_at.desc().nullslast(), Mention.id.desc()
            ).limit(limit)
        ).all()
    filters = [Mention.client_id == client_id, or_(*conditions)]
    sentiment = requested_sentiment(tokens)
    if sentiment:
        # "notas negativas": token matches must carry that sentiment, or the
        # latest positive page crowds the answer out.
        filters.append(Mention.sentiment == sentiment)
    candidates = session.scalars(
        select(Mention)
        .where(*filters)
        .order_by(Mention.published_at.desc().nullslast(), Mention.id.desc())
        .limit(CANDIDATE_POOL)
    ).all()

    token_set = set(tokens)

    # Person-first: mentions linked to the asked-about person get guaranteed
    # slots, ranked by recency — token matches fill the rest. A pure token
    # ranking starves exactly the rows that answer "quién es / qué hizo".
    linked: list[Mention] = []
    linked_roles: dict[int, str] = {}
    if person_ids:
        linked_filters = [
            Mention.client_id == client_id,
            MentionPerson.person_id.in_(person_ids),
        ]
        if sentiment:
            linked_filters.append(Mention.sentiment == sentiment)
        rows = session.execute(
            select(Mention, MentionPerson.role)
            .join(MentionPerson, MentionPerson.mention_id == Mention.id)
            .where(*linked_filters)
            .order_by(Mention.published_at.desc().nullslast(), Mention.id.desc())
            .limit(limit)
        ).all()
        for mention, role in rows:
            linked.append(mention)
            if role:
                linked_roles[mention.id] = role
    linked_ids = {mention.id for mention in linked}

    def score(mention: Mention) -> tuple[int, object]:
        haystack = f"{mention.title or ''} {mention.content or ''}".lower()
        token_hits = sum(
            1
            for token in token_set
            if any(variant in haystack for variant in token_variants(token))
        )
        return (token_hits, mention.published_at or mention.ingested_at)

    pool: dict[int, Mention] = {mention.id: mention for mention in linked}
    for mention in candidates:
        pool.setdefault(mention.id, mention)
    ranked = sorted(pool.values(), key=score, reverse=True)

    forced_ids = linked_ids
    rest = [mention for mention in ranked if mention.id not in forced_ids]
    merged = linked + rest
    seen: set[int] = set()
    unique: list[Mention] = []
    for mention in merged:
        if mention.id in seen:
            continue
        seen.add(mention.id)
        unique.append(mention)
    return unique[:limit], linked_roles


def build_context(
    mentions: list[Mention], linked_roles: dict[int, str] | None = None
) -> tuple[str, list[dict]]:
    """Numbered context block + the citation metadata mirror.

    `linked_roles` annotates rows where the asked-about person appears in a
    named capacity — the strongest signal for "quién es / qué hace".
    """
    linked_roles = linked_roles or {}
    blocks: list[str] = []
    citations: list[dict] = []
    for index, mention in enumerate(mentions, start=1):
        snippet = " ".join((mention.content or "").split())[:SNIPPET_CHARS]
        when = (mention.published_at or mention.ingested_at).strftime("%Y-%m-%d %H:%M")
        role_line = ""
        role = linked_roles.get(mention.id)
        if role:
            role_line = f"ROL: {role}\n"
        blocks.append(
            f"[{index}] {mention.title or '(sin título)'} — "
            f"{mention.source} — {when} — sentimiento: "
            f"{mention.sentiment.value if mention.sentiment else 'sin clasificar'}\n"
            f"{role_line}{snippet}\n{mention.url}"
        )
        citations.append(
            {
                "mention_id": mention.id,
                "title": mention.title,
                "url": mention.url,
                "source": mention.source,
                "published_at": (mention.published_at or mention.ingested_at).isoformat(),
                "sentiment": mention.sentiment.value if mention.sentiment else None,
            }
        )
    return "\n\n".join(blocks), citations


def _recent_digest_block(session: Session, client_id: int) -> str:
    """Plain text of the latest digest when it is fresh (<= 2 days).

    Grounds the answers in the editorial layer: the digest already
    synthesizes the day; stale digests are skipped, not trusted.
    """
    from datetime import date, timedelta

    from app.models import DailySummary

    row = session.scalar(
        select(DailySummary)
        .where(DailySummary.client_id == client_id)
        .order_by(DailySummary.summary_date.desc())
        .limit(1)
    )
    if row is None or row.summary_date < date.today() - timedelta(days=2):
        return ""
    plain = (row.content or {}).get("plain_text") if isinstance(row.content, dict) else None
    if not plain:
        return ""
    return f"Digest editorial reciente ({row.summary_date}):\n{plain}"


def answer_question(session: Session, *, client_id: int, question: str, enricher) -> AskResult:
    """One-shot ask: retrieve, ground, narrate. Empty question => recent feed."""
    tokens = tokenize(question)
    persons = find_persons(session, client_id, tokens)
    person_ids = [person.id for person in persons]
    mentions, linked_roles = retrieve_mentions(
        session, client_id=client_id, tokens=tokens, person_ids=person_ids
    )
    if not mentions:
        return AskResult(
            answer="No encontré menciones que coincidan con la pregunta.",
            citations=[],
            person=None,
            matched_mentions=0,
        )

    context, citations = build_context(mentions, linked_roles=linked_roles)
    person_hint = ""
    if persons:
        top = persons[0]
        mentions_n = session.scalar(
            select(func.count())
            .select_from(MentionPerson)
            .where(MentionPerson.person_id == top.id)
        )
        person_hint = (
            f" La pregunta parece referirse a: {top.name}"
            + (f" ({top.role} de {top.org})" if top.role or top.org else "")
            + (f", quien acumula {mentions_n} menciones en el monitoreo." if mentions_n else ".")
            + " Las notas marcadas ROL tienen el cargo que detenta en esa cobertura."
        )
    digest_block = _recent_digest_block(session, client_id)
    user = (
        f"Pregunta: {question.strip()}\n\n"
        f"Contexto ({len(mentions)} notas, más reciente primero):\n\n{context}"
        + (f"\n\n{digest_block}" if digest_block else "")
        + person_hint
    )
    answer = enricher.complete(ASK_SYSTEM_PROMPT, user)
    if not answer:
        raise AskError("El modelo de consulta no respondió; intenta de nuevo.", status=503)

    answer = str(answer).strip()
    # Fuentes = solo las notas que la respuesta cita con [n]; el resto era
    # contexto recuperado, no respaldo. Sin marcadores (modelo desobediente)
    # se conservan todas: mejor ruido transparente que fuentes vacías.
    cited = {
        marker
        for marker in (int(match) for match in re.findall(r"\[(\d{1,2})\]", answer))
        if 1 <= marker <= len(citations)
    }
    if cited:
        citations = [
            citation for index, citation in enumerate(citations, start=1) if index in cited
        ]

    matched = len(citations)
    return AskResult(
        answer=answer,
        citations=citations,
        person={"id": persons[0].id, "name": persons[0].name} if persons else None,
        matched_mentions=matched,
    )
