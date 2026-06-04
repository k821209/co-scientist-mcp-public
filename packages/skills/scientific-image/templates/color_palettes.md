# Color Palettes for Scientific Figures

Six curated palettes for publication-quality scientific figures. Each palette includes primary colors, tints for background regions, and usage guidance.

**Rule**: Always use exact hex codes — never describe colors by name alone in generation prompts.

---

## 1. Classic Scientific (Default)

Best for: General-purpose scientific diagrams, multi-category data, mixed-element figures.

| Role | Color | Hex | Tint 15% | Tint 30% |
|------|-------|-----|----------|----------|
| Primary Blue | Blue | #0066CC | #E0EEFF | #C2DEFF |
| Secondary Orange | Orange | #FF6600 | #FFF0E0 | #FFE0C2 |
| Tertiary Green | Green | #339966 | #E3F5EC | #C8ECD9 |
| Accent Purple | Purple | #663399 | #EDE3F5 | #DBC8EC |
| Alert Red | Red | #CC3333 | #F9E3E3 | #F3C8C8 |
| Neutral Gray | Gray | #666666 | #EFEFEF | #E0E0E0 |

- **Borders/Lines**: #333333 (dark gray)
- **Arrow default**: #333333, width 2px
- **Text**: #1A1A1A (near-black)
- **Background regions**: Use 15% tint of the dominant category color
- **Subtle dividers**: #CCCCCC

---

## 2. Plant Biology

Best for: Metabolic pathways, biosynthesis routes, plant cell diagrams, photosynthesis figures.

| Role | Color | Hex | Tint 15% | Tint 30% |
|------|-------|-----|----------|----------|
| Primary Green | Forest Green | #2E7D32 | #E2F0E3 | #C6E1C8 |
| Secondary Blue | Royal Blue | #1565C0 | #DFEBF7 | #C0D8F0 |
| Tertiary Amber | Amber | #F57F17 | #FEF0DB | #FDE1B8 |
| Accent Purple | Deep Purple | #6A1B9A | #EDDFF5 | #DCC0EC |
| Highlight Red | Red | #C62828 | #F8E1E1 | #F1C4C4 |
| Neutral | Warm Gray | #5D4037 | #ECE7E5 | #D9CFCB |

- **Borders/Lines**: #2E2E2E
- **Arrow default**: #2E7D32 (green) for biosynthesis flow, #333333 for general
- **Chloroplast fill**: #C6E1C8 (green 30% tint)
- **Cytoplasm fill**: #FEF0DB (amber 15% tint)
- **Text**: #1A1A1A

---

## 3. AI / Computational

Best for: Machine learning pipelines, algorithm architectures, data processing workflows, digital twin diagrams.

| Role | Color | Hex | Tint 15% | Tint 30% |
|------|-------|-----|----------|----------|
| Primary Indigo | Indigo | #1A237E | #DFE1F5 | #C0C4EC |
| Secondary Teal | Teal | #00838F | #DCEEF0 | #B9DEE1 |
| Tertiary Amber | Dark Amber | #FF8F00 | #FFF1DB | #FFE3B8 |
| Accent Magenta | Magenta | #AD1457 | #F6DFE7 | #EDC0D0 |
| Data Green | Green | #2E7D32 | #E2F0E3 | #C6E1C8 |
| Neutral | Cool Gray | #546E7A | #E8EDEF | #D1DCE0 |

- **Borders/Lines**: #263238
- **Arrow default**: #1A237E (indigo), width 2px
- **Neural network nodes**: Use primary/secondary fills
- **Data flow arrows**: #00838F (teal)
- **Text**: #1A1A1A

---

## 4. Molecular Biology

Best for: Protein structures, gene expression, molecular interactions, PPI networks.

