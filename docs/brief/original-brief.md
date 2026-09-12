# Task: Migrate and Simplify the Data Transformation Pipeline from Repository A to Repository B

## Mission

You are working with two repositories:

- **Repository A**: the existing/legacy repository containing the current website and its complete data-processing pipeline. = hca-open-repo. URL https://github.com/ogierMontanus/hca-open-repo 
- **Repository B**: the new repository intended to become the dedicated data-cleaning, preparation, segmentation, and build-data repository. = hca-open-repo-redesign. URL https://github.com/ogierMontanus/hca-open-repo-redesign
- 

Your task is to **investigate Repository A and migrate the relevant data-transformation logic into Repository B**, while using the migration as an opportunity to substantially simplify and improve the architecture.

Do not treat this as a mechanical copy of scripts from A to B.

The desired outcome is that **Repository B becomes the clean, maintainable home for the data preparation and build-time transformation process**, while Repository A's historical chain of JavaScript transformations is reduced, superseded, or ultimately made unnecessary.

The existing website is stable and should remain functional. The primary focus is the **backend data pipeline**, not frontend redesign.

---

# 1. Understand both repositories first

Before changing anything, thoroughly inspect both repositories.

For **Repository A**, investigate:

- all JavaScript transformation scripts;
- build scripts;
- package configuration;
- input and output files;
- CSV and spreadsheet-derived data;
- intermediate data formats;
- generated website data;
- Markdown documentation;
- README files;
- comments;
- tests;
- configuration;
- scripts that invoke other scripts;
- historical or apparently obsolete processing stages. Especially for files in format xslx, tsv from the past 2 weeks in active branches.

Read the documentation carefully, but verify it against the actual code and data.

Do not assume that Repository A's architecture is correct merely because it is currently functioning.

---

# 2. Reconstruct Repository A's actual pipeline

Before migrating anything, reconstruct the complete current data flow in Repository A.

Determine:

**source spreadsheet/CSV → transformation → intermediate data → transformation → intermediate data → final website data**

For every transformation, identify:

- input;
- output;
- purpose;
- fields affected;
- dependencies;
- assumptions;
- joins;
- normalization;
- cleaning;
- enrichment;
- restructuring;
- indexing;
- formatting;
- whether the operation is genuinely required by the website.

Create a dependency map.

The purpose is to distinguish between:

1. **essential data preparation**;
2. **website-specific preparation**;
3. **historical processing**;
4. **duplicated processing**;
5. **obsolete processing**.

---

# 3. Determine what belongs in Repository B

Repository B should become the principal home for the data-processing work that logically belongs before website generation.

Do not simply copy every JavaScript file from A.

For every component in A, determine whether it should be:

- migrated unchanged;
- migrated and refactored;
- consolidated with another transformation;
- replaced by an existing operation in B;
- moved into spreadsheet/PowerQuery processing;
- replaced by a simpler build-time transformation;
- eliminated entirely;
- left in A because it genuinely belongs to website generation.

The distinction between **data preparation** and **website presentation/runtime behaviour** is important.

---

# 4. Investigate the spreadsheet variants

Repository A and contain several versions or variants of spreadsheet-derived data in formats csv, tsv and MS-excel format. Read the  branches from the past 2 weeks.

Investigate them carefully.

Determine:

- which is authoritative;
- which are intermediate;
- what transformations already happen in Excel/PowerQuery;
- whether the same transformation is subsequently repeated in JavaScript;
- whether one of the spreadsheet variants already provides the appropriate input for B;
- whether the current JavaScript architecture exists partly because of historical spreadsheet formats.

Do not automatically move transformations into JavaScript.

Consider all reasonable locations for each operation:

- master spreadsheet;
- PowerQuery;
- Repository B preprocessing;
- Repository B build-time transformation;
- website generation.

The goal is the simplest reliable overall pipeline.

---

# 5. Use Repository B as the target architecture

Do not reproduce Repository A's architecture inside B.

