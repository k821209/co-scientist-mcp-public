# Heatmap / Matrix Style Guide

For heatmaps, correlation matrices, expression data visualization, and clustered data displays.

---

## Characteristics

- Grid of colored cells encoding numerical values
- Row and column labels (genes, samples, conditions)
- Optional dendrograms for hierarchical clustering
- Color scale legend mapping values to colors
- May include annotations (row/column color bars)

---

## Layout Patterns

### Basic Heatmap
```
           Sample1  Sample2  Sample3  Sample4
Gene A     [████]   [░░░░]   [████]   [▓▓▓▓]
Gene B     [░░░░]   [████]   [▓▓▓▓]   [░░░░]
Gene C     [▓▓▓▓]   [▓▓▓▓]   [░░░░]   [████]
Gene D     [████]   [████]   [████]   [░░░░]

████ = High   ▓▓▓▓ = Medium   ░░░░ = Low
```

### Clustered Heatmap with Dendrogram
```
        ┌──┬──┐
        │  │  │           (column dendrogram)
        ┌──┐  │
     S1  S3  S2  S4
┬─ A  [██] [██] [░░] [▓▓]
│  C  [▓▓] [▓▓] [░░] [██]    (row dendrogram on left)
├─ B  [░░] [██] [▓▓] [░░]
│  D  [██] [██] [██] [░░]
```

### Correlation Matrix (Symmetric)
```
       A     B     C     D
A    1.00  0.85 -0.32  0.67
B    0.85  1.00  0.12  0.45
C   -0.32  0.12  1.00 -0.78
D    0.67  0.45 -0.78  1.00
```

### Annotated Heatmap
```
              [Treatment Color Bar]
              T1    T2    C1    C2
[Cluster] A   [██]  [██]  [░░]  [░░]
  Bar     B   [██]  [▓▓]  [░░]  [░░]
          C   [░░]  [░░]  [██]  [██]
          D   [░░]  [░░]  [▓▓]  [██]
```

---

## Element Conventions

| Element | Shape | Fill | Border | Notes |
|---------|-------|------|--------|-------|
| Data cell | Square/Rectangle | Color from scale | White (#FFFFFF), 1px | Uniform size across grid |
| Row label | Text (left-aligned) | — | — | 9–10pt, sans-serif |
| Column label | Text (rotated 45° or vertical) | — | — | 9–10pt, sans-serif |
| Dendrogram line | Orthogonal lines | — | #333333, 1.5px | Standard hierarchical tree |
| Color scale legend | Gradient bar | Scale colors | #333333, 1px | 10–15px wide, labeled with values |
| Annotation bar | Thin rectangle | Category color | White, 0.5px | 8–12px wide, alongside labels |
| Value text (optional) | Centered in cell | — | — | 7–8pt, white on dark, black on light |

---

## Color Scale Conventions

### For Expression Data (Diverging)
- Down-regulated: Blue #0D47A1 → Medium Blue #42A5F5 → White #FFFFFF → Medium Red #EF5350 → Up-regulated: Red #B71C1C
- Center: White represents baseline/zero

### For Correlation Matrix (Diverging)
- Negative: Blue #0D47A1 → White #FFFFFF → Positive: Red #B71C1C
- Diagonal: Gray #E0E0E0 or neutral

### For Abundance/Counts (Sequential)
- Low: #E3F2FD → Medium: #42A5F5 → High: #0D47A1
- Zero: White #FFFFFF

### For Categorical / Annotation Bars
- Use Comparative palette: Blue #1565C0, Red #C62828, Green #2E7D32, Amber #F57F17

---

## Arrow Conventions

Heatmaps rarely use arrows, but when needed:

| Element | Style | Color | Notes |
|---|---|---|---|
| Cluster highlight bracket | L-shaped bracket | #333333, 2px | Points to cluster of interest |
| Annotation callout | Thin line + text | #666666, 1px | Points to specific cell/region |

---

## Prompt Keywords

- "gene expression heatmap"
- "correlation matrix"
- "clustered heatmap with dendrogram"
- "scientific data visualization"
- "diverging color scale blue-white-red"
- "flat design, white background"

## Example Prompt Fragment

```
"Scientific journal-style gene expression heatmap on white background.
Grid of colored cells with diverging color scale: deep blue (#0D47A1)
for low expression through white (#FFFFFF) to deep red (#B71C1C) for
high expression. White 1px borders between cells. Row labels (gene names)
on the left in 10pt sans-serif. Column labels (sample names) rotated 45
degrees at top. Hierarchical clustering dendrogram on left side and top,
drawn with dark gray (#333333) orthogonal lines. Color scale legend bar
on the right side. No shadows, no gradients, no 3D effects."
```

---

## Reference Journals

- Nature — gene expression heatmap standards
- Cell — clustered heatmap with annotation bars
- Genome Research — multi-omics heatmap figures
