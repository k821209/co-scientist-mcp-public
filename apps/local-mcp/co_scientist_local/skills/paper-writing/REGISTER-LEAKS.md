# The four leaks — what the author actually corrects

Read this before drafting a section and **again before editing one in
response to a comment.** `REGISTER-BIO-AI.md` says what journal prose sounds
like in this field; this file says what goes wrong anyway. Both were written
for the same reason: the rules in SKILL.md were loaded and followed, and the
manuscript still came back marked.

**Where it comes from.** Every comment the author has written on AI-drafted
prose, and every before/after pair those comments produced: 818 comments and
653 edits across 59 papers and reports, to 2026-10-08. The ranking below is
that corpus's ranking, not a guess about what matters.

| what the author wrote | how often |
|---|---|
| delete this / you don't need to say this (빼자, 삭제, 안써도 됨, 첨언 빼자) | 119 |
| I can't tell what this sentence means (뭔말임, 말이 어렵다) | 50 |
| define this / expand this abbreviation (약자 풀자, 뭔 뜻이지) | 29 |
| this is said already (중복, 앞에서 한말인듯) | 15 |
| this belongs in the other section | 15 |
| where did this number come from (어디서 온거지) | 8 |
| this is our talk, not the reader's (우리끼리 이야기, 독자는 모르지) | 8 |
| this is spoken, not written (구어체 같다) | 7 |

The largest category by a factor of two is **deletion**, and almost none of
it is wordiness. It is sentences addressed to the wrong reader: to the
comment, to the session, or to a reviewer the author is arguing with inside
their head. That is the single idea behind all four leaks below.

---

## Leak 1 — the aside that defends a claim standing on its own

The biggest class in the corpus, and the one most likely to be re-flagged
after you fix something else. A claim is made; a clause is then appended
that qualifies, disclaims, pre-empts or justifies it. The author deletes the
clause and keeps the claim.

Five shapes, all verbatim, all deleted:

- **The reading instruction.** "the 100% figure above is closed-set
  Leave-One-Out accuracy and should not be read as open-world field
  accuracy" → *"이런말은 지적사항쓸때 하는거 아닌가 여기서는빼라"*. And
  "Without a negative class, an enrichment p-value would not mean what it
  appears to mean."
- **The pre-emptive limit.** "This comparison has two limits." → *"이런말을
  뭔 의도지? 리뷰어한테 걸리기전에 먼저 이야기한다 이런 말인가? 레서폰스
  레터에 이런말을 안쓰지."*
- **The scope disclaimer.** ", so it is not a substitute for SNP-level GWAS
  and is not designed to maximise genomic-selection accuracy"; "Gene-Miner
  occupies a deliberately narrow niche." → *"쓸데가 좁다고 생각할 수도?"*;
  "is the wrong choice where close reproduction matters more than extension"
  → *"누가 자기 소프트웨어 논문에 wrong choice 같은 소릴 쓰지?"*
- **Our own honesty, advertised.** ", and we should say so rather than
  present them as new." → *"인공지능의 정직성을 여기다 자랑하지마라. ㅡㅡ;"*
  Also "We report the 8.1% as plainly as the 91.9%", "…guaranteeing that
  reported accuracy reflects genuine learning", "so that no result can come
  from a trained head fitting the labels" → *"leakage를 막는건 당연한거라서,
  leakage가 없다는걸 자랑하지말고 구조를 서술만 하면된다."* Doing the
  analysis correctly is the baseline, not a finding.
- **The internal benchmark.** "A lighter two-stream configuration finishes
  in a few hours"; "All runs timed here used one workstation with 24 CPU
  cores and 62 GB of RAM." → *"이런말은 독자들은 모르지. 우리끼리의 연구의
  전 분석을 이야기할 필요가 있나."*

**The test.** Delete the clause. If the claim still stands and nothing false
remains, it was an aside — the deletion is the fix, not a shorter version of
the aside. A real limitation belongs in the Discussion's limitations
paragraph once, as a statement; it does not ride along with each claim.