Instead, ask:

> What should Repository B ideally look like if we were designing the data-preparation pipeline today, knowing everything we have learned from Repository A?

Repository B should preferably provide a clear progression such as:

**authoritative source → cleaning → preparation/normalization → segmentation/structuring → final website-ready data**

The exact architecture must be determined from the repositories.

Do not impose this example mechanically.

---

# 6. Build-time processing is preferred

The preferred architecture is **build-time transformation**.

Avoid unnecessary runtime/browser transformations.

Where a transformation can be performed once during the build process, investigate whether it should be.

The desired direction is toward:

**spreadsheet/CSV → Repository B → final data consumed by website**

rather than:

**spreadsheet/CSV → script 1 → script 2 → script 3 → script 4 → intermediate files → website**

However, retain intermediate stages where they provide a meaningful conceptual or validation boundary.

The objective is not minimum file count but minimum unnecessary complexity.

---

# 7. Existing JavaScript may be replaced completely

You are explicitly authorized to replace the existing JavaScript architecture.

Do not assume that a script in Repository A needs to survive merely because it currently works.

A transformation may be:

- rewritten;
- consolidated;
- moved;
- replaced with another technology;
- incorporated into a larger build step;
- rendered unnecessary by a better upstream data structure.

If several scripts collectively perform one conceptual operation, consider replacing them with one coherent operation.

If one large script performs several genuinely independent operations, consider separating it.

Use architectural reasoning rather than a simple "fewer files = better" rule.

---

# 8. Do not preserve obsolete intermediate formats

Repository A may contain intermediate files that were useful at an earlier stage of development.

Determine whether they are still necessary.

If not, design B so that they disappear.

Backward compatibility with obsolete intermediate files is **not a significant constraint**.

The priority is the quality of the new pipeline.

Historical files may be retained for reference, but they should not dictate the architecture of Repository B.

---

# 9. Preserve the functioning website

The current website is stable.

Repository B must ultimately produce data capable of supporting it.

However, the existing generated data format should not automatically be treated as immutable.

If the website can consume a simpler or better-structured output with minor backend or UI adjustments, that is acceptable.

Frontend changes should remain secondary.

Do not redesign the frontend simply because a backend refactoring makes it possible.

---

# 10. Look for hidden simplifications

Actively search for solutions that are not obvious from the existing architecture.

In particular, investigate whether:

- several JavaScripts can become one build operation;
- JavaScript transformations duplicate PowerQuery transformations;
- multiple intermediate CSV files can disappear;
- transformations can be performed earlier;
- several datasets can be generated from one canonical preparation stage;
- the same parsing/normalization code is repeated;
- the website is receiving data structures that were designed for an older version;
- data can be prepared once rather than repeatedly;
- a simpler intermediate representation can serve several views;
- joins can be performed once rather than separately for each output;
- existing tooling in B already makes some scripts in A redundant.

Do not restrict the investigation to the solutions that are obvious from filenames.

Trace actual data dependencies.

---

# 11. Compare alternative migration architectures

Do not immediately implement the first solution you discover.

Develop and compare plausible target architectures.

For example:

### Option A — Conservative migration
Move the necessary A scripts into B with limited refactoring.

### Option B — Consolidated pipeline
Combine several A transformations into a substantially shorter build-time pipeline.

### Option C — Data-first architecture
Move as much appropriate transformation as possible upstream into the spreadsheet/PowerQuery layer and leave B with a small, transparent preparation/build process.

### Option D — Re-engineered pipeline
Replace most of A's JavaScript transformation chain with a new architecture in B using the most appropriate available tools.

These are examples only.

If the repository suggests better alternatives, develop those instead.

Evaluate them on:

- maintainability;
- simplicity;
- reproducibility;
- transparency;
- data provenance;
- testability;
- robustness;
- build-time performance;
- ease of updating the source spreadsheets;
- suitability for scholarly data;
- future extensibility;
- clarity for future developers.

---

# 12. Establish validation before migration is considered complete

