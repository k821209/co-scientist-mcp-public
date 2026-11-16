# A report, a proposal, a plan — what its reader strikes

Read this instead of `SKILL.md` §1–§6 when the document is not a journal
manuscript: a commissioned-work report, a grant or tender proposal, an
operating plan, a self-assessment form. `doc_type` is `report` or `other`, and
the reader is an office, not a journal.

## Where the ranking comes from

From what the authors of such documents struck in their own drafts: 324
comments on 30 report-type documents, 136 of them on Korean passages
(2026-11-16). Counted by what the comment asked for:

| what the comment asked for | of 136 | kind the reader reports |
|---|---|---|
| "빼자", "삭제", "이런 말은 안 쓴다" — a sentence with no use to the recipient | ~35 | `not_for_reader` |
| "뭔 말이지", "그래서 뭘 했다는 거야", "이 수가 뭘 말하는 거지" | ~17 | `unclear` |
| "이상한 표현", "다른 단어를 쓰자" | ~11 | `figurative` |
| "개조식으로", "4줄이면 안 읽어", "들여쓰기" | ~6 | `form` |
| "방법론 명시", "이게 ○○ 말하는 건가" | ~5 | `unnamed` |
| content, numbers, figures to add, administration | ~62 | not prose — not this skill's |

Two more kinds the reader carries — `overstatement` and `translationese` — are
there because these documents are prone to them. They were rare in the
comments, so they rank last and are not to be hunted at the expense of the
first three.

## The five, with the sentence each one costs

Constructed pairs in the shape of the real ones. The left column is what a
session writes; the right is what the recipient needed.

**1. `not_for_reader` — the fix is deletion.** What was not done, how the work
went, reassurance nobody asked for, the same thing twice.

| written | stands |
|---|---|
| 재작업이 필요한 시료는 없다. | (삭제) |
| 초기에는 추출 도구의 한계로 누락된 것으로 보았으나 재확인 결과 문제가 없었다. | (삭제) |
| 별도의 품질 성적서는 만들지 않고 본 보고서로 갈음한다. | (삭제), or one line in the cover note |
| 새로운 지표를 도입하여 구조 지지도를 평가하였다. | 전사체별 구조 지지도를 측정하였다. |

The author cannot see these: each records something that mattered while the
work was being done. A session's own misunderstanding, written into a plan, is
the plainest case — and the one the author is least pleased to find.

**2. `unclear` — say what was done and what the number counts.**

| written | stands |
|---|---|
| 중복 9줄을 직접 제거한 뒤 정규화하였다. | 중복된 9행을 삭제하고, ○○ 규격 검사를 통과하도록 속성 순서를 맞추었다. |
| 신규 18,934개 | 신규 locus 18,934개 |
| 위 수는 전체 판이다. | 위 수에는 증거가 없는 low 등급이 포함되어 있다. |

When the concrete fact is not in the section, the reader returns
`needs_author: yes` and the question. File it as a question, not as a rewrite.

**3. `figurative` — the literal statement.** The metaphors a session reaches
for (축, 칸, 자리, 실려 있다, 눌리고, 수렴하고) name a quality where the form
wants an arrangement, an assignment, or a count.

| written | stands |
|---|---|
| 이수 체계의 한 칸이다 | 이수 체계의 한 단계로 편성한다 |
| 깊이를 축으로 놓는다 | 수준에 따라 셋으로 구분한다 |
| 45점이 과정에 실려 있다 | 45점을 과정 평가에 배정하였다 |

**4. `form`.** Prose where the form is itemised; four lines where the reader
scans; `~한다` and `~합니다` in one unit; a row of numbers that is a table.

**5. `unnamed`.** A description where an expert recipient expects the name of
the method, the regulation, the programme. The plain-language rule of a
journal abstract runs the other way here: an evaluator who knows the field
reads a paraphrase as not knowing the name.

## What changes in the pass

- **The reader is `report-copyedit`**, handed the kind of document and who
  receives it — not a venue and a field. Both come from the paper (its
  `journal` field on a report usually holds the form or the commissioning
  body) or from the user. Never invent the recipient: without one the reader
  cannot tell an expert office from a general one, and says so in
  `BUNDLE_NOTE`.
- **`list_references` is not consulted.** The vocabulary test for a report is
  the form's own words and the recipient's field, which the reader is told.
- **A `(삭제)` suggestion is a complete finding.** File it as written.
- **English conventions do not apply** — tense rules, concession placement and
  figure-title form in `SKILL.md` are a journal's.
- A response or cover letter is neither: that is `/reviewer-frame-check`.
