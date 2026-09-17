# Field register — computational biology / bio-AI

Read this before drafting a section, a caption or a table for a biology
journal. `/paper-writing` §2 says *write journal prose, not chat prose*; it does
not say what journal prose sounds like **in this field**. This file does, from a
worked exemplar rather than from rules, because the rules in SKILL.md were loaded
and followed and the manuscript still came out in the wrong register.

**Exemplar:** Ye, Benegas, Albors, Li, Prillo, Fields, Clarke & Song, *Predicting
genome-wide functional constraints with GPN-Star*, **Nature** (2026),
doi:10.1038/s41586-026-11005-5. A gLM paper in the same subfield, same year,
top venue. Quotes below are verbatim from it.

## 1. Tense

Results are **past tense**. This is the single most pervasive tell.

> "GPN-Star (V) **achieved** the highest area under the precision-recall curve
> (AUPRC), matching the performance of the protein language model ESM-1b."

> "GPN-Star (M) **continued to outperform** all other models on this benchmark."

> "Across all five species, GPN-Star scores **exhibited** substantially higher
> rare variant enrichment compared with PhyloP and PhastCons."

Present tense is reserved for what remains true outside the experiment — the
method, the data, the definition.

| don't | do |
|---|---|
| "The specialist wins on specificity AUC in both directions." | "The specialist outperformed the foreign adapter in both directions." |
| "Level ρ is flat." | "Level ρ remained unchanged." |
| "The panel collapses, from 361 measured conditions to 59." | "The number of measured conditions fell from 361 to 59." |
| "Composition alone does not reach the released checkpoint." | "Composition alone did not reach the published checkpoint." |

## 2. Sentence shape

The field's Results paragraph has one rhythm, repeated:

**We [verb] [which data / which benchmark] → [what happened] (Fig. N) → [one
clause of interpretation].**

> "We next considered somatic cancer variants from the COSMIC database,
> constructing a benchmark to distinguish missense variants frequently observed
> in tumours from common missense variants in the general population. As shown in
> Fig. 2b, GPN-Star (V) substantially outperformed all competing models,
> demonstrating strong predictive capability for pathogenicity beyond germline
> variants."

Openers that carry a paragraph: *We next considered… We also assessed… We
further evaluated… We then compared… Beyond X, we…*

**Hedges go at the end of the sentence and name the thing conceded**, once:

> "…GPN-Star (V) outperformed all genome-wide models, **although it slightly
> lagged behind the protein-specific models**."

> "…potentially suggesting that the present approach to incorporating tissue
> specificity remains suboptimal."

> "**A plausible explanation is that** WGAs are constructed relative to a
> reference species and often consist of small, highly fragmented synteny blocks."

Do **not** interleave the concession into the middle of the claim, and do not
concede twice in one paragraph. A manuscript that argues with itself inside every
sentence reads as unsure of its own result.

## 3. Terminology

Words that mean something else in biology, or that belong to ML-workshop prose:

| ours | why it fails | field term |
|---|---|---|
| **artefact** (for the distributed file) | In biology an artefact is a spurious result. A reviewer reads "Artefact 9.7 MB" as a defect. | adapter size; distributed file; model weights |
| **arm** | Clinical-trial term borrowed for a model config. | model configuration; training regime; or just name it |
| **the target axis**, **the parameterisation axis** | Design-space metaphor from ML workshops. | the choice of training target; low-rank adaptation versus full fine-tuning |
| **the .01 floor** | Invented unit of measurement. | "differences below 0.01 were treated as within run-to-run variation" |
| **released checkpoint** | Ambiguous. | the published PlantCAD2 model; the pretrained model |
| **scope** (column head) | Vague. | trained on (one species / both species) |
| **Level ρ** bare | ρ undefined. | Spearman's ρ, defined on first use and in the column head |

Name each model configuration with a short tag on first use and reuse it
verbatim everywhere, as GPN-Star does with GPN-Star (V), (M), (P).

## 4. Numbers

- **Leading zero.** `0.738`, never `.738`. Dropping it is a psychology/statistics
  convention; Nature-family and BMC journals keep it.
