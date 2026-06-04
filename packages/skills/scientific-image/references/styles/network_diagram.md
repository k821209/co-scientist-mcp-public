# Network Diagram Style Guide

For protein-protein interaction (PPI) networks, gene regulatory networks (GRNs), and co-expression networks.

---

## Characteristics

- Nodes represent biological entities (proteins, genes, TFs)
- Edges represent relationships (interactions, regulation, co-expression)
- No single directional flow — multi-directional connections
- Hub nodes (highly connected) are visually prominent
- Often clustered by function, pathway, or module

---

## Layout Patterns

### Clustered Network
```
    ┌── Module A ──┐     ┌── Module B ──┐
    │  (A1)-(A2)   │     │  (B1)-(B2)   │
    │   |    |     │─────│   |          │
    │  (A3)-(A4)   │     │  (B3)-(B4)   │
    └──────────────┘     └──────────────┘
            │
    ┌── Module C ──┐
    │  (C1)-(C2)   │
    │       |      │
    │      (C3)    │
    └──────────────┘
```

### Hub-and-Spoke
```
           (N2)    (N3)
             \    /
    (N1) ── (HUB) ── (N4)
             /    \
           (N5)    (N6)
```

### Layered Regulatory
```
  [TF1]    [TF2]    [TF3]        ← Regulators (top)
    │  \   /  │  \   /  │
    ▼   ▼ ▼   ▼   ▼ ▼   ▼
  [G1]  [G2] [G3] [G4] [G5]     ← Targets (bottom)
```

---

## Element Conventions

| Element | Shape | Fill | Border | Notes |
|---------|-------|------|--------|-------|
| Protein / Gene | Circle | Category-based palette color, 30% tint | Palette color, 2px | Size proportional to degree or importance |
| Hub node | Larger circle | Solid palette color | Darker shade, 3px | 1.5–2× size of normal nodes |
| Transcription factor | Rounded rectangle | Palette accent, 30% tint | Palette accent, 2px | Distinguished from regular genes |
| Metabolite (if in network) | Diamond | Light tint | Palette secondary, 2px | Smaller than gene nodes |
| Cluster / Module | Dashed ellipse or rounded rect | 15% tint | Matching color, 2px dashed | Contains grouped nodes |

**Node sizing**: Hub nodes (degree > mean + 1σ) should be 1.5–2× the size of peripheral nodes. This makes network topology visually obvious.

---

## Arrow / Edge Conventions

| Relationship | Line Style | Ends | Color | Width |
|---|---|---|---|---|
| Physical interaction (PPI) | Solid | None (no arrows) | #666666 | 2px |
| Activation | Solid | Filled triangle → | #339966 | 2px |
| Repression | Solid | Flat bar ⊣ | #CC3333 | 2px |
| Co-expression | Dashed | None | #999999 | 1.5px |
| Predicted / computational | Dotted | Open triangle ▷ | #AAAAAA | 1px |
| Strong interaction | Solid | None | #333333 | 3px |
| Weak interaction | Solid | None | #CCCCCC | 1px |

**Edge width encoding**: For weighted networks, edge width can encode interaction strength (1px weak → 4px strong).

---

## Prompt Keywords

- "protein-protein interaction network"
- "gene regulatory network diagram"
- "biological network visualization"
- "node-edge graph with clusters"
- "flat design, white background, scientific illustration"

## Example Prompt Fragment

```
"Scientific journal-style protein-protein interaction network on white
background. Protein nodes as circles with blue (#BCD0ED) fill and dark blue
(#0D47A1) border. Hub proteins are larger circles with solid blue (#0D47A1)
fill and white text. Physical interactions as gray (#666666) solid lines
without arrowheads. Activation edges as green (#339966) solid arrows.
Repression as red (#CC3333) flat-bar arrows. Functional modules enclosed in
dashed ellipses with 15% tinted backgrounds. No shadows, no gradients."
```

---

## Reference Journals

- Nature Methods — network visualization standards
- Cell Systems — biological network figures
- Molecular Systems Biology — GRN and PPI network layouts