The migration must not depend on visual inspection alone.

Develop a validation strategy that compares the output of:

**Repository A's current pipeline**

with

**Repository B's proposed pipeline**.

Where appropriate, compare:

- record counts;
- identifiers;
- fields;
- values;
- joins;
- relationships;
- dates;
- sorting;
- links;
- missing values;
- duplicate handling;
- special characters;
- generated indexes;
- edge cases.

Differences should be classified as:

- identical/expected;
- intentional improvement;
- formatting-only difference;
- unexplained discrepancy.

Unexplained discrepancies must be investigated.

Where the existing system lacks tests, create appropriate tests or comparison tools as part of the migration plan.

---

# 13. First phase: investigation and plan only

**Do not immediately migrate or delete the code.**

The first phase is an architectural investigation.

Produce a report containing:

## A. Repository A analysis

What A currently does and why.

## B. Repository B analysis

What B currently does and what its intended role appears to be.

## C. Complete transformation map

A → B data-flow analysis showing all relevant stages.

## D. Migration inventory

For each relevant A script or transformation:

| Component | Current function | Destination in B | Action | Reason |
|---|---|---|---|---|
| ... | ... | ... | migrate/refactor/consolidate/eliminate | ... |

## E. Redundancy analysis

Identify transformations that can be removed or combined.

## F. Spreadsheet analysis

Explain which transformations already exist in the spreadsheet/PowerQuery layer and whether they should remain there.

## G. Target architectures

Present the strongest alternatives.

## H. Recommended architecture

Select the best target architecture and explain why.

## I. Migration sequence

Specify the safest order in which the migration should subsequently be performed.

## J. Validation strategy

Explain how equivalence and improvements will be demonstrated.

## K. Proposed removals

List scripts, intermediate files, and dependencies that can eventually become obsolete.

**Do not delete them during this investigation phase.**

---

# 14. Implementation phase comes only after the plan

After the investigation has produced a defensible architecture, the next stage will be to implement the migration.

When implementation is authorized:

1. establish the new pipeline in B;
2. migrate or replace the necessary transformations;
3. connect the appropriate source data;
4. reproduce required website output;
5. run automated comparisons;
6. investigate discrepancies;
7. update documentation;
8. only then identify obsolete components in A;
9. remove obsolete processing only after validation.

The final state should not require Repository A's old transformation chain merely to produce the website data.

---

# 15. Documentation must reflect the new architecture

As part of the eventual migration, update B's documentation so that a new developer can understand:

- where source data comes from;
- what the authoritative data is;
- what preparation takes place;
- what each build stage does;
- what files are generated;
- how the website consumes the result;
- how to reproduce the build;
- how to test it;
- what should and should not be edited manually.

Do not simply document the historical sequence of scripts.

Document the **conceptual architecture**.

---

# 16. Important constraints

### Do not:

- blindly copy Repository A into B;
- preserve historical complexity without justification;
- optimize merely for number of JavaScript files;
- make frontend redesign the main task;
- assume JavaScript is necessarily the correct technology;
- delete legacy code before validation;
- introduce unnecessary frameworks or infrastructure;
- silently change scholarly data semantics.

### Do:

- inspect both repositories deeply;
- follow actual data dependencies;
- investigate the spreadsheet variants;
- consider PowerQuery and other existing transformations;
- prefer build-time processing;
- challenge unnecessary intermediate stages;
- allow existing scripts to be completely supplanted;
- validate the new pipeline against the old one;
- document the reasoning behind architectural decisions.

---

# Guiding question

The central question is:

> **How can the data-processing logic currently distributed across Repository A be migrated into Repository B so that B becomes a clean, reproducible, build-time data-preparation pipeline, while eliminating as much historical and accidental complexity as possible and preserving the functionality of the stable website?**

Do not assume that the answer is "move the JavaScript files from A to B."

Determine what the architecture **should be**, using the actual repositories, data, documentation, and dependencies as evidence.