# Captions and legends

_Part of `/paper-writing`. Read from `SKILL.md` before writing or trimming any caption or legend, and whenever `lint_legends` fires._

### 2d-quater. Trimming a caption can delete the paper's method

Before cutting anything from a caption or legend, check whether the value exists
anywhere else. A caption can be the **sole carrier** of a parameter, and every
other lint flag here (`long`, `interpretive`, `bare_cross_reference`) invites
deletion.

This nearly shipped: a Figure 6 legend carried "projected … with **± 250 kb
padding**". It reads exactly like method detail whose home is Methods — but
Methods never stated it (it stated a *different* 100 kb constant, for a separate
upstream step), and the paper's headline number depended on it entirely:

| padding | candidates inside a QTL |
|---|---|
| 0 kb | 188/474 = 39.7% |
| 100 kb | 196/474 = 41.4% |
| **250 kb** | **213/474 = 44.9%** ← the manuscript's number |
| 1 Mb | 256/474 = 54.0% |

`lint_legends` flags this as **`caption_only`** — relocate, do not delete (its
description has the rule).

Two rules follow:

- **A value that depends on a tunable parameter states the parameter AND how much
  the value moves with it.** "44.9% at ± 250 kb, 39.7% unpadded, 54.0% at ± 1 Mb"
  is one sentence and pre-empts "why 250 kb?" at review.
- **State the predicate**, not just the threshold. "Inside a QTL" has two equally
  natural readings — the gene's start point contained in the interval, or its span
  intersecting it. They disagree (one gene, 8 QTL vs 10), the headline percentage
  was identical either way, so no numeric check could ever catch it, and a
  reproducer is left guessing.

#### What belongs where

| Keep in the caption | Move to Methods | Move to Results/Discussion | Delete |
|---|---|---|---|
| panel letters and what each shows; visual encodings (colour, shape, line style, size); axis definitions; `n`; values that appear ONLY in the figure; a note that prevents misreading the panel ("an empty cell means no study reported a QTL there") | test names, correction procedures, software + versions, iteration/restart counts, thresholds, merge conventions, annotation-source IDs, and **any predicate a number depends on** | derived statistics the text already quotes; interpretation; generalisability caveats | only sentences duplicated near-verbatim from a body section — exactly what `body_duplication` enumerates |

Worked example, a table caption 200 → 66 words: the stage list, `52.1 ± 8.5 s`,
`~3.6× faster` and `~64× less RAM` all came out because **each is a cell in the
table itself**; the incremental-append argument came out because it is a
Discussion paragraph. Nothing was lost — because every token was verified present
elsewhere first, which is the check `caption_only` automates.

#### 2d-quinquies. A caption points at numbers; it does not reprint them

The most common padding is a caption walking the reader through values already in
front of them:

> Gene-Miner's all-isoform Complete (C) fraction rises where the RNA-seq captures
> alternative isoforms (rice 93.6% → 96.5%, Drosophila 96.5% → 98.9%, C. elegans
> 95.1% → 98.3%; soybean only 91.9% → 92.1%), whereas BRAKER3's barely changes.

Every one of those percentages is a cell in that same table. The caption has
become a worse-formatted copy of the table underneath it.

- **One headline value is good caption writing.** "Completeness reaches 96.5% for
  rice" earns its place. A walk-through of eight does not.
- **Replace the list with what to NOTICE.** The sentence above is trying to say
  "all-isoform gains track isoform richness; BRAKER3 is flat" — say that, and let
  the numbers stay in the table.
- **Figures are the worse offender**, because nothing structural stops it: a
  figure has no columns, so a caption can carry a whole mini-Results of numbers
  and still look like a caption.
- **Word count will not save you.** A numeric-dense caption can be short, so the
  `long` flag stays quiet.

`lint_legends` reports this as **`number_restatement`**; its description says
what it lists and how it relates to `caption_only`.

#### 2d-quinquies-bis. What goes in a caption, and what does not

`caption` and `legend` describe what the item **shows**. Interpretation belongs
to the body section that cites it.

| field | holds |
|---|---|
| `title` | the short name ("Genome size by accession") |
| `caption` | the "Figure N." sentence plus what is depicted — axes, units, `n`, normalisation, the reference the values are relative to |
| `legend` | panel-by-panel and symbol-level detail: what A/B/C are, what the colours and shapes mean, what an empty cell means |
| the body | what the result MEANS, what it excludes, why it matters, how it relates to the other evidence |

Journals print caption and legend as one block, and the naming is not consistent
between them — Annual Reviews says caption, Nature-family says legend, and
"legend" also still means the key drawn inside the figure. Use the split above
regardless of what the target journal calls it.

**This is where "write from the reader's context" gets misapplied.** That rule
says to keep the context that makes a claim checkable when you compress. It does
NOT say to move the context into the caption — keep it, but keep it in the body.
A caption that argues duplicates the body, and the two copies then drift apart
under revision, which is how a manuscript ends up stating its central argument
twice in two places that have to be kept in sync by hand.

`lint_manuscript`'s `summary.clean` now covers captions and legends too, so a
manuscript whose figure legends restate the synthesis can no longer report clean;
`summary.body_clean` is the section-text-only answer. Both are `null` when that
dimension had nothing in it — see the gate below.

#### 2d-sexies. Describe the panel; don't argue from it

The same failure in words rather than numbers. A legend says what the reader is
looking at. The moment it says what the reader should *conclude*, that sentence
belongs in Results.

| legend text | verdict |
|---|---|
| "Darker shading indicates higher coverage." | fine — that IS the legend's job |
| "The lower panel shows the same data on a log scale." | fine — describes the graphic |
| "In rice the models are **overwhelmingly larger** than the reference." | Results |
| "Gene-Miner **approaches** their ceiling and **matches or exceeds** BRAKER3." | Results |
| "The novel loci are **markedly lower**." | Results |
| "They are complete gene models, **as expected** for lineage-specific genes." | Results/Discussion |

The tell is not the comparative word — legends compare all the time — it is
**what the subject is**. When the subject is the graphic (shading, panel, bars,
axis), a comparison describes an encoding. When the subject is a result (the
models, the loci, the pipeline), it is a claim.

`lint_legends` flags these as **`interpretive`**; its description gives the
thresholds and what is deliberately not flagged.

#### 2d-septies. Say what kind of evidence a panel is

A caption says whether what it shows was **measured, simulated, calculated or
drawn**. A simulated curve beside measured points, a model's prediction, a
schematic of a mechanism: each is named for what it is in the caption, and
the body does not call a simulation a result of an experiment. A reviewer who
finds out from the Methods that the "observed" trend was computed reads every
other panel with that in mind. This is description, not interpretation, so it
belongs in the caption under the rules above — it is the note that prevents
misreading the panel.

#### 2d-octies. The figures are read before the text

An editor's second look, after the title and abstract, is the figures with
their captions, and many reviewers start there. So the display items, read in
order with nothing else, should let a reader in the field say what the paper
shows — not because a caption argues (it must not: 2d-sexies), but because
each title names what is depicted and each caption makes the panel legible.
You cannot run that check on yourself; `/cold-read` has the run ("the display
items alone").

