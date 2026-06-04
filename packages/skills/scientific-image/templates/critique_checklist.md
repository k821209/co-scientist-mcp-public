# Critique Checklist for Scientific Figures

Weighted scoring rubric for evaluating generated scientific figures. Used by the Critic agent to determine pass/fail and generate targeted edit instructions.

---

## Scoring Scale

| Score | Meaning |
|-------|---------|
| 5 | Excellent — publication-ready, no issues |
| 4 | Good — minor cosmetic issues only |
| 3 | Acceptable — noticeable issues but usable |
| 2 | Needs improvement — clear problems that affect readability |
| 1 | Poor — major problems requiring regeneration |

---

## Evaluation Categories

### 1. Arrow Correctness (Weight: 25%)

**Check items:**
- [ ] Every arrow has a clear, identifiable source and target node
- [ ] Arrowheads are visible and correct type (triangle vs bar vs open)
- [ ] Arrow direction matches the intended relationship (A→B, not B→A)
- [ ] No floating arrows (disconnected from any node)
- [ ] No arrows pointing to wrong targets
- [ ] Different relationship types use distinct arrow styles (solid vs dashed vs dotted)
- [ ] Inhibition arrows use flat-bar heads (⊣), not triangles
- [ ] Arrow labels are positioned near the arrow midpoint, not overlapping nodes
- [ ] Minimal arrow crossings; crossed arrows are visually distinguishable
- [ ] Bidirectional arrows are clearly two-headed, not ambiguous

**Common issues to flag:**
- "Arrow between [X] and [Y] points in wrong direction — should flow from X to Y"
- "Arrow from [X] to [Y] is missing — add solid arrow with filled triangle head"
- "Arrowhead on [X→Y] is too small to see — enlarge to at least 6px"
- "Arrow label '[text]' overlaps with node [Z] — offset label 8px from line"

---

### 2. Color Consistency (Weight: 25%)

**Check items:**
- [ ] All nodes of the same category use the same fill color
- [ ] Colors match the palette specified by the Stylist (within visual tolerance)
- [ ] No unexpected colors appear that are not in the specification
- [ ] Background regions use correct tint values (lighter than node fills)
- [ ] Sufficient contrast between node fill and text labels
- [ ] Sufficient contrast between arrow colors and background
- [ ] No color conflicts between adjacent elements
- [ ] Group/compartment borders match their specified color
- [ ] Legend colors match the actual figure elements
- [ ] No rainbow/random color assignments

**Common issues to flag:**
- "Node [X] uses incorrect fill — should be #0066CC but appears as [wrong color]"
- "Gene nodes use inconsistent colors — some are blue, others are green; all should be #0066CC"
- "Text label on [node] has low contrast against fill — use white (#FFFFFF) text on dark fill"
- "Background region for [group] is too dark — use 15% tint #E0EEFF instead"

---

### 3. Text Readability (Weight: 15%)

**Check items:**
- [ ] All text labels are legible (not blurry, not too small)
- [ ] No text is cut off or clipped by node boundaries
- [ ] Text does not overlap other text or critical elements
- [ ] Font style is consistent (all sans-serif)
- [ ] Text size hierarchy is clear (titles > labels > annotations)
- [ ] No spelling errors in visible labels
- [ ] Chemical formulas and gene names are correctly formatted
- [ ] All planned labels are present (no missing labels)

**Common issues to flag:**
- "Label '[text]' on node [X] is truncated — widen node or reduce font size"
- "Labels '[A]' and '[B]' overlap — increase spacing between nodes"
- "Text on [node] is too small to read — increase to at least 9pt"
- "Gene name '[X]' should be italicized per convention"

---

### 4. Layout Balance (Weight: 15%)

**Check items:**
- [ ] Elements are evenly distributed across the canvas
- [ ] No large empty areas next to crowded regions
- [ ] Nodes at the same hierarchy level are aligned
- [ ] Flow direction is consistent (all left→right or all top→bottom)
- [ ] Groups/compartments are clearly bounded and non-overlapping
- [ ] Sufficient spacing between nodes (≥40px between edges)
- [ ] The figure uses the available space efficiently
- [ ] Symmetric structures appear symmetric