- Numbers in prose are **normal and expected** in this field when they carry a
  comparison: "402 genes compared with 383 from the original method",
  "(33%, 170-fold enriched)". The terminal-output rule about keeping numbers out
  of prose does not apply to the manuscript.
- Report the metric by name every time it first appears in a section
  ("area under the precision-recall curve (AUPRC)", "Spearman's ρ").

## 5. Figure titles are descriptive, not claims

Nature-family figure titles name the object, not the finding. Every one in the
exemplar:

> Fig. 1 | **Overview of GPN-Star.**
> Fig. 2 | **Performance of GPN-Star on human genome-wide variant effect prediction.**
> Fig. 3 | **SNP heritability analyses in human complex traits.**
> Fig. 4 | **GPN-Star scores reflect evolutionary constraints on the human genome.**
> Fig. 5 | **Application of GPN-Star to non-human species.**

Fig. 4's title is the furthest the field goes toward a claim, and it is a
statement of what the panel displays.

| don't | do |
|---|---|
| "A rank-8 adapter reaches full fine-tuning once the objective is matched" | "Frozen-probe performance of low-rank adapters and full fine-tuning" |
| "What the adapter is trained on decides what it learns" | "Effect of the training target on three downstream metrics" |
| "Coverage falls before signal does" | "Metric performance as a function of compendium size" |

The claim goes in the Results sentence that cites the figure. That is where a
reader looks for it and where a reviewer can argue with it.

## 6. Nothing interpretive inside a table object

SKILL.md §2d-sexies already forbids this in a `caption`. It also applies to a
table's **`content`**: `lint_legends` checks the prose outside the pipe table
too (`content_interpretive`), so a mini-Results moved there is caught — but it
is caught after the fact; do not write it.

Forbidden inside `content`: a bolded summary line, a "Three readings" paragraph,
a sentence beginning "What the experiment establishes is…", any sentence whose
subject is a result rather than a column. Footnotes defining a column, stating a
unit, or naming an exclusion are fine and expected.

GPN-Star has **no main-text tables at all**. Two is comfortable. Five, each
carrying its own discussion, is a Results section that has been cut up and
filed under the wrong headings.

## 7. Section headers name the object of study

> Alignment- and phylogeny-informed gLMs · Pathogenic coding variants ·
> Pathogenic non-coding variants · Fine-mapped variants in GWAS · Rare variant
> association testing · Complex trait heritability · Relevant evolutionary
> timescales · Tissue-specific heritability signals · Interpretability of
> GPN-Star · Genome-wide evolutionary constraints · GPN-Star for model organisms

One header per benchmark or per analysis, phrased as a noun phrase. Not a claim,
not a question.

## 8. Display-item budget

The exemplar's allocation, which is the field's shape for a methods-plus-
evaluation paper:

| slot | carries |
|---|---|
| Fig 1 | the method or the data it is built on |
| Fig 2 | the main evaluation, many panels, every competitor, confidence intervals |
| Fig 3 | **what a reader of this field gets from it** — the downstream application |
| Fig 4 | mechanism or sanity: does the score mean what we say it means |
| Fig 5 | generalisation beyond the training setting |
| Extended Data 1–10 | the full competitor sets, the ablations, case studies |
| Supplementary | protocol, vocabularies, parameter tables, everything defensive |

A paper that spends two of five main figures on how its labels were made, and
none on what the method finds, has its budget inverted. Protocol goes to
Supplementary.

## 9. Statistical furniture the field expects

Present in the exemplar, and the bar a reviewer applies:

- A confidence interval on every headline number. "95% confidence intervals
  based on 1,000 class-stratified bootstrap resamples."
- A classical or trivial baseline that is not a neural network. PhastCons,
  PhyloP, CADD, and a mutation-rate null.
- A held-out partition named explicitly, and used for the headline number.
- Replicate runs wherever the procedure is stochastic. "This procedure was run
  three times with different random seeds."
- Limitations stated plainly in the Discussion, in the authors' own voice,
  naming the specific weakness: "improvements from expanding context sizes were
  relatively small", "A practical limitation is that GPN-Star requires WGAs
  during inference."
- Deposit: weights, training data and benchmarks on a public host, code on
  GitHub, a Zenodo DOI, and a data-availability statement that says whether new
  data were generated.