**State what was done, not what was not.** "MDSearch was not benchmarked."
drew *"우리가 한걸 강조해서 써야지 안한걸 강조하는 애가 어딧니."* — and in a
Korean report, "read 수준 품질검사는 아직 수행하지 않았으며" drew *"뭘
안했다는 이야기는 보고서에 안쓴다."* The author's general form of the rule:
*"우리가 발명한게 아니다 라고 말하기 보다는 이는 어느 방법을 따랏다 라고
쓰자. 부정어를 최소화."* Minimise negation. Where a declined request must be
named in a response letter, name it with its reason in the same breath —
`/response-letter` has the worked form.

## Leak 2 — the answer that became a clause (the revision leak)

This is why revision leaks more than drafting. The loop, traced through the
corpus three times on single sentences:

1. The author comments *"뭔말임?"* on a sentence.
2. The sentence is kept and **the answer is appended to it** as a new clause.
3. The author flags the result as an aside, a duplicate, or still unreadable.

One real chain: *"K가 1일때는 어찌 계산됨?"* produced "the sweep starts at
K = 3 because K = 1 would be the same setting as K = 0", which drew
*"지우자."* Another: *"뭔말인지 모르겟다"* produced "The chance adjustment is
not biased against fragmented genes, in that their typical adjusted value is
no lower than other genes'", which drew *"여전히 말이 어려운데... 뭔말이야"*.
The accepted version threw the sentence away and wrote the event: "Fragmentation
does not lower the score a gene typically gets. It lowers the highest score a
gene can get."

**A comment asking what a sentence means is a report that the sentence
failed.** It is not a request for an explanatory clause. Rewrite that
sentence so the question cannot arise; if the answer is a fact the reader
needs, it is a sentence of its own, in the place where the reader first needs
it — usually earlier, often in Methods.

**Then re-read the paragraph, not the sentence.** Every duplication the
author caught in a revision round was a clause that answered one comment and
restated a neighbouring sentence: *"이거 앞에서 언급한듯"*, *"앞의 문장과
중복 아님?"*, *"앞에서 한말인듯? 숫자만 빼고"*.

## Leak 3 — session context presented as paper context

The author's own phrasing for this is *"논문 맥락이 아니라 대화 맥락에
의존한다"*. Four kinds, in order of severity.

- **A session incident stated as a fact about the field.** The gravest,
  because it is a fabricated claim, not a style defect. "The obstacle is
  sparsity: with 90–95% zeros per cell, any per-cell tokenization of
  expression is unstable" → *"이건 사실이 아닌듯, 이건 우리 분석과정 중에
  일어낫던일이지."* And "most multi-task deep learning architectures
  combining classification with self-supervised objectives suffer
  information leakage" → *"이것도 사실일것 같지 않은데, 우리 분석과정 기억
  아님?"* A sentence of the form *X is unstable / X suffers from Y* is a
  literature claim and needs a citation. If its only source is something that
  happened in this session, it is either a result of yours — reported with
  its evidence — or it is nothing.
- **Our own earlier misreading, written up as background.** "결함의 원인은
  OCR이 아닙니다" → *"분석중에 니가 오해했던걸 계획서에 넣을 이유가
  없잖아."*
- **The workshop floor.** Repo paths ("Analysis scripts are in
  analysis/structure_corrected_ami/…" → *"레스폰스 레터에 이게 들어가면
  안되지"*), script names in parentheses, `random_state`, manifest tables,
  core counts, and implementation trivia: "(the field name `query_from` is
  retained from the BLAST JSON output)", "the **byte-identical** soft-masked
  genome" → *"byte 라는건 왜 쓴거야"*. Also code-comment reasoning: "Token
  order is reshuffled at every access" → *"이건 코드에나 쓰는 가이드. 논문에
  안쓴다."*
