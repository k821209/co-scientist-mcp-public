# Architecture Diagram Style Guide

For system architectures, platform designs, software stacks, and multi-layer computational frameworks.

---

## Characteristics

- Layered structure (top → bottom or left → right)
- Components grouped by function or domain
- Data flows between layers/components
- Often shows both internal structure and external interfaces
- May include databases, APIs, user interfaces, and processing modules

---

## Layout Patterns

### Layered Architecture (Top → Bottom)
```
┌──────────────── User Interface Layer ───────────────┐
│  [Web Portal]      [API Gateway]      [Dashboard]   │
└────────────────────────┬────────────────────────────┘
                         ▼
┌──────────────── Application Layer ──────────────────┐
│  [Module A]    [Module B]    [Module C]              │
└────────────────────────┬────────────────────────────┘
                         ▼
┌──────────────── Data Layer ─────────────────────────┐
│  [Database]    [Object Store]   [Cache]             │
└─────────────────────────────────────────────────────┘
```

### Platform Architecture
```
┌── Input ──┐     ┌── Processing ──────────┐     ┌── Output ──┐
│ [Source 1] │     │ ┌──────┐   ┌────────┐ │     │ [Result A] │
│ [Source 2] │────→│ │ Core │──→│ Engine │ │────→│ [Result B] │
│ [Source 3] │     │ └──────┘   └────────┘ │     │ [Report]   │
└────────────┘     └───────────────────────┘     └────────────┘
```

### Microservice / Component Architecture
```
┌─────────┐     ┌─────────┐     ┌─────────┐
│Service A│◄───►│Service B│◄───►│Service C│
└────┬────┘     └────┬────┘     └────┬────┘
     │               │               │
     └───────────────┼───────────────┘
                     ▼
              ┌──────────────┐
              │  Shared DB   │
              └──────────────┘
```

---

## Element Conventions

| Element | Shape | Fill | Border | Notes |
|---------|-------|------|--------|-------|
| Application module | Rounded rectangle | 30% tint of category | Category color, 2px | 100–150px wide |
| AI / ML component | Rounded rectangle | Indigo 30% tint (#C0C4EC) | Indigo (#1A237E), 2px | Highlighted as AI component |
| Database | Cylinder | Light tint | #666666, 2px | Standard DB icon shape |
| API / Interface | Rectangle | White | Teal (#00838F), 2px | Thin, wide rectangle |
| External service | Dashed rounded rectangle | White | #999999, 2px dashed | Shows external dependency |
| User / Actor | Circle or stick figure | White | #333333, 2px | At top of diagram |
| Layer group | Large dashed rectangle | 15% tint | Layer color, 2px dashed | Labeled with layer name |
| Cloud service | Cloud shape | Light tint | #666666, 1.5px | For cloud infrastructure |

---

## Arrow Conventions

| Relationship | Arrow | Color | Notes |
|---|---|---|---|
| Data flow | Solid, filled triangle → | #333333 | 2.5px, shows data movement |
| API call | Solid, filled triangle → | Teal (#00838F) | 2px, between services |
| Bidirectional | Double-headed solid ↔ | #333333 | 2px |
| Async / message queue | Dashed, filled triangle → | #FF8F00 | 2px, for event-driven |
| User interaction | Solid, open triangle ▷ | #666666 | 1.5px |
| Dependency | Dotted, open triangle ▷ | #999999 | 1.5px, "uses" relationship |

**Layer transitions**: Arrows crossing layer boundaries should be vertical and centered.

---

## Prompt Keywords

- "system architecture diagram"
- "platform design overview"
- "software stack visualization"
- "layered architecture"
- "scientific computing platform"
- "flat design, white background, technical illustration"

## Example Prompt Fragment

```
"Scientific journal-style layered platform architecture diagram on white
background. Three horizontal layers: 'Data Input' (top), 'AI Processing'
(middle), 'Output' (bottom). Modules as rounded rectangles — data modules
in teal (#B9DEE1) fill, AI modules in indigo (#C0C4EC) fill, output modules
in amber (#FFE3B8) fill. Databases as cylinder shapes. Solid dark arrows
(#333333, 2.5px) showing data flow between layers. Layer groups as dashed
rectangles with 15% tinted backgrounds. Clean sans-serif labels.
No shadows, no gradients."
```

---

## Reference Journals

- Nature Biotechnology — bioinformatics platform architectures
- Nucleic Acids Research — database/tool architecture figures
- Bioinformatics — computational pipeline system designs
