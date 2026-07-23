# Boltz WebApp Domain Context

## Glossary

- User: login account and isolation boundary for projects, assets, files, and tasks.
- Project: a user-owned CADD workspace for one target, study, or compound series.
- Asset: reusable project data object such as protein, prepared protein, ligand, pocket, docking result, FEP result, or SAR table.
- File: concrete persisted file under an asset or task output, such as PDB, SDF, CSV, log, or report.
- Task: computation over one or more assets whose outputs become new assets.
- Protein workbench: CADD workspace for importing, inspecting, selecting, cleaning, pocket-defining, and exporting protein structures.
- Structure selection mode: viewer mode that defines the click target granularity: atom, residue, chain, HETATM component, or pocket.
- HETATM component: non-polymer PDB group such as ligand, cofactor, metal, or water parsed from HETATM records.
- Pocket: docking search region defined by a reference ligand or residue, center coordinates, and box dimensions.
- Prepared protein: protein asset generated after CADD preparation decisions such as water handling, metal/cofactor retention, protonation, alternate-location handling, and pocket definition.