- **Vocabulary coined mid-session, used as if defined.** *arm*, *setting*,
  *sweep*, *scan*, *axis*, *stream*, *tier*, *breadth*, *absorbed r²*, *the
  same-species core* each drew a bare *"이게 뭔 뜻으로 쓴거지"* or *"이걸
  앞으로 우리가 이렇게 부르겠다는 뜻으로 쓴 거니"*. A term invented while
  working is invisible to you and opaque to everyone else. Either define it
  at first use as a definition ("we call this the *same-species core*") or
  use the field's word. `REGISTER-BIO-AI.md` §3 lists the ones already
  rejected; SKILL.md §2c has the first-use audit that catches the rest.

## Leak 4 — the spoken sentence

Only seven comments say *구어체* outright, but they point at a recurring
shape rather than a word list. The flagged originals, verbatim:

| flagged | accepted |
|---|---|
| "but the method matters too." | "though the merging method also contributes" |
| "This is context for where the candidates sit, not validation of them, and the manuscript says so." | "The manuscript presents this overlap as context rather than as evidence for the candidates." |
| "because with that many categories that much mutual information is what chance produces." | "because a locus divided into this many categories reaches that level by chance alone." |
| "that played no part in building them" | "evidence independent of how they were built" |
| "what resolving the constraint would **buy**" | "what resolving the constraint would achieve" |

What they have in common: the sentence addresses someone. It concedes mid-stream
("…, but X matters too"), it reports that the paper agrees with itself ("and the
manuscript says so"), it reaches for an idiom where a measurement belongs, or it
explains itself in a trailing causal clause the way speech does.

Idioms the author has stopped, beyond the imported metaphors in SKILL.md §2a:
*buy*, *room to shuffle*, *runs away without bound*, *knife-edge*,
*data-hungry* (*"헝그리는 좀 말이 그렇지 않냐?"*), *exists to surface*,
*by eye*, *% of the time*, *turns out*, *the point is*, *which is what makes*.

**Headings are sentences too.** "Why the two methods differ at *E2*." drew
*"왜 두 메서드의 결과가 다른가? 라고 풀어써야지. 누가 알아봄"* — a noun phrase
used as a statement reads as a slide title.

---

## Do not over-correct

Every item here was corrected in the opposite direction at least once, so
these are not licences to strip:

- **Field-standard terms stay.** GWAS, BLUP, BUSCO, plastome, pseudo-bulk are
  the readers' shared vocabulary. Leak 3 is about words coined in the session,
  not about technical words.
- **A number keeps its scale and its owner.** The commonest repair in the
  corpus is the opposite of deletion: "libraries" → "the same four RNA-seq
  libraries used to build the catalogue"; "λ falls from 7.03 to 1.23" →
  "**For the PLINK scan**, λ falls…". Cutting an aside never means cutting the
  clause that makes a number checkable (SKILL.md §2c).
- **A conceded limit, once and in its place, is required.** The objection is to
  conceding inside every claim, and to volunteering limits a reviewer has not
  raised.
- **Plain is not colloquial.** Correcting estimator-voice overshoots into
  conversation; both axes have to hold at once, which is why
  `lint_manuscript` ships `estimator_voice` and `colloquial_register`
  together.

## The mechanical pass

`lint_manuscript(slug)` covers the regex-able part of all four leaks —
`defensive_aside`, `insider_context`, `colloquial_register`, `estimator_voice`,
`duplication`, `section_leakage`. Run it before resolving any comment, not only
before declaring a section done: a revised section has not been through it.

**Know what it is worth.** Replayed over this corpus, those rules fire on 7% of
the passages the author flagged and on 1.5% of the passages that survived — so
they are specific, and they are not coverage. The other 93% is semantic: an
undefined referent, an opaque comparison, a number with no owner, a sentence
answering the wrong reader. No regex reaches those, and the two most damaging
leaks (an answer appended as a clause; a session incident written as a fact
about the field) are both in that 93%. They need the whole-paragraph re-read
after every edit, and `/cold-read` or `/prose-review` on a finished draft.

Of the handful of passages where the rules fire on text that had already been
accepted, most were deleted by the author one round later — the lint catching,
early, exactly the clause that Leak 2 produces.
