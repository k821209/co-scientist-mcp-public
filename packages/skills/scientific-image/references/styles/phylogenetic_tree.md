# Phylogenetic Tree Style Guide

For phylogenetic trees, dendrograms, evolutionary relationships, and hierarchical classification.

---

## Characteristics

- Branching tree structure showing evolutionary or hierarchical relationships
- Leaf nodes represent taxa, species, genes, or samples
- Branch lengths may encode evolutionary distance or time
- Internal nodes represent common ancestors or split points
- Often annotated with bootstrap values, divergence times, or trait data

---

## Layout Patterns

### Rectangular (Cladogram)
```
     ┌── Species A
  ┌──┤
  │  └── Species B
──┤
  │  ┌── Species C
  └──┤
     │  ┌── Species D
     └──┤
        └── Species E
```

### Circular / Radial
```
         Species A
        /
   ----+---- Species B
  /
-+     Species C
  \   /
   --+
      \
       Species D
```

### Rectangular with Branch Lengths
```
     ┌─────────── Species A (long branch)
  ┌──┤
  │  └──── Species B
──┤
  │  ┌── Species C
  └──┤
     └───────── Species D (long branch)

  |────|────|────|────|
  0   0.1  0.2  0.3  0.4  (substitutions/site)
```

### Tree with Trait Annotations
```
                        Color  Size   Habitat
  ┌── Species A          ██    ●●●    [Forest]
──┤
  │  ┌── Species B       ░░    ●●     [Desert]
  └──┤
     └── Species C       ▓▓    ●      [Marine]
```

---

## Element Conventions

| Element | Shape | Fill | Border | Notes |
|---------|-------|------|--------|-------|
| Leaf node | Small circle (4–6px) or text only | Clade color | Same color, 2px | One per terminal taxon |
| Internal node | Small circle (3–4px) | #333333 or clade color | — | At branching points |
| Branch line | Orthogonal lines | — | Clade color, 2px | Right-angle bends for rectangular tree |
| Bootstrap value | Small text at node | — | — | 7–8pt, near internal node |
| Scale bar | Horizontal line with ticks | — | #333333, 1.5px | Below tree, labeled with units |
| Clade highlight | Background shading | 15% tint | — | Vertical strip behind clade |
| Trait annotation | Small colored squares/circles | Trait color | White, 0.5px | Aligned in columns next to leaf labels |

**Clade coloring**: Assign distinct colors to major clades. All branches and leaves within a clade share the same color.

---

## Arrow Conventions

Phylogenetic trees rarely use arrows, but when needed:

| Element | Style | Color | Notes |
|---|---|---|---|
| Gene transfer (HGT) | Curved dashed arrow | #CC3333, 1.5px | Crosses between distant branches |
| Duplication event | Star symbol at node | #FF8F00 | Small star at duplication point |
| Loss event | X symbol on branch | #CC3333 | Indicates gene loss |
| Annotation callout | Thin line + text | #666666, 1px | Points to specific node or clade |
| Time arrow | Horizontal arrow below | #333333, 1.5px | "Present ← Past" or with dates |

---

## Clade Color Assignments

Use Classic Scientific palette for clades:

| Clade | Color | Hex |
|-------|-------|-----|
| Clade 1 | Blue | #0066CC |
| Clade 2 | Green | #339966 |
| Clade 3 | Orange | #FF6600 |
| Clade 4 | Purple | #663399 |
| Clade 5 | Red | #CC3333 |
| Unassigned | Gray | #666666 |

---

## Prompt Keywords

- "phylogenetic tree"
- "rectangular cladogram"
- "evolutionary tree diagram"
- "dendrogram with clade coloring"
- "scientific illustration, flat design, white background"

## Example Prompt Fragment

```
"Scientific journal-style rectangular phylogenetic tree on white
background. Orthogonal branching lines. Five major clades colored:
blue (#0066CC), green (#339966), orange (#FF6600), purple (#663399),
red (#CC3333). Leaf labels in 10pt sans-serif, right-aligned next
to terminal nodes. Bootstrap values (>70) as small text near internal
nodes. Scale bar at bottom showing substitutions per site.
Clade backgrounds as subtle 15% tinted vertical strips.
No shadows, no gradients, no 3D effects."
```

---

## Reference Journals

- Molecular Biology and Evolution — phylogenetic tree standards
- Systematic Biology — tree visualization conventions
- Nature — species tree and gene tree figures
