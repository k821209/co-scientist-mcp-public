# Workflow / Pipeline Diagram Style Guide

For sequential research workflows, experimental protocols, bioinformatics pipelines, and multi-stage processes.

---

## Characteristics

- Strictly sequential: clear start → end flow
- Each step is a distinct process or tool
- Inputs and outputs are explicit
- Often includes branching (parallel steps) and merging
- May show data transformations at each stage

---

## Layout Patterns

### Linear Pipeline
```
[Input] → [Step 1] → [Step 2] → [Step 3] → [Output]
```

### Branching Pipeline
```
                    ┌→ [Analysis A] ─┐
[Input] → [Preprocess] ─┤                  ├→ [Integration] → [Output]
                    └→ [Analysis B] ─┘
```

### Multi-Stage with Data Flow
```
┌─ Stage 1: Data ─┐   ┌─ Stage 2: Model ──┐   ┌─ Stage 3: Validate ─┐
│ [Collect]        │   │ [Train]            │   │ [Test]              │
│     ↓            │   │     ↓              │   │     ↓               │
│ [Clean]          │──→│ [Optimize]         │──→│ [Deploy]            │
│     ↓            │   │     ↓              │   │                     │
│ [Format]         │   │ [Evaluate]         │   │                     │
└──────────────────┘   └────────────────────┘   └─────────────────────┘
```

### Iterative / Loop
```
[Input] → [Process] → [Evaluate] ──pass──→ [Output]
               ▲            │
               └──fail──────┘
```

**Primary flow**: Left → Right (preferred) or Top → Bottom

---

## Element Conventions

| Element | Shape | Fill | Border | Notes |
|---------|-------|------|--------|-------|
| Process step | Rounded rectangle | 30% tint of step category | Category color, 2px | 100–150px wide |
| Input / Output | Parallelogram | White | #666666, 1.5px | Leaning right for input, left for output |
| Data / File | Rectangle with folded corner | #FFF8E1 (light yellow) | #F57F17, 1.5px | Small icon for data artifacts |
| Decision | Diamond | White | #333333, 2px | Yes/No branches |
| Tool / Software | Rectangle with icon | White | Tool-category color, 2px | Tool name + small logo placeholder |
| Stage group | Dashed rectangle | 15% tint | Stage color, 2px dashed | Groups related steps |

---

## Arrow Conventions

| Relationship | Arrow | Color | Notes |
|---|---|---|---|
| Main flow / sequence | Solid, filled triangle → | #333333 | 2.5px, primary direction |
| Data transfer | Solid, filled triangle → | Palette secondary | 2px, from data to process |
| Conditional branch | Dashed, filled triangle → | #666666 | Labeled "yes"/"no" or condition |
| Feedback / iteration | Curved solid, filled triangle → | Palette accent | Loops back to earlier step |
| Optional step | Dotted, open triangle ▷ | #999999 | 1.5px |
| Parallel split | Solid fork (one→many) | #333333 | Multiple arrows from one source |
| Merge | Solid join (many→one) | #333333 | Multiple arrows to one target |

**Step numbering**: Optionally number each step (①, ②, ③) in a small circle at top-left of each process box.

---

## Prompt Keywords

- "research workflow diagram"
- "bioinformatics pipeline"
- "experimental protocol flowchart"
- "sequential process diagram"
- "data analysis pipeline"
- "flat design, white background, scientific illustration"

## Example Prompt Fragment

```
"Scientific journal-style bioinformatics pipeline diagram on white
background. Left-to-right flow. Process steps as rounded rectangles
numbered 1-6 with teal (#B9DEE1) fill and teal (#00838F) border.
Input/output as parallelogram shapes with light gray fill. Data files
as small rectangles with folded corners in light yellow (#FFF8E1).
Solid dark arrows (#333333, 2.5px) connecting sequential steps.
Stage groups enclosed in dashed rectangles with 15% tinted backgrounds
labeled 'Stage 1: Data Collection', 'Stage 2: Analysis'.
No shadows, no gradients, sans-serif labels."
```

---

## Reference Journals

- Nature Methods — bioinformatics pipeline figures
- Genome Biology — analysis workflow diagrams
- Bioinformatics — computational pipeline visualizations
