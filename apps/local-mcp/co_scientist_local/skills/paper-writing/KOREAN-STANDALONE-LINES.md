# Korean: a line that stands alone

_Part of `/paper-writing`. Read from `SKILL.md` when drafting Korean titles, headers, table headers, figure titles, slide lines._

### 2d-quater-bis. Korean: in a line that stands alone, keep the subject and the object

Korean drops what the context restores, and in speech that is right. A
slide title, a table-of-contents item, a question line, a table header, a
figure title, a card's headline stand with no sentence before them — there
is no context to restore from. "또 목적어도 주어도 없는 문장들 있네" (a user,
on 16 of 31 slides). Keep **who / what / about what** inside the line, even
when the previous sentence would restore it.

| 나쁨 | 좋음 |
|---|---|
| 목록 맨 위가 실제로 맞는가 | 모델이 매긴 후보 목록의 상위 몇 개가 실제로 그 기관에서 켜지는가 |
| 모델이 프로모터의 어디를 보고 매기는가 | 모델은 프로모터의 어느 자리를 보고 점수를 매기는가 |
| 적응시키면 나아집니다 | 어댑터를 얹으면 프로모터를 더 잘 읽습니다 |
| 기관에 따라 크게 다릅니다 | 발굴 정밀도는 기관에 따라 크게 다릅니다 |
| 점수는 몇 군데가 만듭니다 | 프로모터 2 kb 중 몇 자리가 점수를 만듭니다 |

The self-check: write the line alone on paper and show it to someone; if
"무엇이?" or "무엇을?" comes back, fix it. **This rule is the pair of
§2d-quinque's deictic rule**: deleting "그" from "그 목록의 맨 위가" and
stopping leaves an omitted-subject line — the name the deictic pointed at
has to go in its place ("후보 목록"). Noun-phrase titles have no predicate
and are exempt ("우리가 틀렸던 자리 셋", "후보 목록을 만드는 절차").
`lint_manuscript` flags a short Korean predicate line with no case particle
as `omitted_argument`, headings included.
