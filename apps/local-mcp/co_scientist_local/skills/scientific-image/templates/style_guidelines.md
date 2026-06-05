# Academic Visual Standards for Scientific Figures

Style guidelines following Nature, Science, and Cell publication standards.

---

## General Principles

1. **Clarity over decoration**: Every visual element must serve a communicative purpose
2. **Consistent visual language**: Same shape = same category throughout the figure
3. **Minimal ink**: Remove anything that doesn't add information (Tufte's data-ink ratio)
4. **Reproducible colors**: Use exact hex codes, never rely on color names
5. **Accessible design**: Ensure readability at 50% zoom; avoid red-green only distinctions

---

## Typography

| Element | Font Style | Size Range | Color |
|---------|-----------|------------|-------|
| Figure title | Bold sans-serif | 14–18pt | #1A1A1A |
| Section labels | Bold sans-serif | 11–14pt | #1A1A1A |
| Node/box labels | Regular sans-serif | 9–12pt | #1A1A1A or white on dark fill |
| Edge/arrow labels | Regular sans-serif | 8–10pt | #333333 |
| Annotations | Italic sans-serif | 8–10pt | #555555 |
| Axis labels | Regular sans-serif | 10–12pt | #1A1A1A |
| Legend text | Regular sans-serif | 9–11pt | #333333 |

**Font families** (in prompt): "Arial", "Helvetica", or "sans-serif". Never use serif fonts for labels in diagrams.

**Contrast rule**: Text on colored background must have contrast ratio >= 4.5:1. Use white (#FFFFFF) text on dark fills (luminance < 40%), black (#1A1A1A) text on light fills.

---

## Node / Shape Conventions

| Entity Type | Shape | Fill | Border | Size |
|-------------|-------|------|--------|------|
| Gene / Protein | Rounded rectangle | Palette primary, 30% tint | Palette primary, 2px | 80–120px wide |
| Metabolite / Compound | Ellipse / pill | Palette secondary, 30% tint | Palette secondary, 2px | 60–100px wide |
| Enzyme / Catalyst | Diamond or hexagon | Palette tertiary, 30% tint | Palette tertiary, 2px | 50–80px |
| Process / Step | Rectangle | White or light tint | Palette primary, 2px | 100–160px wide |
| Database / Data store | Cylinder | Palette neutral, 15% tint | #666666, 1.5px | 60–80px wide |
| Decision | Diamond | White | #333333, 2px | 60–80px |
| Input/Output | Parallelogram | Light tint | #666666, 1.5px | 80–120px wide |
| Group / Compartment | Dashed rectangle | 15% tint of group color | Group color, 2px dashed | — |

**Rounding**: All rounded rectangles use 8–12px corner radius. Circles and ellipses have smooth curves.

---

## Arrow / Edge Conventions

| Relationship | Line Style | Arrowhead | Color | Width |
|---|---|---|---|---|
| Activation / catalysis | Solid | Filled triangle (→) | #333333 | 2px |
| Inhibition | Solid | Flat bar (⊣) | #CC3333 | 2px |
| Conversion / flow | Solid | Filled triangle (→) | Palette primary | 2.5px |
| Regulatory (positive) | Dashed | Open triangle (▷) | #339966 | 1.5px |
| Regulatory (negative) | Dashed | Flat bar (⊣) | #CC3333 | 1.5px |
| Bidirectional | Solid | Both ends (↔) | #333333 | 2px |
| Weak / predicted | Dotted | Open triangle (▷) | #999999 | 1.5px |
| Data flow | Solid | Filled arrow (→) | Palette secondary | 2px |
| Feedback loop | Curved/arc | Filled triangle (→) | Palette accent | 2px |

**Critical rules**:
- Every arrow MUST have a clearly defined source and target
- Arrowheads must be large enough to distinguish type (≥6px head size)
- Arrow paths should not cross unless unavoidable; use routing to minimize crossings
- Parallel arrows between same nodes must be offset (≥8px gap)
- Label arrows at their midpoint, offset from the line

---

## Layout Principles

### Spacing
- **Minimum node spacing**: 40px between edges of adjacent nodes
- **Arrow label offset**: 6–10px from the arrow line
- **Group padding**: 20–30px inside dashed group boundary
- **Figure margin**: 40–60px from content to figure edge

### Alignment
- Nodes within the same hierarchy level should be horizontally or vertically aligned
- Use grid-based placement (snap to invisible grid)
- Center labels within their nodes

### Flow Direction
| Diagram Type | Primary Flow | Secondary Flow |
|---|---|---|
| Pathway / pipeline | Left → Right or Top → Bottom | — |
| Network | Radial or force-directed | — |
| Hierarchy / tree | Top → Bottom | Left → Right |
| Comparison | Left | Right (side by side) | — |
| Architecture | Top → Bottom (layers) | Left → Right within layer |

---

## Background and Framing

- **Figure background**: Pure white (#FFFFFF) — required for publication
- **Group regions**: 15% tint with dashed border (2px, matching color)
- **No drop shadows** on any element
- **No gradients** on fills (flat color only)
- **No 3D effects** anywhere
- **Border around entire figure**: Optional, 1px #CCCCCC if needed

---

## Legend / Key

When the figure uses more than 3 distinct colors or shapes:
- Place legend in bottom-right or bottom-center
- Use small (16×16px) shape samples next to labels
- Group by category (e.g., "Nodes", "Arrows")
- Font size: 9–10pt, #333333

---

## Scale and Resolution

| Output Use | Recommended Size | DPI |
|---|---|---|
| Grant proposal (print) | 4K, 16:9 | 300 |
| Journal figure | 4K, 4:3 or 3:2 | 300 |
| Presentation slide | 2K or 4K, 16:9 | 150–300 |
| Web / screen only | 2K, 16:9 | 72–150 |

---

## Prompt Construction Template

When building the final generation prompt, always include these layers in order:

```
1. [STYLE] "Scientific journal figure, flat design, clean white background, no shadows, no gradients, sans-serif font, Nature-style illustration"
2. [LAYOUT] "Left-to-right metabolic pathway" or "Top-down architecture diagram" etc.
3. [ENTITIES] List every node with exact shape, fill hex, border hex, label
4. [RELATIONSHIPS] List every arrow with source→target, line style, color hex, arrowhead type
5. [GROUPS] Compartments/regions with dashed borders and tinted fills
6. [LABELS] All text labels with positions and sizes
7. [NEGATIVE] "No 3D effects, no drop shadows, no gradients, no decorative elements, no photo-realistic textures"
```
