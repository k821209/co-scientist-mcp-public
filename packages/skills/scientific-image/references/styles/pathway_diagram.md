# Pathway Diagram Style Guide

For metabolic pathways, signaling cascades, and biosynthesis routes.

---

## Characteristics

- Linear or branching flow of molecular transformations
- Enzymes catalyze conversions between metabolites
- Often organized by cellular compartment (cytoplasm, chloroplast, ER, etc.)
- Direction indicates biological causality or metabolic sequence

---

## Layout Patterns

### Linear Pathway (default)
```
[Substrate A] ──enzyme1──→ [Intermediate B] ──enzyme2──→ [Product C]
```

### Branching Pathway
```
                          ┌──enzyme2──→ [Product B]
[Substrate A] ──enzyme1──┤
                          └──enzyme3──→ [Product C]
```

### Compartmentalized
```
┌─── Cytoplasm ───────────────────────────────┐
│  [Precursor] ──E1──→ [Intermediate]         │
│                          │                  │
└──────────────────────────┼──────────────────┘
                           ▼
┌─── Chloroplast ─────────────────────────────┐
│              [Intermediate] ──E2──→ [Product]│
└─────────────────────────────────────────────┘
```

### Cyclic Pathway
```
         [A] ──E1──→ [B]
          ▲              │
          │             E2
         E4              │
          │              ▼
         [D] ←──E3── [C]
```

**Primary flow**: Left → Right or Top → Bottom
**Secondary flow**: Branches go upward or downward from the main chain

---

## Element Conventions

| Element | Shape | Fill | Border | Notes |
|---------|-------|------|--------|-------|
| Metabolite / Compound | Ellipse or pill | Light tint (30%) | Palette secondary, 2px | Main substrate/product use larger size |
| Enzyme / Catalyst | Small diamond or hexagon | Light tint (30%) | Palette tertiary, 2px | Positioned on or near the arrow |
| Gene | Rounded rectangle | Light tint (30%) | Palette primary, 2px | When gene regulation is shown |
| Cofactor (ATP, NADPH) | Small circle or text-only | White or no fill | — | Positioned as side-input to reaction |
| Compartment | Dashed rectangle | 15% tint | Matching color, 2px dashed | Labeled at top-left corner |

---

## Arrow Conventions

| Relationship | Arrow | Color | Notes |
|---|---|---|---|
| Enzymatic conversion | Solid, filled triangle → | Palette primary | Main pathway flow |
| Allosteric activation | Dashed, open triangle ▷ | #339966 (green) | Regulatory arrow pointing to enzyme |
| Inhibition / feedback | Dashed, flat bar ⊣ | #CC3333 (red) | Pointing to enzyme or metabolite |
| Transport (across compartment) | Solid, filled triangle → | #666666 | Crosses compartment boundary |
| Cofactor input/output | Thin solid, small arrow | #999999 | Side arrows into reaction |
| Reversible reaction | Double-headed ↔ | Palette primary | Only when truly reversible |

**Enzyme label placement**: On the arrow (midpoint, slightly offset above/below the line). Format: enzyme name in italic if it is a gene name.

---

## Prompt Keywords

Include in generation prompt:
- "metabolic pathway diagram"
- "biosynthesis route"
- "enzyme-catalyzed reactions"
- "flat design, clean white background"
- "scientific journal illustration style"
- "compartmentalized cellular pathway"

## Example Prompt Fragment

```
"Scientific journal-style metabolic pathway diagram on white background.
Left-to-right flow. Metabolites as ellipses with light green (#C6E1C8) fill
and green (#2E7D32) border. Enzymes as small hexagons with amber (#FDE1B8)
fill on the arrows. Solid arrows (#2E7D32, 2px) for main conversions.
Dashed red arrows (#CC3333) with flat bar heads for inhibition.
Compartment regions as dashed rectangles with light tinted backgrounds.
No shadows, no gradients, no 3D effects. Sans-serif labels."
```

---

## Reference Journals

- Nature Chemical Biology — pathway figures
- Plant Cell — compartmentalized metabolic diagrams
- Metabolic Engineering — multi-step biosynthesis routes
