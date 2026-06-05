# Style Guide Index

Maps diagram types to their corresponding style guides.

---

## Available Style Guides

| Type Key | Name | Style Guide | Best For |
|----------|------|-------------|----------|
| `pathway` | Pathway Diagram | [pathway_diagram.md](styles/pathway_diagram.md) | Metabolic pathways, biosynthesis routes, signaling cascades |
| `network` | Network Diagram | [network_diagram.md](styles/network_diagram.md) | PPI networks, gene regulatory networks, co-expression |
| `workflow` | Workflow / Pipeline | [workflow_pipeline.md](styles/workflow_pipeline.md) | Research protocols, bioinformatics pipelines, multi-stage processes |
| `comparison` | Comparison Chart | [comparison_chart.md](styles/comparison_chart.md) | Bar charts, treatment vs control, statistical comparisons |
| `architecture` | Architecture Diagram | [architecture_diagram.md](styles/architecture_diagram.md) | System designs, platform architectures, software stacks |
| `heatmap` | Heatmap / Matrix | [heatmap_matrix.md](styles/heatmap_matrix.md) | Gene expression, correlation matrices, clustered data |
| `tree` | Phylogenetic Tree | [phylogenetic_tree.md](styles/phylogenetic_tree.md) | Evolutionary trees, dendrograms, hierarchical classification |

---

## Auto-Detection Rules

When the user does not specify `--type`, detect the diagram type from content keywords:

### Pathway (`pathway`)
- Keywords: pathway, biosynthesis, metabolism, enzyme, catalysis, conversion, substrate, product, metabolite, reaction, flux, precursor, intermediate, compartment, chloroplast, cytoplasm, ER
- Also matches: "from X to Y synthesis", "production route", "bio-conversion"

### Network (`network`)
- Keywords: network, interaction, PPI, protein-protein, gene regulatory, GRN, co-expression, hub, node, edge, connectivity, module, cluster, interactome
- Also matches: "interaction map", "regulatory network", "signaling network"

### Workflow (`workflow`)
- Keywords: workflow, pipeline, protocol, process, step, stage, procedure, analysis pipeline, bioinformatics pipeline, data processing, preprocessing, input, output
- Also matches: "step-by-step", "experimental procedure", "data analysis flow"

### Comparison (`comparison`)
- Keywords: comparison, compare, bar chart, treatment, control, versus, vs, fold change, expression level, statistical, significance, error bar, grouped
- Also matches: "before and after", "wild type vs mutant", "dose response"

### Architecture (`architecture`)
- Keywords: architecture, platform, system, framework, infrastructure, layer, module, service, API, database, stack, integration, pipeline architecture
- Also matches: "system design", "platform overview", "technical architecture"

### Heatmap (`heatmap`)
- Keywords: heatmap, heat map, correlation, matrix, expression matrix, clustering, dendrogram, gene expression, transcriptome, annotation bar
- Also matches: "expression profile", "correlation analysis", "clustered expression"

### Tree (`tree`)
- Keywords: phylogenetic, tree, cladogram, dendrogram, evolutionary, taxonomy, divergence, clade, bootstrap, branch length, species tree
- Also matches: "evolutionary relationship", "taxonomic classification", "gene tree"

---

## Fallback

If no keywords match or the content is ambiguous:
1. Default to `workflow` if the content describes a sequential process
2. Default to `pathway` if biological entities and reactions are mentioned
3. Default to `architecture` if system components and data flows are described
4. Ask the user to specify `--type` if still uncertain

---

## Multi-Type Figures

If the content spans multiple diagram types (e.g., a pathway embedded in an architecture):
1. Use the **primary** diagram type for overall layout
2. Reference the **secondary** style guide for specific sub-elements
3. Document both in the pipeline report