**Common issues to flag:**
- "Left half of the figure is crowded while right half is empty — redistribute nodes"
- "Nodes [A], [B], [C] are at the same level but not aligned — align horizontally"
- "Group [X] overlaps with group [Y] — add spacing or resize"
- "Pathway flows left→right but middle section flows upward — maintain consistent direction"

---

### 5. Academic Style Compliance (Weight: 10%)

**Check items:**
- [ ] White background (no colored or textured background)
- [ ] No drop shadows on any element
- [ ] No gradients (all flat fills)
- [ ] No 3D effects or perspective
- [ ] No decorative or purely aesthetic elements
- [ ] Clean, professional appearance suitable for Nature/Science/Cell
- [ ] Appropriate for black-and-white printing (shapes distinguishable without color)
- [ ] Figure would look appropriate in a grant proposal or peer-reviewed paper

**Common issues to flag:**
- "Background is not pure white — change to #FFFFFF"
- "Nodes have drop shadows — remove all shadow effects"
- "Some fills use gradient — replace with flat solid color"
- "Decorative border/frame is unnecessary — remove it"

---

### 6. Content Accuracy (Weight: 10%)

**Check items:**
- [ ] All entities from the blueprint are present in the figure
- [ ] No extra entities that were not in the blueprint
- [ ] Relationships match the blueprint (correct connections)
- [ ] Groupings match the blueprint (correct compartments)
- [ ] Labels match the blueprint text exactly
- [ ] Pathway order is biologically/logically correct
- [ ] No duplicate nodes that should be single nodes

**Common issues to flag:**
- "Node [X] from the blueprint is missing — add it with specified shape and color"
- "Extra node [Y] appears that is not in the blueprint — remove it"
- "Connection between [A] and [B] is missing — add [arrow type] arrow"
- "[X] and [Y] should be in the same group/compartment but are separated"

---

## Pass / Fail Criteria

**PASS** (accept the figure):
- Overall weighted score >= 3.5
- AND no individual category score < 2.5

**FAIL** (needs revision):
- Overall weighted score < 3.5
- OR any individual category score < 2.5

**Auto-accept after round 3**: If max rounds (3) reached, accept with warnings listing all remaining issues.

---

## Critique Report Template

```markdown
## Critique Report — Round {N}

### Scores
| Category | Weight | Score | Weighted |
|----------|--------|-------|----------|
| Arrow Correctness | 25% | X.X | X.XX |
| Color Consistency | 25% | X.X | X.XX |
| Text Readability | 15% | X.X | X.XX |
| Layout Balance | 15% | X.X | X.XX |
| Academic Style | 10% | X.X | X.XX |
| Content Accuracy | 10% | X.X | X.XX |
| **Overall** | **100%** | — | **X.XX** |

### Verdict: PASS / FAIL

### Issues Found
1. [Category] Issue description
2. [Category] Issue description
...

### Edit Instructions (if FAIL)
Priority fixes for the Visualizer:
1. "Specific instruction for highest-priority fix"
2. "Specific instruction for second fix"
3. "Specific instruction for third fix"
(Maximum 5 instructions per round, ordered by impact)
```

---

## Edit Instruction Format

When generating edit instructions for the Visualizer, format them as a single concatenated prompt:

```
"Fix the following issues in this scientific diagram:
1. [Most critical fix]
2. [Second fix]
3. [Third fix]
Keep all other elements exactly as they are. Maintain the white background, flat design, and all correctly-placed elements."
```

**Rules for edit instructions:**
- Maximum 5 fixes per round (focus on highest impact)
- Be spatially specific ("the arrow in the upper-left", "the blue node labeled X")
- Include exact colors when correcting color issues ("change fill to #0066CC")
- Always end with preservation instruction ("keep everything else the same")
- Prioritize Arrow and Color fixes first (they have highest weight)