| Role | Color | Hex | Tint 15% | Tint 30% |
|------|-------|-----|----------|----------|
| Primary Blue | Dark Blue | #0D47A1 | #DDE7F6 | #BCD0ED |
| Secondary Green | Dark Green | #1B5E20 | #DFEDE0 | #C0DCC2 |
| Tertiary Orange | Dark Orange | #E65100 | #FCEADB | #FAD5B8 |
| Accent Purple | Deep Purple | #4A148C | #E7DCF3 | #D0BAE7 |
| Highlight Yellow | Gold | #F9A825 | #FEF3DA | #FDE7B6 |
| Neutral | Medium Gray | #616161 | #ECECEC | #DADADA |

- **Borders/Lines**: #212121
- **Arrow default**: #212121 (near-black)
- **Protein domains**: Primary/Secondary fills with 30% tints
- **Gene boxes**: White fill with colored left border (4px)
- **Text**: #1A1A1A

---

## 5. Comparative

Best for: Bar charts, grouped comparisons, before/after, treatment vs control, side-by-side analyses.

| Role | Color | Hex | Tint 15% | Tint 30% |
|------|-------|-----|----------|----------|
| Group A | Blue | #1565C0 | #DFEBF7 | #C0D8F0 |
| Group B | Red | #C62828 | #F8E1E1 | #F1C4C4 |
| Group C | Green | #2E7D32 | #E2F0E3 | #C6E1C8 |
| Group D | Amber | #F57F17 | #FEF0DB | #FDE1B8 |
| Baseline | Gray | #757575 | #F0F0F0 | #E0E0E0 |
| Significance | Black | #212121 | — | — |

- **Borders/Lines**: #424242
- **Arrow default**: #212121
- **Error bars**: #424242, width 1.5px
- **Significance brackets**: #212121, with asterisks
- **Axis lines**: #424242
- **Text**: #1A1A1A

---

## 6. Heatmap / Sequential

Best for: Heatmaps, correlation matrices, expression data, gradient visualizations.

### Diverging Scale (Blue → White → Red)
| Value | Color | Hex |
|-------|-------|-----|
| -1.0 (min) | Deep Blue | #0D47A1 |
| -0.5 | Medium Blue | #42A5F5 |
| 0 (center) | White | #FFFFFF |
| +0.5 | Medium Red | #EF5350 |
| +1.0 (max) | Deep Red | #B71C1C |

### Sequential Scale (Light → Dark)
| Value | Color | Hex |
|-------|-------|-----|
| 0 (min) | Lightest | #E3F2FD |
| 0.25 | Light | #90CAF9 |
| 0.50 | Medium | #42A5F5 |
| 0.75 | Dark | #1565C0 |
| 1.0 (max) | Darkest | #0D47A1 |

### Viridis-like Scale (for continuous data)
| Value | Color | Hex |
|-------|-------|-----|
| 0 (min) | Dark Purple | #440154 |
| 0.25 | Blue-Purple | #3B528B |
| 0.50 | Teal | #21908C |
| 0.75 | Green-Yellow | #5DC863 |
| 1.0 (max) | Yellow | #FDE725 |

- **Grid lines**: #E0E0E0 (light gray)
- **Cell borders**: #FFFFFF (white), 1px
- **Row/column labels**: #1A1A1A, 10pt minimum
- **Dendrogram lines**: #333333
- **Text**: #1A1A1A

---

## Palette Selection Guide

| Diagram Type | Recommended Palette |
|---|---|
| Metabolic/biosynthesis pathway | Plant Biology |
| Signaling pathway | Classic Scientific |
| PPI / gene regulatory network | Molecular Biology |
| ML/AI pipeline or architecture | AI/Computational |
| System architecture diagram | AI/Computational |
| Treatment comparison / bar chart | Comparative |
| Heatmap / correlation matrix | Heatmap/Sequential |
| Phylogenetic tree | Classic Scientific |
| General / mixed | Classic Scientific |

## Prompt Integration Rule

When building the generation prompt, specify colors as:
```
"Node X: fill #0066CC, border #333333, text #1A1A1A"
"Arrow from X to Y: color #333333, width 2px, solid line, pointed arrowhead"
"Background region: fill #E0EEFF (15% tint of #0066CC)"
```

Never say "blue node" — always say "node with fill #0066CC".
