"""specs/08-rubric.md's patch ladder. D3 built P0-P2 (deterministic, zero
model calls). D4 adds P3 (rephrase, local model) and its bank-variant
writeback. P4 (accept and log to gap_ledger) is still not built: spec 08
only reaches it after P3's rewrite budget is exhausted or a rewrite is
discarded, and marking a variant `accepted: true` on a "soft" deficit is a
product judgment call (what counts as soft) this session isn't making
without asking first.

No persistence to job_resume_variants OR to the real resume/bank/aankit.yaml
here: the former needs base_resumes (E2, not built); the latter was
confirmed by asking not to wire up automatically in D4 (see D30 in
docs/decisions.md), since aankit.yaml is hand-authored and this would be
the first-ever automated write to it. apply_variants_to_bank() returns a
new in-memory Bank; persisting it anywhere is a separate, deliberate act.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from jobengine.llm import router
from jobengine.llm.schemas import LLMCallResult, LLMConfig
from jobengine.resume.bank import (
    WARN_CHAR_LIMIT,
    Bank,
    Bullet,
    BulletVariant,
    Role,
    is_past_tense,
)
from jobengine.resume.pdf import render_pdf
from jobengine.resume.render import Identity, RenderProfile, render
from jobengine.rubric import measure, rules


def _target_stems(
    required_keywords: list[str], preferred_keywords: list[str] | None
) -> set[str]:
    return {measure.stem(k) for k in required_keywords + (preferred_keywords or [])}


def _keyword_score(keywords: list[str], target_stems: set[str]) -> int:
    return len({measure.stem(k) for k in keywords} & target_stems)


# Matches a word (letters, apostrophes, hyphens) or a plain digit run. Used
# by validate_rewrite to find "claims" (proper nouns, technology names,
# numbers) rather than ordinary prose words.
_CLAIM_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]*|\d+(?:\.\d+)?")


def _claim_tokens(text: str) -> list[str]:
    return _CLAIM_TOKEN_RE.findall(text)


def _identity_text(identity: Identity) -> str:
    return " ".join(
        str(value)
        for value in (
            identity.full_name,
            identity.email,
            identity.phone,
            identity.city,
            identity.state,
            identity.linkedin,
            identity.github,
            identity.portfolio,
            identity.scholar,
            identity.work_authorization_statement,
        )
        if value
    )


def _allowed_source_text(bullet: Bullet, identity: Identity) -> str:
    return " ".join([bullet.what, bullet.how, bullet.result, _identity_text(identity)])


def validate_rewrite(
    bullet: Bullet,
    new_text: str,
    keywords_added: list[str],
    identity: Identity,
) -> list[str]:
    """CLAUDE.md hard rule 12, enforced here in code rather than trusted to
    the prompt: a P3 rewrite must not introduce any proper noun, number, or
    technology absent from the parent bullet's what/how/result or
    identity.toml. Returns a list of violation reasons; empty means the
    rewrite is safe to accept.

    Deliberately not a known-jargon allowlist (slop_lint.py's
    _TECH_JARGON_TERMS is far too narrow, ~20 terms, and would only catch
    fabrications that happen to already be on that list): any token that
    starts uppercase or is a digit run, isn't the bullet's own opening
    word (always capitalized by sentence position, never a new claim),
    and doesn't appear anywhere in the allowed source text, is rejected.
    This is stricter than spec 08's literal wording requires in some
    edge cases (e.g. a legitimate acronym coined fresh in the rewrite
    would also be rejected), which is the safe failure direction per
    CLAUDE.md hard rule 2: over-rejection costs a P3 attempt, silently
    accepting a fabricated claim would not be recoverable once the
    rewrite is in the bank.

    A keyword in keywords_added is only accepted if it is already in the
    bullet's own keywords list, or its stem already appears in the
    allowed source text (spec 08: "a keyword may only be added if the
    bank bullet's keywords list already contains it or the keyword names
    something the parent already describes")."""
    violations: list[str] = []

    allowed_source = _allowed_source_text(bullet, identity)
    allowed_tokens = {t.lower() for t in _claim_tokens(allowed_source)}

    new_tokens = _claim_tokens(new_text)
    for index, token in enumerate(new_tokens):
        if index == 0:
            continue
        if token.lower() in allowed_tokens:
            continue
        if token[0].isupper() or token[0].isdigit():
            violations.append(
                f"introduces a claim not in the parent bullet or identity.toml: {token!r}"
            )

    existing_stems = {measure.stem(k) for k in bullet.keywords}
    source_stems = {measure.stem(t) for t in _claim_tokens(allowed_source)}
    for keyword in keywords_added:
        keyword_stem = measure.stem(keyword)
        already_tagged = keyword_stem in existing_stems
        keyword_token_stems = {measure.stem(t) for t in _claim_tokens(keyword)}
        described_by_parent = bool(keyword_token_stems & source_stems)
        if not already_tagged and not described_by_parent:
            violations.append(
                f"keyword not already tagged on the bullet or described by "
                f"the parent: {keyword!r}"
            )

    return violations


_REPHRASE_PROMPT = """Rewrite this resume bullet so it naturally incorporates \
one or two of the target keywords below, but only the ones that genuinely \
fit what the bullet already describes.

what: {what}
how: {how}
result: {result}

Target keywords (incorporate at most 1-2, only if truly applicable): {target_keywords}

Rules, all mandatory:
- At most one period in the whole bullet.
- Must open in past tense.
- No first-person pronouns (I, we, my, our).
- Do not invent or imply any fact, tool, number, or claim that is not \
already present in the what/how/result fields above. A keyword may only \
be added if it names something those fields already describe.

Return the rewritten bullet text and the list of keywords you actually \
incorporated (an empty list if none genuinely apply)."""


class RephraseSchema(BaseModel):
    text: str
    keywords_added: list[str] = []


async def call_rephrase(
    bullet: Bullet,
    target_keywords: list[str],
    config: LLMConfig,
    *,
    local_client: Any | None = None,
) -> LLMCallResult:
    """The only place this module talks to an LLM. Input is exactly the
    bullet's what/how/result fields and the target keywords, per spec 08's
    explicit P3 constraint: never the whole bank, never the JD text."""
    provider = router.get_provider("rephrase", config, local_client=local_client)
    return await provider.call(
        stage="rephrase",
        messages=[
            {
                "role": "user",
                "content": _REPHRASE_PROMPT.format(
                    what=bullet.what,
                    how=bullet.how,
                    result=bullet.result,
                    target_keywords=", ".join(target_keywords),
                ),
            }
        ],
        schema=RephraseSchema,
    )


def _run_rephrase(
    bullet: Bullet,
    target_keywords: list[str],
    config: LLMConfig,
    *,
    local_client: Any | None = None,
) -> LLMCallResult:
    """Sync wrapper so run_ladder (an orchestration entry point, like
    sources/sync.py's sync()) stays a plain function; call_rephrase itself
    stays async, matching router.call()'s own leaf-function convention."""
    return asyncio.run(
        call_rephrase(bullet, target_keywords, config, local_client=local_client)
    )


def _with_bullet_rewrite(
    bank: Bank,
    role_id: str,
    bullet_id: str,
    new_text: str,
    keywords_added: list[str],
) -> Bank:
    """Applies an accepted P3 rewrite to this specific tailored candidate:
    both the text AND the keyword tags change, since an accepted
    keywords_added is exactly the claim that this rewrite now covers that
    keyword. Without merging into .keywords here, R001's coverage math
    would never see the improvement a successful P3 rewrite was supposed
    to produce, since coverage() reads bullet.keywords, not bullet.text.
    The canonical full_bank's bullet.keywords is never touched by this;
    only the transient working candidate used for this job's render/
    score is."""
    new_roles = []
    for role in bank.roles:
        if role.id != role_id:
            new_roles.append(role)
            continue
        new_bullets = []
        for b in role.bullets:
            if b.id != bullet_id:
                new_bullets.append(b)
                continue
            merged_keywords = list(b.keywords)
            existing_stems = {measure.stem(k) for k in merged_keywords}
            for kw in keywords_added:
                if measure.stem(kw) not in existing_stems:
                    merged_keywords.append(kw)
                    existing_stems.add(measure.stem(kw))
            new_bullets.append(
                b.model_copy(update={"text": new_text, "keywords": merged_keywords})
            )
        new_roles.append(role.model_copy(update={"bullets": new_bullets}))
    return bank.model_copy(update={"roles": new_roles})


def _select_p3_target(candidate: Bank) -> tuple[str, Bullet] | None:
    """spec 08: "pick the one selected bullet with the most room (fewest
    keywords, shortest rendered length)." Rendered length is approximated
    by character count (bank.py's own R006 fallback estimate), not a real
    render, since P3's own selection step should stay cheap. Ties broken
    by original bank order for determinism (Python's min() returns the
    first minimal element)."""
    candidates = [
        (role.id, bullet) for role in candidate.roles for bullet in role.bullets
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda pair: (len(pair[1].keywords), len(pair[1].text)))


def _best_existing_variant(
    bullet: Bullet, missing_keywords: list[str]
) -> BulletVariant | None:
    """spec 08: "the selector prefers an existing variant over a new P3
    call." Picks whichever existing variant's keywords_added best
    overlaps the current missing keywords; None if no variant covers any
    of them, in which case a new call is warranted."""
    missing_stems = {measure.stem(k) for k in missing_keywords}
    scored = [
        (len({measure.stem(k) for k in v.keywords_added} & missing_stems), v)
        for v in bullet.variants
    ]
    scored = [(score, v) for score, v in scored if score > 0]
    if not scored:
        return None
    return max(scored, key=lambda pair: pair[0])[1]


def _passes_prose_gates(candidate_with_rewrite: Bank, new_text: str) -> list[str]:
    """R005 (<=1 period), R006 (char-count estimate: spec 08's own stated
    fallback for when no render exists yet, used deliberately here rather
    than a full render+PDF-convert per candidate rewrite, which would be
    real scope creep beyond P3's cheap, fast-iteration design; the
    ladder's own subsequent re-render/re-score step independently
    re-verifies R006 with real PDF geometry like any other rule), R007
    (past tense), R008 (no first-person pronoun), and the full slop
    linter (reusing rules.check_r013 against the whole candidate with
    this one bullet substituted in, so role-level checks like H004's 3-8
    count see real context, not an artificial single-bullet role)."""
    problems: list[str] = []
    if new_text.count(".") > 1:
        problems.append("R005: more than one period")
    if len(new_text) > WARN_CHAR_LIMIT:
        problems.append(f"R006 (char estimate): over {WARN_CHAR_LIMIT} chars")
    if not is_past_tense(new_text):
        problems.append("R007: does not open in past tense")
    if measure.has_first_person_pronoun(new_text):
        problems.append("R008: first-person pronoun")

    lint_result = rules.check_r013(candidate_with_rewrite)
    if lint_result is not None:
        problems.append(f"slop linter: {lint_result.detail}")
    return problems


class P3Attempt(BaseModel):
    role_id: str
    bullet_id: str
    text: str
    keywords_added: list[str]
    reused_existing_variant: bool
    accepted: bool
    reason: str | None = None


def apply_p3(
    candidate: Bank,
    full_bank: Bank,
    missing_keywords: list[str],
    identity: Identity,
    llm_config: LLMConfig | None,
    *,
    max_calls: int = 2,
    local_client: Any | None = None,
) -> tuple[Bank, list[P3Attempt]]:
    """P3: rephrase, local model. Only meaningful once P0-P2 leave hard
    failures (missing_keywords non-empty) and an LLM config is actually
    given; a caller that omits llm_config gets P0-P2 behavior unchanged.
    Picks the bullet with the most room, prefers an existing variant over
    a new call, validates every candidate hard (validate_rewrite's
    traceability guard, then R005/R006/R007/R008 + the slop linter), and
    stops at the first accepted rewrite rather than always spending both
    calls: the ladder's own re-score after this tier decides whether one
    rewrite was enough. Discarded attempts still count against
    max_calls (each is a real LLM call already spent), but a reused
    existing variant does not, since it costs nothing."""
    if llm_config is None or not missing_keywords:
        return candidate, []

    attempts: list[P3Attempt] = []
    calls_made = 0
    working = candidate
    attempted_bullet_ids: set[str] = set()

    while calls_made < max_calls:
        target = _select_p3_target(working)
        if target is None:
            break
        role_id, bullet = target
        if bullet.id in attempted_bullet_ids:
            break
        attempted_bullet_ids.add(bullet.id)

        full_role = next((r for r in full_bank.roles if r.id == role_id), None)
        canonical_bullet = bullet
        if full_role is not None:
            canonical_bullet = next(
                (b for b in full_role.bullets if b.id == bullet.id), bullet
            )

        existing = _best_existing_variant(canonical_bullet, missing_keywords)
        if existing is not None:
            text, keywords_added, reused = existing.text, existing.keywords_added, True
        else:
            result = _run_rephrase(
                bullet, missing_keywords[:2], llm_config, local_client=local_client
            )
            calls_made += 1
            reused = False
            try:
                parsed = RephraseSchema.model_validate(result.output)
            except ValidationError as exc:
                attempts.append(
                    P3Attempt(
                        role_id=role_id,
                        bullet_id=bullet.id,
                        text="",
                        keywords_added=[],
                        reused_existing_variant=False,
                        accepted=False,
                        reason=f"LLM output failed schema validation: {exc}",
                    )
                )
                continue
            text, keywords_added = parsed.text, parsed.keywords_added

        violations = validate_rewrite(canonical_bullet, text, keywords_added, identity)
        if violations:
            attempts.append(
                P3Attempt(
                    role_id=role_id,
                    bullet_id=bullet.id,
                    text=text,
                    keywords_added=keywords_added,
                    reused_existing_variant=reused,
                    accepted=False,
                    reason="; ".join(violations),
                )
            )
            continue

        candidate_with_rewrite = _with_bullet_rewrite(
            working, role_id, bullet.id, text, keywords_added
        )
        prose_problems = _passes_prose_gates(candidate_with_rewrite, text)
        if prose_problems:
            attempts.append(
                P3Attempt(
                    role_id=role_id,
                    bullet_id=bullet.id,
                    text=text,
                    keywords_added=keywords_added,
                    reused_existing_variant=reused,
                    accepted=False,
                    reason="; ".join(prose_problems),
                )
            )
            continue

        working = candidate_with_rewrite
        attempts.append(
            P3Attempt(
                role_id=role_id,
                bullet_id=bullet.id,
                text=text,
                keywords_added=keywords_added,
                reused_existing_variant=reused,
                accepted=True,
            )
        )
        break

    return working, attempts


def apply_variants_to_bank(full_bank: Bank, attempts: list[P3Attempt]) -> Bank:
    """Pure, in-memory: returns a new Bank with each accepted P3Attempt
    recorded on its target bullet's variants list (creating a new
    BulletVariant, or incrementing used_count if the exact same text was
    reused from an existing one), never touching the bullet's own
    canonical `text`. Does not write to any file; persisting the result
    is a separate, deliberate action (see this module's own docstring for
    why that isn't wired up automatically here)."""
    accepted = [a for a in attempts if a.accepted]
    if not accepted:
        return full_bank

    now = datetime.now(UTC).date().isoformat()
    new_roles = []
    for role in full_bank.roles:
        role_attempts = [a for a in accepted if a.role_id == role.id]
        if not role_attempts:
            new_roles.append(role)
            continue

        new_bullets = []
        for bullet in role.bullets:
            bullet_attempts = [a for a in role_attempts if a.bullet_id == bullet.id]
            if not bullet_attempts:
                new_bullets.append(bullet)
                continue

            variants = list(bullet.variants)
            for attempt in bullet_attempts:
                existing = next(
                    (v for i, v in enumerate(variants) if v.text == attempt.text), None
                )
                if existing is not None:
                    idx = variants.index(existing)
                    variants[idx] = existing.model_copy(
                        update={"used_count": existing.used_count + 1}
                    )
                else:
                    variants.append(
                        BulletVariant(
                            text=attempt.text,
                            keywords_added=attempt.keywords_added,
                            created_at=now,
                            used_count=1,
                        )
                    )
            new_bullets.append(bullet.model_copy(update={"variants": variants}))
        new_roles.append(role.model_copy(update={"bullets": new_bullets}))

    return full_bank.model_copy(update={"roles": new_roles})


def _swap_overlapping_roles(roles: list[Role], target_stems: set[str]) -> list[Role]:
    """P0's role-level reordering: adjacent roles may only swap if their
    date ranges genuinely overlap (measure.roles_date_overlap), which is
    exactly the condition under which measure.is_reverse_chronological
    tolerates either order. Repeated passes so a score improvement can
    propagate through a chain of overlapping neighbors, not just one
    adjacent pair."""
    roles = list(roles)
    scores = {
        r.id: sum(_keyword_score(b.keywords, target_stems) for b in r.bullets)
        for r in roles
    }
    changed = True
    while changed:
        changed = False
        for i in range(len(roles) - 1):
            a, b = roles[i], roles[i + 1]
            if measure.roles_date_overlap(a, b) and scores[b.id] > scores[a.id]:
                roles[i], roles[i + 1] = b, a
                changed = True
    return roles


def apply_p0(
    candidate: Bank,
    required_keywords: list[str],
    preferred_keywords: list[str] | None = None,
) -> Bank:
    """P0: reorder, free. Bullets within each role sorted by descending
    keyword score (Python's sort is stable, so ties keep their original
    order). Roles reordered only among genuinely overlapping pairs (never
    project roles, confirmed scope: project-section ordering is P2's job,
    not an automatic P0 one), never breaking R009."""
    target_stems = _target_stems(required_keywords, preferred_keywords)

    reordered = []
    for role in candidate.roles:
        sorted_bullets = sorted(
            role.bullets,
            key=lambda b: _keyword_score(b.keywords, target_stems),
            reverse=True,
        )
        reordered.append(role.model_copy(update={"bullets": sorted_bullets}))

    non_project = [r for r in reordered if r.kind != "project"]
    project = [r for r in reordered if r.kind == "project"]
    non_project = _swap_overlapping_roles(non_project, target_stems)

    return candidate.model_copy(update={"roles": non_project + project})


def apply_p1(
    candidate: Bank,
    full_bank: Bank,
    profile: str,
    required_keywords: list[str],
    preferred_keywords: list[str] | None = None,
) -> Bank:
    """P1: swap, free. For each still-globally-missing required keyword,
    swap the lowest-scoring selected bullet in a role for the
    highest-scoring not-yet-selected same-role bullet (from the full
    bank, tagged for this profile) that carries it. Bullet count per role
    never changes, so R003 is preserved by construction. Roles processed
    in their current order (P0 already decided that order), so an earlier
    role's swap resolves a keyword before a later role gets a chance at
    it: "prefer swaps in the first role" falls out of this directly."""
    target_stems = _target_stems(required_keywords, preferred_keywords)
    required_stems = {measure.stem(k) for k in required_keywords}
    full_roles_by_id = {r.id: r for r in full_bank.roles}

    working_roles = [role.model_copy() for role in candidate.roles]

    def _covered_stems() -> set[str]:
        return {
            measure.stem(k)
            for role in working_roles
            for b in role.bullets
            for k in b.keywords
        }

    for i, role in enumerate(working_roles):
        full_role = full_roles_by_id.get(role.id)
        if full_role is None:
            continue

        current_bullets = list(role.bullets)
        selected_ids = {b.id for b in current_bullets}

        candidates_by_stem: dict[str, list[Bullet]] = {}
        for b in full_role.bullets:
            if b.id in selected_ids or profile not in b.profiles:
                continue
            for s in {measure.stem(k) for k in b.keywords}:
                candidates_by_stem.setdefault(s, []).append(b)

        still_missing = required_stems - _covered_stems()
        for missing_stem in sorted(still_missing & candidates_by_stem.keys()):
            if not current_bullets:
                break
            best_candidate = max(
                candidates_by_stem[missing_stem],
                key=lambda b: _keyword_score(b.keywords, target_stems),
            )
            lowest = min(
                current_bullets, key=lambda b: _keyword_score(b.keywords, target_stems)
            )
            idx = current_bullets.index(lowest)
            current_bullets[idx] = best_candidate

        working_roles[i] = role.model_copy(update={"bullets": current_bullets})

    return candidate.model_copy(update={"roles": working_roles})


def apply_p2(
    candidate: Bank,
    section_order: list[str],
    required_keywords: list[str],
    preferred_keywords: list[str] | None = None,
) -> tuple[Bank, list[str]]:
    """P2: promote, free. Targets keywords whose only occurrence isn't in
    the current first role of the current first section (a positional
    proxy for "below the fold," since P2 decides before any PDF exists to
    measure real y-coordinates against; the ladder re-renders and
    re-scores after every tier, so the real R002 check is what actually
    confirms whether this helped). Promotes the whole section if the
    source lives in a different section, and additionally promotes the
    source role within its own group only when that role is a project
    (no R009 constraint); a work-history role that isn't already its
    section's first role is left in place, since moving it could violate
    R009 and D3's confirmed scope doesn't include R009-aware role
    promotion."""
    target_stems = _target_stems(required_keywords, preferred_keywords)
    new_section_order = list(section_order)
    if not new_section_order or not candidate.roles:
        return candidate, new_section_order

    def _section_of(role: Role) -> str:
        return "projects" if role.kind == "project" else "work_history"

    first_section = new_section_order[0]
    first_section_roles = [
        r for r in candidate.roles if _section_of(r) == first_section
    ]
    first_role = first_section_roles[0] if first_section_roles else None
    first_role_stems = (
        {measure.stem(k) for b in first_role.bullets for k in b.keywords}
        if first_role is not None
        else set()
    )

    not_front_loaded = target_stems - first_role_stems
    if not not_front_loaded:
        return candidate, new_section_order

    source_role = next(
        (
            r
            for r in candidate.roles
            if (first_role is None or r.id != first_role.id)
            and (
                {measure.stem(k) for b in r.bullets for k in b.keywords}
                & not_front_loaded
            )
        ),
        None,
    )
    if source_role is None:
        return candidate, new_section_order

    source_section = _section_of(source_role)
    if source_section != first_section:
        new_section_order.remove(source_section)
        new_section_order.insert(0, source_section)

    new_roles = list(candidate.roles)
    if source_role.kind == "project":
        projects = [r for r in new_roles if r.kind == "project"]
        rest = [r for r in new_roles if r.kind != "project"]
        projects.sort(key=lambda r: r.id != source_role.id)
        new_roles = projects + rest

    return candidate.model_copy(update={"roles": new_roles}), new_section_order


class PatchResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tiers_applied: list[str]
    passed: bool
    bank: Bank
    section_order: list[str]
    docx_path: Path
    pdf_path: Path
    rubric_result: rules.RubricResult
    p3_attempts: list[P3Attempt] = []


def run_ladder(
    *,
    full_bank: Bank,
    profile: str,
    identity: Identity,
    section_order: list[str],
    out_dir: Path,
    required_keywords: list[str],
    preferred_keywords: list[str] | None = None,
    llm_config: LLMConfig | None = None,
    local_client: Any | None = None,
) -> PatchResult:
    """Attempt P0, then P0+P1, then P0+P1+P2, then (only if llm_config is
    given) P0+P1+P2+P3, in order, stopping at the first that clears all
    hard rules. Every tier re-renders (real docx + real PDF via A4b) and
    re-scores through D1's real score_resume(), not a cheaper
    approximation, per spec 08's "every tier re-runs the full rubric
    afterward." Omitting llm_config reproduces D3's exact P0-P2-only
    behavior; P3 never fires without an explicit config, so no caller
    accidentally spends a model call."""
    preferred_keywords = preferred_keywords or []
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate = measure.select_for_profile(full_bank, profile)
    current_section_order = list(section_order)

    tiers: list[tuple[str, object]] = [
        (
            "P0",
            lambda bank, order: (
                apply_p0(bank, required_keywords, preferred_keywords),
                order,
            ),
        ),
        (
            "P1",
            lambda bank, order: (
                apply_p1(
                    bank, full_bank, profile, required_keywords, preferred_keywords
                ),
                order,
            ),
        ),
        (
            "P2",
            lambda bank, order: apply_p2(
                bank, order, required_keywords, preferred_keywords
            ),
        ),
    ]

    tiers_applied: list[str] = []
    result: rules.RubricResult | None = None
    docx_path = pdf_path = None
    p3_attempts: list[P3Attempt] = []

    for tier_name, tier_fn in tiers:
        candidate, current_section_order = tier_fn(candidate, current_section_order)
        tiers_applied.append(tier_name)

        render_profile = RenderProfile(
            section_order=current_section_order, include_summary=False
        )
        doc = render(candidate, identity, render_profile)
        docx_path = out_dir / f"candidate_{'_'.join(tiers_applied)}.docx"
        doc.save(docx_path)
        pdf_path = render_pdf(docx_path, out_dir)

        result = rules.score_resume(
            bank=candidate,
            profile=profile,
            docx_path=docx_path,
            pdf_path=pdf_path,
            required_keywords=required_keywords,
            preferred_keywords=preferred_keywords,
        )
        if result.passed:
            break

    assert result is not None and docx_path is not None and pdf_path is not None

    if not result.passed and llm_config is not None:
        missing = measure.missing_keywords(candidate, required_keywords)
        if missing:
            candidate, p3_attempts = apply_p3(
                candidate,
                full_bank,
                missing,
                identity,
                llm_config,
                local_client=local_client,
            )
            # "P3" is recorded as attempted here regardless of outcome,
            # matching P0/P1/P2's own convention (always appended even if
            # that tier changed nothing); only re-render/re-score if an
            # accepted rewrite actually changed the candidate, since a
            # fully-discarded attempt (see D29/D30) leaves it identical.
            tiers_applied.append("P3")
            if any(a.accepted for a in p3_attempts):
                doc = render(candidate, identity, render_profile)
                docx_path = out_dir / f"candidate_{'_'.join(tiers_applied)}.docx"
                doc.save(docx_path)
                pdf_path = render_pdf(docx_path, out_dir)
                result = rules.score_resume(
                    bank=candidate,
                    profile=profile,
                    docx_path=docx_path,
                    pdf_path=pdf_path,
                    required_keywords=required_keywords,
                    preferred_keywords=preferred_keywords,
                )

    return PatchResult(
        tiers_applied=tiers_applied,
        passed=result.passed,
        bank=candidate,
        section_order=current_section_order,
        docx_path=docx_path,
        pdf_path=pdf_path,
        rubric_result=result,
        p3_attempts=p3_attempts,
    )
