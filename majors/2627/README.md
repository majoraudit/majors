# Major Template + Processing System

This repository defines how Major Templates are stored and processed using MQL (Major Query Language) — a custom domain-specific language designed to describe academic requirements in a structured, visual, and auditable way.

MQL 0.2 lets developers or administrators define course requirements as named requirements with typed course predicates, credit and course counts, scoped constraints, sharing rules, choices, facts, and effects. Each program compiles to a versioned semantic IR that an audit engine consumes.

## Overview

Each major has a folder that includes a main json and mql files. The json includes basic information about the major, the format of which can be seen in computer_science.json. Within are links to .mql templates (for various specialties such as ba/bs or globliast/specialist or geographical locations). These templates are compiled into the MQL 0.2 semantic IR (JSON) and then processed by the MajorAudit rules engine. `yale-institution.json` declares the catalog and transcript fields, enums, grade order, and fact types the programs may use.

An example of a completed MajorTemplate can be seen with the computer_science major.

## Catalog manifest

`manifest.json` is the coverage source of truth for the 2026–2027 catalog. Its
major inventory comes from Yale's **Majors in Yale College** page, while each
major's `programs` list comes from manual review of the linked subject page.

A program is listed separately when Yale describes materially different audit
requirements for a degree, concentration, track, or intensive curriculum.
Choices that share the same audit logic remain within one MQL program. This
includes elective choices, senior-project options, distinction in the major,
and concentrations that change only the subject of an otherwise identical set
of requirements. Generic simultaneous-master's guidance is also not a separate
program unless the subject page presents the combined degree as one of the
major's offered degree programs.

The manifest's program IDs are semantic identifiers, not filenames. Each
major's `<major-id>.json` file maps those programs, in the same order, to the
MQL filenames in `specializations`. `validate.py` checks that the catalog
inventory, program counts, JSON mappings, files, and parsed MQL requirements
agree, and it compiles every program with the institution schema.

## Set up testing environment
Programs are written in MQL 0.2 (see `MQL_Language_Specification.md` at the repository root) and need pylibmql 0.3.0 or later.

1. Install the compiler:
   ```bash
   pip install --upgrade pylibmql
   ```
2. Check the version:
   ```py
   import pylibmql
   print(pylibmql.__version__)  # 0.3.0 or later
   ```
3. Compile a program against the Yale institution schema in this directory:
   ```py
   import pylibmql

   SOURCE = """
   program example {
     catalog 2026-2027
     institution "https://majoraudit.org/mql/yale" @ "2026-2027"
     credit_scale 2
   }

   requirement linear_algebra "Linear algebra with proofs" [core] {
     slot from [MATH 2250, MATH 2260];
   }

   requirement electives "Two MATH courses numbered 3000 or above" [elective] {
     courses at least 2 where course.subject = "MATH" and course.number >= 3000;
   }
   """

   institution = open("majors/2627/yale-institution.json").read()
   ir = pylibmql.compile_program(SOURCE, "example.mql", institution)
   print(ir.version())       # 0.2.0, the IR schema version
   print(ir.json_pretty())   # the semantic IR an audit engine consumes
   ```
   Compilation errors raise `ValueError` with every diagnostic as `path:line:column: CODE: message`.
4. Validate the whole repository from the root:
   ```bash
   python validate.py
   ```
