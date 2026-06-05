# Comparison Chart Style Guide

For bar charts, grouped comparisons, treatment vs control, before/after analyses, and multi-condition data.

---

## Characteristics

- Side-by-side or grouped data presentation
- Clear category labels and value axis
- Error bars for statistical data
- Significance indicators (asterisks, brackets)
- Color-coded groups for quick visual distinction

---

## Layout Patterns

### Grouped Bar Chart
```
     │
  30 │  ██          ██
     │  ██  ░░      ██  ░░
  20 │  ██  ░░  ▓▓  ██  ░░  ▓▓
     │  ██  ░░  ▓▓  ██  ░░  ▓▓
  10 │  ██  ░░  ▓▓  ██  ░░  ▓▓
     │  ██  ░░  ▓▓  ██  ░░  ▓▓
   0 └──────────────────────────
       Treatment A   Treatment B
     ██ Control  ░░ Low dose  ▓▓ High dose
```

### Side-by-Side Comparison
```
┌─── Before ────────┐    ┌─── After ─────────┐
│                    │    │                    │
│  [Metric A: 45]   │    │  [Metric A: 78]   │
│  [Metric B: 23]   │ vs │  [Metric B: 56]   │
│  [Metric C: 67]   │    │  [Metric C: 89]   │
│                    │    │                    │
└────────────────────┘    └────────────────────┘
```

### Multi-Panel Comparison
```
┌─── Panel A ───┐  ┌─── Panel B ───┐  ┌─── Panel C ───┐
│  (bar chart)  │  │  (bar chart)  │  │  (bar chart)  │
│               │  │               │  │               │
└───────────────┘  └───────────────┘  └───────────────┘
```

---

## Element Conventions

| Element | Shape | Fill | Border | Notes |
|---------|-------|------|--------|-------|
| Bar (Group A) | Rectangle | #1565C0 (solid) | None or same color darker | Width consistent across groups |
| Bar (Group B) | Rectangle | #C62828 (solid) | None | Same width as Group A |
| Bar (Group C) | Rectangle | #2E7D32 (solid) | None | Same width |
| Bar (Group D) | Rectangle | #F57F17 (solid) | None | Same width |
| Error bar | T-shaped line | — | #424242, 1.5px | Centered on bar top |
| Significance bracket | Horizontal bracket + asterisk | — | #212121, 1.5px | Above compared bars |
| Axis line | Straight line | — | #424242, 1.5px | X and Y axes |
| Grid line (optional) | Horizontal dashed | — | #E0E0E0, 0.5px | Background reference |
| Baseline | Horizontal solid at y=0 | — | #424242, 1.5px | If negative values exist |

---

## Arrow Conventions

Comparison charts typically use minimal arrows, but when needed:

| Relationship | Arrow | Color | Notes |
|---|---|---|---|
| Increase/improvement | Solid upward arrow | #2E7D32 | Next to value change |
| Decrease | Solid downward arrow | #C62828 | Next to value change |
| Fold change indicator | Curved arrow between bars | #333333 | Labeled with fold change |
| Reference line | Horizontal dashed | #999999 | Threshold or control level |

---

## Significance Notation

| Symbol | Meaning |
|--------|---------|
| ns | Not significant (p > 0.05) |
| * | p < 0.05 |
| ** | p < 0.01 |
| *** | p < 0.001 |
| **** | p < 0.0001 |

Place above brackets connecting compared groups. Bracket height should not overlap with error bars.

---

## Prompt Keywords

- "grouped bar chart comparison"
- "treatment vs control bar graph"
- "scientific comparison figure"
- "statistical bar chart with error bars"
- "flat design, white background, publication quality"

## Example Prompt Fragment

```
"Scientific journal-style grouped bar chart on white background.
Three treatment groups shown in blue (#1565C0), red (#C62828), and
green (#2E7D32) solid-fill bars. Error bars (black #424242, 1.5px)
on each bar showing standard error. Significance brackets above
compared groups with asterisks (**, ***). Y-axis with numerical
scale and label. X-axis with condition labels. Clean sans-serif font.
Light gray (#E0E0E0) horizontal grid lines. Legend in bottom-right.
No shadows, no gradients, no 3D effects."
```

---

## Reference Journals

- Nature — standard bar chart formatting
- Science — grouped comparison figures
- PNAS — multi-panel statistical comparisons
