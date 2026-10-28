---
title: Major Query Language (MQL)
subtitle: Language Specification, version 0.2
date: 28 October 2026
---

## Abstract

Major Query Language (MQL) 0.2 is a declarative language for Yale major requirements. A program names its requirements, says how each one counts (slots, courses, credits, or satisfied children), selects courses by explicit lists or typed predicates over catalog and transcript fields, and adds constraints, sharing rules, choices, facts, and effects. Every construct compiles to exactly one node of the MQL 0.2 semantic intermediate representation (IR), whose counting, activation, scope, sharing, and explanation rules are fixed by RFC 0001. An audit or planning engine reads the IR together with an institution schema, a catalog, a transcript, and a student profile; it never reads source comments or catalog prose.

This document specifies the language as implemented by `pylibmql` / `libmql` 0.3.0 (RFC 0002 surface grammar, IR `schema_version` 0.2.0) and records the conventions this repository uses to encode the 2026–2027 Yale College catalog with it: the Yale institution schema, role names, approvals, and the patterns for non-course requirements.

**Implementation baseline:** `libmql` / `pylibmql` 0.3.0, IR schema 0.2.0
**Upstream revision:** `cfab5f465144457db8f8f2059037c35eeba43181` (majoraudit/major-requirement-parser)
**Normative sources:** RFC 0001 (semantic IR), RFC 0002 (surface grammar), `docs/schemas/mql-ir-0.2.schema.json`, `libmql/src/mql2.pest`, `libmql/src/compiler.rs`
**Status:** Implementation-derived reference. Where this document and the RFCs differ, the RFCs govern.

MQL 0.1.12 (`SELECT … FROM …`, `PLACEMENT`, `TAG`, `RANGE`, `LIMIT`, variables, and externals) is a separate, frozen language. It is described only in Appendix B, which maps each 0.1 construct to its 0.2 form. The tools never infer the language version from file contents: `mql FILE` and `pylibmql.parse` read 0.1 source; `mql --compile FILE` and `pylibmql.compile_program` read 0.2 source.

## 1. Conformance and terminology

The key words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** have their RFC 2119 meanings.

- A **program** is one `.mql` source file. It describes one degree program: a major, degree, track, or concentration.
- A **requirement** is a named node that counts **attempts** (transcript entries) toward a lower bound and an optional upper bound. Requirements nest.
- A **count statement** is the single statement in a requirement body that declares how the requirement counts and what it selects.
- A **selector** chooses the attempts that may be assigned to a requirement: a course list, a predicate, or (implicitly) the requirement's children.
- A **predicate** is a typed Boolean expression over fields of the catalog course, offering, transcript attempt, or student profile.
- A **condition** is a Boolean expression over choices and facts. Conditions activate requirements, constraints, sharing rules, and effects.
- A **constraint** restricts the set of attempts assigned within a **scope**.
- A **choice** is a named, finite decision (a declared track, or an alternative the solver may pick).
- A **fact** is a typed statement about the student (a placement, a proficiency, or an approval).
- An **effect** changes the program when a condition holds: it waives, activates, rebounds, substitutes, re-obligates, or permits.
- The **institution schema** declares the fields, enums, grade order, joins, and fact types that predicates and facts may use.
- An **audit** assigns a student's attempts to requirements so as to satisfy as many active required roots as possible; RFC 0001 §5 fixes its objective.

## 2. Source model

A file is a header followed by any number of items in any order:

```ebnf
file ::= header item*
item ::= choice | fact | requirement | constraint | share | effect
```

Source order has no semantic meaning except for generated node order. Every declaration has an author ID that is unique across the whole program: choices, facts, requirements at every depth, constraints, sharing rules, and effects share one namespace.

### 2.1 Example

```mql
// Computer Science B.A.: ten term courses taken for letter grades, including the senior project.
program computer_science_ba {
  catalog 2026-2027
  institution "https://majoraudit.org/mql/yale" @ "2026-2027"
  credit_scale 2
}

// CPSC 3230 replaces the CPSC 3231-3232 pair and adds one elective.
choice systems "Systems sequence": solver one of "split", "combined";

requirement discrete "Core: discrete mathematics (CPSC 2020 or MATH 2440)" [core] {
  slot from [CPSC 2020, MATH 2440];
}

requirement systems_split "Core: CPSC 3231 and 3232" [core] when systems = "split" {
  courses exactly 2 from [CPSC 3231, CPSC 3232];
}

requirement systems_combined "Core: CPSC 3230" [core] when systems = "combined" {
  slot from [CPSC 3230];
}

requirement electives "Intermediate or advanced electives (four if CPSC 3230 is taken)" [elective] {
  courses at least (systems: "split" => 3, "combined" => 4)
    where course.attributes contains "YC CPSC Elective" or attempt.approved_for contains "electives";
  constraint outside_electives "At most one advanced course from another department":
    at most 1 attempts where not course.attributes contains "YC CPSC Elective";
}

constraint one_algorithms "Only one of CPSC 3650 or 3660 counts" in program:
  limit 1 attempts where course.code in ["CPSC3650", "CPSC3660"];

constraint letter_grades "All courses in the major taken for a letter grade" in program:
  all where attempt.grading_mode = "letter";

constraint total_courses "Ten term courses in all" in program:
  total at least 10 attempts;
```

## 3. Lexical structure

### 3.1 Whitespace and comments

Space, tab, carriage return, and line feed are insignificant between tokens. Line comments begin with `//`; block comments are `/* … */` and do not nest. Comments are ignored by the compiler; any rule an engine must enforce belongs in code, not in a comment.

### 3.2 Keywords and identifiers

Keywords are lowercase and must end at a word boundary, so `intro` is an identifier and not `in` followed by `tro`. Identifiers match `^[a-z][a-z0-9_]*$` and become IR author IDs. The words `and or not true false null fact in is where from when before match` are reserved and cannot be identifiers. Other keywords (`program`, `requirement`, `courses`, `limit`, …) are matched only where the grammar expects them.

### 3.3 Literals

- **Strings** use double quotes. `\"` and `\\` are the only escapes; strings cannot contain a raw line feed.
- **Integers** are optionally signed decimal digits. Counts and constraint amounts other than credits must be whole numbers.
- **Numbers** in amounts may have a decimal part (`1.5`). A credit amount is multiplied by `credit_scale` and must then be a whole number of units: `credits at least 1.5` is valid at scale 2 (3 units); `1.25` is rejected (`MQL0303_AMOUNT`).
- **Booleans** are `true` and `false`; `null` is a predicate value.
- **Value lists** are `[v, …]`, used with `in` and `overlaps`.

### 3.4 Course codes

A course code is 2–5 uppercase letters or `&`, optional spaces, and 3–4 digits with an optional uppercase suffix: `CPSC 2010`, `S&DS 2380`, `CHEM 1340L`. In a course list it becomes the canonical ID with the spaces removed (`CPSC2010`). A quoted string in a course list is taken verbatim as a canonical ID, which is how codes outside that shape are written, for example the Summer Session course `"PSYCS1390"` (PSYC S1390).

Inside predicates, course codes are ordinary strings: `course.code = "CPSC3650"`.

## 4. Program header

```ebnf
header ::= "program" ident "{" ( "catalog" YYYY-YYYY
                               | "institution" string "@" string
                               | "credit_scale" integer )* "}"
```

`catalog` and `institution` are required; each entry may appear once (`MQL0310_HEADER`). `credit_scale` defaults to 1. If an institution schema is supplied, its `schema_id` and `version` must equal the header's (`MQL0307_INSTITUTION_MISMATCH`). The program ID becomes the IR `program_id`, and generated node IDs have the form `program_id::author_id`.

## 5. Requirements

```ebnf
requirement ::= obligation? "requirement" ident string? roles? ("when" condition)?
                "{" ( count | requirement | constraint )* "}"
obligation  ::= "required" | "optional" | "advisory"
roles       ::= "[" ident, … "]"
count       ::= kind bounds? selector? ("each" number "credits")? ";"
kind        ::= "slot" | "courses" | "canonical" "courses" | "credits" | "assignments" | "children"
bounds      ::= "exactly" amount | "at" "least" amount | "at" "most" amount
              | "between" amount "and" amount
amount      ::= number | "(" ident ":" scalar "=>" number, … ")"
selector    ::= "from" "[" course, … "]" | "from" "requirements" "[" ident, … "]"
              | "where" predicate
```

The singular spellings `course`, `credit`, and `assignment` are accepted for `courses`, `credits`, and `assignments`.

### 5.1 Count statements

A requirement body has exactly one count statement (`MQL0301_COUNT_STATEMENT`).

| Count kind | IR contribution | Unit | Meaning |
| --- | --- | --- | --- |
| `slot` | `SLOT` | `SLOTS` | One attempt fills the requirement. Without bounds, exactly 1. |
| `courses` | `DISTINCT_ATTEMPTS` | `COURSES` | Number of distinct assigned attempts. |
| `canonical courses` | `DISTINCT_CANONICAL_COURSES` | `COURSES` | Number of distinct catalog courses (repeats and cross-listings count once). |
| `credits` | `CREDITS` | `CREDIT_UNITS` | Sum of the assigned attempts' earned credit units. |
| `assignments` | `ASSIGNMENTS` | `ASSIGNMENTS` | Number of assignment edges, including permitted sharing. |
| `children` | `NESTED_SATISFACTION` | `BOOLEAN_CHILDREN` | Number of satisfied nested requirements. |

Every kind except `slot` requires bounds (`MQL0302_MISSING_BOUND`). A count with neither a selector nor nested requirements is an error (`MQL0304_MISSING_SELECTOR`). A count without a selector selects its nested requirements. `each n credits` fixes the credit value of every assigned attempt (`fixed_credit_units`).

### 5.2 Bounds

| Bound | Lower | Upper |
| --- | --- | --- |
| `exactly n` | n | n |
| `at least n` | n | none |
| `at most n` | 0 | n |
| `between a and b` | a | b |

A parenthesized amount `(choice: v1 => n1, v2 => n2)` is a `CHOICE_TABLE` bound: the bound is looked up from the named choice's value, and every alternative of the choice must have a case. Upper bounds cap the attempts assigned to the requirement; extra matching attempts are not a failure and remain free for other requirements (RFC 0001 §5). A lower bound of 0 is allowed; such a requirement is always satisfied and serves as a pool that lets otherwise-unassigned courses count toward a total.

### 5.3 Selectors

- `from [CPSC 2010, MATH 2440]` is a `COURSE_LIST`. An attempt matches when its canonical course is in the list.
- `where predicate` is a `PREDICATE` selector (§7).
- `from requirements [a, b]` is `CHILD_REQUIREMENTS` over named requirements.
- With no selector, the count statement ranges over the requirement's nested children.

### 5.4 Nesting, activation, and obligation

Nested `requirement` blocks become IR `children`. A child inherits its parent's obligation unless it declares its own, and every descendant inherits its ancestors' activation. `when` defaults to `true`.

- `required` (the default) roots determine completion and progress.
- `optional` roots are evaluated but do not affect completion; their assignments may count toward explicitly named totals.
- `advisory` roots are informational and receive no assignments. This repository uses them only for rules that no record can witness (for example, "graduate grades must average High Pass").

An inactive requirement contributes nothing and is not satisfied. A program's completion requires every active required root to be satisfiable and every active constraint to hold at the same time.

### 5.5 Roles

The bracketed list after the description assigns roles: `[core]`, `[prerequisite, mathematics]`. Roles name sets of requirements for constraint scopes (`in roles [core, elective, senior]`). They carry no meaning beyond that.

## 6. Constraints

```ebnf
constraint ::= "constraint" ident string? ("when" condition)? ("in" scope)? ":" body ";"
scope      ::= "direct" ident | "subtree" ident | "requirements" "[" ident, … "]"
             | "roles" "[" ident, … "]" | "branch" ident "=" scalar | "program"
body       ::= ("at" "least" | "at" "most" | "exactly") number unit "where" predicate
             | "all" "where" predicate
             | "group" field ( "distinct" "at" "least" n | "distinct" "exactly" n | "same"
                             | "at" "most" n "per" "group" | "at" "least" n "per" "group" )
             | "limit" number unit "where" predicate
             | "total" "at" "least" number unit ("where" predicate)?
             | "repeat" "at" "most" n "times" "where" predicate
             | "order" predicate "before" predicate
unit       ::= "attempts" | "canonical" "courses" | "credits" | "assignments"
```

| Body | IR kind | Holds when |
| --- | --- | --- |
| `at least / at most / exactly n unit where p` | `SELECTED_SET` | the scoped selected set contains that many units matching `p` |
| `all where p` | `SELECTED_SET` (`ALL`) | every attempt in the scope matches `p` |
| `group field …` | `GROUP` | the selected set's values of `field` meet the grouping rule |
| `limit n unit where p` | `LIMIT` | at most `n` units matching `p` are used in the scope |
| `total at least n unit (where p)?` | `TOTAL` | the scope's distinct used units reach `n` |
| `repeat at most n times where p` | `REPEAT` | no more than `n` attempts of the matching canonical course contribute |
| `order p before q` | `ORDERING` (strict) | a contributing attempt matching `p` has a strictly earlier term than one matching `q` |

`SELECTED_SET` constraints cannot count `assignments`. Credit amounts in constraints are written in course credits and scaled, as in counts.

A constraint declared inside a requirement defaults to `in direct <that requirement>` and is attached to the requirement's `constraint_ids`. A top-level constraint MUST declare a scope (`MQL0309_MISSING_SCOPE`); MQL 0.2 has no unscoped constraints.

| Scope | Attempts in scope |
| --- | --- |
| `direct r` | attempts assigned directly to `r` |
| `subtree r` | attempts assigned to `r` or any descendant |
| `requirements [a, b]` | attempts assigned directly to the named requirements |
| `roles [x, y]` | attempts assigned to any active requirement carrying one of the roles |
| `branch c = v` | attempts assigned while choice `c` has value `v` |
| `program` | every active program assignment |

Grouping ignores attempts whose group field is missing. A `group` constraint has no predicate of its own; it applies to the whole scope.

## 7. Conditions and predicates

```ebnf
condition ::= condition "or" condition | condition "and" condition | "not" condition
            | "(" condition ")" | "true" | "false" | "fact" ident | ident ("=" | "!=") scalar
predicate ::= predicate "or" predicate | predicate "and" predicate | "not" predicate
            | "(" predicate ")" | field "is" ("null" | "unknown")
            | field op value ("match" ("canonical" | "enrolled_as" | "either"))?
field     ::= ("course" | "offering" | "attempt" | "student") "." ident
op        ::= "=" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "contains" | "overlaps"
value     ::= scalar | "null" | "[" value, … "]"
```

`not` binds tighter than `and`, which binds tighter than `or`; chains flatten into one `AND`/`OR` node. Use parentheses whenever a predicate mixes `and` and `or` across different fields. `choice != v` lowers to `NOT CHOICE_EQUALS`.

The record targets `course`, `offering`, `attempt`, and `student` map to `CATALOG_COURSE`, `OFFERING`, `TRANSCRIPT_ATTEMPT`, and `STUDENT_PROFILE`. A field's type comes from the institution schema, so a program that uses predicates or group fields MUST be compiled with one (`MQL0305_UNKNOWN_FIELD`). The compiler checks that the schema allows the operator on that field (`MQL0306_OPERATOR_NOT_ALLOWED`) and that enum and grade literals are declared members (`MQL0311_UNKNOWN_VALUE`). `match canonical | enrolled_as | either` is valid only on `COURSE_CODE` fields (`MQL0225_INVALID_OPERATOR`).

An ordinary predicate is false when the data it needs is missing; `is null` and `is unknown` test for missing data explicitly. Grades compare by the schema's grade order, never lexically.

## 8. Sharing

```ebnf
share ::= ("share" | "exclusive") ident string? ("when" condition)? ":" ident ("," ident)+ ";"
```

The program default is exclusive: an attempt counts toward at most one named requirement, and never fills two slots of the same requirement. Every nested requirement has its own author ID, so siblings are exclusive of each other too.

`share s: a, b, c;` permits every pair among `a`, `b`, and `c`, and permits one attempt to appear in all three. Because a rule permits every pair it lists, two requirements that may each share with a third but not with each other need two rules (`share s1: a, c;` and `share s2: b, c;`). Constraints, repeat rules, and grade rules still apply to shared attempts. A distinct total over several receiving requirements counts a shared attempt once.

## 9. Choices, facts, and effects

```ebnf
choice ::= "choice" ident string? ":" owner "one" "of" scalar ("," scalar)* ";"
owner  ::= "declared" | "solver" | "planning" | "fact" ident
fact   ::= "fact" ident string? ":" "approval"? ident ( "{" ident ":" scalar, … "}" )? ";"
effect ::= "effect" ident string? "when" condition ":" action ";"
action ::= "waive" ident | "activate" ident | "deactivate" ident
         | "set" ("lower" | "upper") "of" ident "to" number
         | "substitute" ident "with" ident | "make" ident obligation
         | "permit" ident "where" predicate
```

**Choices.** A choice's value type comes from its first alternative. `declared` choices come from the student profile (a declared track or concentration); evaluation is indeterminate when the profile omits them, and the audit never changes them. `solver` choices pick among catalog-equivalent alternatives (for example a one- or two-term senior essay); the audit picks the best value. `planning` choices exist only for future-plan construction. `fact f` choices are fixed by a fact.

**Facts.** The fact type (the identifier after the colon) MUST exist in the institution schema, `approval` MUST match the schema's declaration, and every parameter MUST be declared there (`MQL0308_UNKNOWN_FACT_TYPE`). A fact is present when the student profile records it; `when fact f` tests presence.

**Effects.** Effects are evaluated from the original program state and applied as a set, so source order does not matter. Identical effects are idempotent; two different effects writing the same bound, activation, substitution target, or obligation are a conflict that invalidates evaluation. `set … to n` is measured in the target's unit (credit targets are scaled). `waive` marks a requirement satisfied while keeping the fact or approval as its witness.

## 10. Semantics summary

The following RFC 0001 rules decide how an engine counts. They are restated here because the encodings in §12 depend on them.

1. **Slots versus pools.** `slot` fills once. `courses at least n` is one pool that accepts many distinct attempts; there is no need to repeat a selector `n` times.
2. **Exclusive by default.** An attempt is assigned to at most one named requirement unless a `share` rule permits it.
3. **Upper bounds cap assignments.** They never make a requirement fail because a student took more matching courses.
4. **Nested satisfaction counts 1.** A satisfied child contributes 1 to a `children` count, regardless of its own size.
5. **Credits are integers.** With `credit_scale 2`, a half-credit lab is 1 unit and a 1.5-credit studio is 3 units. Earned credit comes from the transcript attempt; failed, withdrawn, and non-credit attempts contribute nothing.
6. **Inactive means absent.** A requirement whose `when` is false contributes nothing, receives nothing, and is not part of completion.
7. **Constraints are mandatory while active.** There are no soft constraints; informational rules are advisory requirements.
8. **Progress** for an active required root is `min(q, lower) / lower`, an exact rational. The default explanatory witness maximizes satisfied roots, then progress, then course-witnessed (not approval-witnessed) assignments.
9. **Priority is gone.** The 0.1 priority field has no 0.2 equivalent; display order is source order.

## 11. The Yale institution schema

`majors/2627/yale-institution.json` is the institution schema for the 2026–2027 catalog (`schema_id` `https://majoraudit.org/mql/yale`, version `2026-2027`). It validates against `institution-schema-0.2.schema.json`. Every program in this repository names it in its header.

### 11.1 Fields

| Field | Type | Operators | Notes |
| --- | --- | --- | --- |
| `course.subject` | enum `subject` | `=` `!=` `in` | Canonical subject code. The enum lists 129 Yale codes (including `BLST`, `CPLT`, `HELN`, `E&EB`/`EEB`), so subject literals are checked by the compiler. |
| `course.number` | integer | `=` `!=` `<` `<=` `>` `>=` `in` | Numeric part of the course number (`CHEM 1340L` → 1340). |
| `course.code` | course code | `=` `!=` `in` | Canonical ID, e.g. `"CPSC2010"`; supports `match`. |
| `course.credits` | credit | comparisons | Catalog credit value. Avoided in predicates until literal scaling is specified (§14). |
| `course.attributes` | set | `contains` `overlaps` | Yale Course Search attributes ("YC CPSC Elective"). Values must appear in `tag_values`. |
| `course.distributionals` | set | `contains` `overlaps` | `Hu`, `So`, `Sc`, `QR`, `WR`, `L1`–`L5`. |
| `course.format` | enum `course_format` | `=` `!=` `in` | `lecture`, `seminar`, `lab`, `studio`, `tutorial`, `independent_study`, `research`, `senior_project`, `colloquium`, `language`. |
| `course.language` | string, nullable | `=` `!=` `in` `is null` | Language of instruction. |
| `attempt.grade` | grade | comparisons, `is null` | Order: F, D-, D, D+, C-, C, C+, B-, B, B+, A-, A. |
| `attempt.grading_mode` | enum | `=` `!=` `in` | `letter`, `crdf`, `pass_fail`. |
| `attempt.graduate_grade` | enum, nullable | `=` `!=` `in` `is null` | Graduate School grades `F`, `P`, `HP`, `H`. |
| `attempt.source` | enum | `=` `!=` `in` | `yale`, `study_abroad`, `summer`, `transfer`, `acceleration`. |
| `attempt.term` | term | `=` `<` `<=` `>` `>=` | Used by `order` constraints. |
| `attempt.year_of_study` | integer | `=` `<` `<=` `>` `>=` | 1–4; "taken in the senior year" is `= 4`. |
| `attempt.enrolled_subject` | enum `subject` | `=` `!=` `in` | The code the student enrolled under ("enrolled under the HIST number"). |
| `attempt.approved_for` | set | `contains` `overlaps` | Requirement-level approvals recorded on the attempt (§12.3). |
| `student.class_year` | integer | comparisons | |

### 11.2 Fact types

| Fact type | Approval | Parameters | Used for |
| --- | --- | --- | --- |
| `placement` | no | `test`, `result` | Placement exams and AP/IB scores |
| `language_proficiency` | no | `language`, `level` | Proficiency shown without coursework |
| `prior_coursework` | no | `description` | Prior preparation, certificates, year abroad |
| `program_admission` | no | `program` | Program membership facts |
| `dus_approval` | yes | `for` | DUS sign-offs (orientations, prospectuses, intensive majors) |
| `adviser_approval` | yes | `for` | Adviser sign-offs |
| `committee_approval` | yes | `for` | Committee decisions and simultaneous-degree admission |

### 11.3 Aliases and attribute values

`department_aliases` maps renamed codes to current ones: `AFAM` → `BLST`, `EENG` → `ECE`, `HELN` → `MGRK`. `tag_values` lists the 533 Yale course attributes from upstream `yale_attributes.txt`, HTML-unescaped (`YC ARCH Urbanism & Landscape`). Attribute strings must match that list exactly, including Yale's truncations (`YC ARCHStructures&Computation`).

## 12. Repository conventions

### 12.1 Files and headers

Each program lives in `majors/2627/<major>/<file>.mql`. The program ID MUST equal the file stem; `validate.py` checks this. Each file starts with a one-line summary comment and a `// Source:` line giving the catalog page, then the header:

```mql
program <file_stem> {
  catalog 2026-2027
  institution "https://majoraudit.org/mql/yale" @ "2026-2027"
  credit_scale 2
}
```

Every program uses `credit_scale 2`, so half-credit courses are exact.

### 12.2 Roles

Roles in use: `prerequisite`, `introductory`, `core`, `elective`, `concentration`, `senior`, `language`, `graduate`, `distribution`, `breadth`, `group`, `seminar`, `letter_required`, plus department roles in joint majors (`computing`, `mathematics`, `physics`, `philosophy`, `psychology`, `economics`, `arts`, `geosciences`, `science`, `italian`, `literature`, `creative_writing`, `content`, `intersection`, `orientation`, `admission`, `field`, `senior_extra`). Totals that exclude prerequisites are written `in roles [core, elective, senior]` and so on; totals that include them use `in program`.

### 12.3 Approvals on attempts

Catalog phrases such as "approved by the DUS", "in the area of focus", or "or an equivalent" cannot be decided from catalog data. They are written as `attempt.approved_for contains "<id>"`, where `<id>` is normally the author ID of the requirement the approval applies to (`"electives"`, `"focus"`, `"senior"`). Two shared tokens are used throughout: `"major"` approves an outside or study-abroad course for major credit, and `"crdf"` records DUS permission to count a Credit/D/Fail course. These approvals are course-level witnesses, which the audit ranks below course-matching witnesses (§10, rule 8).

### 12.4 Non-course requirements

Orientations, portfolios, field schools, admissions, journals, and similar requirements are encoded as a required requirement, an approval or placement fact, and a `waive` effect:

```mql
fact field_school "Summer field school approved in advance by the DUS":
  approval dus_approval { for: "field_research" };

requirement field_research "Summer field research" [field] {
  slot where attempt.approved_for contains "field_research";
}

effect field_school_done when fact field_school: waive field_research;
```

The requirement shows up in progress; the fact satisfies it and stays visible as the witness. Placement waivers use the same shape with a `placement` fact. When a waiver requires replacement courses ("every two BIOL modules placed out are replaced by one MCDB course"), the replacement is a requirement with `when fact …`.

### 12.5 Recurring patterns

| Catalog rule | Encoding |
| --- | --- |
| "No course taken Credit/D/Fail may count" | `constraint letter_grades … in program: all where attempt.grading_mode = "letter";` |
| "At most n Credit/D/Fail courses" | `limit n attempts where attempt.grading_mode = "crdf";` |
| "Outside credit with DUS approval" | `all where attempt.source = "yale" or attempt.approved_for contains "major";` |
| "n courses in all" | `total at least n attempts` (or `credits`) in a named scope |
| "A or B" | `slot from [A, B];` |
| "A and B, or C" | parent `children at least 1` with children `courses exactly 2 from [A, B]` and `slot from [C]` |
| "n courses numbered 3000+ in X" | `courses at least n where course.subject = "X" and course.number >= 3000;` |
| "n electives, at least m of them …" | pool plus nested `at least m attempts where …` |
| "one each in k of m areas" | parent `children at least k` with one child per area |
| "two courses in one area" | parent `children at least 1` with one `courses at least 2` child per area, or `group field same` when the area is a field |
| "different departments" | `group course.subject distinct at least n` |
| "no more than two per department" | `group course.subject at most 2 per group` inside the pool |
| "only one of X or Y counts" | `limit 1 attempts where course.code in [X, Y]` |
| "counts at most twice" | `repeat at most 2 times where course.code = …` |
| "X before Y" | `order course.code = "X" before course.code = "Y"` |
| "n electives (n+1 if …)" | choice plus a choice-table bound |
| tracks and concentrations in one file | `declared` choice plus `when` on the branch requirements |
| concentration rules over courses already counted | program- or role-scope `SELECTED_SET` constraints (Anthropology, Art) |
| concentration courses that may also count for the major | concentration requirements plus pairwise `share` rules (MB&B) |
| "one course may satisfy region, preindustrial, and seminar" | one `share` rule per region with the other requirements (History) |
| simultaneous B.S./M.S. | admission fact and waive, graduate requirement with grade constraints, advisory High Pass average |

## 13. Diagnostics and validation

Compilation reports every diagnostic, each as `path:line:column: CODE [id]: message`. `pylibmql.compile_program` raises `ValueError` listing them.

| Code | Meaning |
| --- | --- |
| `MQL0300_SYNTAX` | Source does not match the grammar |
| `MQL0301_COUNT_STATEMENT` | A requirement has zero or several count statements |
| `MQL0302_MISSING_BOUND` | A non-`slot` count has no bounds |
| `MQL0303_AMOUNT` | A credit amount is not a whole unit, or a count is fractional |
| `MQL0304_MISSING_SELECTOR` | A count has neither a selector nor nested requirements |
| `MQL0305_UNKNOWN_FIELD` | A field is undeclared, or no institution schema was supplied |
| `MQL0306_OPERATOR_NOT_ALLOWED` | The schema does not allow the operator on the field |
| `MQL0307_INSTITUTION_MISMATCH` | The supplied schema is not the one the header names |
| `MQL0308_UNKNOWN_FACT_TYPE` | Fact type, approval flag, or parameter not declared |
| `MQL0309_MISSING_SCOPE` | A top-level constraint has no `in` scope |
| `MQL0310_HEADER` | A header entry is missing or repeated |
| `MQL0311_UNKNOWN_VALUE` | An enum or grade literal is not declared |

The compiler then runs the IR validator, whose `MQL02xx` codes include `MQL0201_UNRESOLVED_ID`, `MQL0203_CONFLICTING_EFFECTS`, `MQL0204_ADVISORY_SCOPE`, `MQL0207_DUPLICATE_ID`, `MQL0212_SHARING_CARDINALITY`, `MQL0215_INVALID_BOUNDS`, `MQL0218_INCOMPLETE_CHOICE_TABLE`, `MQL0219_UNKNOWN_CHOICE_VALUE`, `MQL0221_INVALID_SCOPE`, `MQL0222_INVALID_EFFECT`, `MQL0224_INCOMPATIBLE_UNIT`, and `MQL0225_INVALID_OPERATOR`.

`validate.py` adds the checks the compiler cannot make: the program ID matches the file stem; every literal compared against `course.attributes` is in `tag_values`; every distributional literal is declared; and every course-list ID and `course.code` literal has a known subject (or alias), accepting Summer Session IDs such as `PSYCS1390`. It also checks the catalog manifest against each major's `specializations`, as before.

## 14. Known limits

- **No engine yet.** pylibmql 0.3.0 compiles and validates; it does not audit or plan. Every encoding here follows RFC 0001 semantics, but none has been executed against a transcript.
- **Credit literals in predicates.** Whether `course.credits >= 1` is compared in units or credits is not specified, so no program uses credit literals in predicates.
- **Set-valued literals are not compiler-checked.** Attribute and distributional strings are checked by `validate.py`, not by the compiler.
- **Groups have no predicate.** A rule like "no more than two introductory courses per department" cannot be one group constraint; Sociology writes one `limit` per relevant subject instead.
- **"k of m categories" over a selected set.** Category coverage among already-counted courses needs one requirement per category plus `share` rules (History of Art); a group constraint cannot express it when categories are a set-valued attribute.
- **No modules.** RFC 0001 §17 leaves imports to a later RFC, so the 21 MB&B and 16 MCDB programs repeat their common requirements. They are generated from one template each.
- **Non-record judgments** (a High Pass average, "no more than four core courses in one tradition") are advisory requirements.

## 15. Interfaces

### 15.1 Command line

```console
mql --compile program.mql --institution majors/2627/yale-institution.json   # compile 0.2 source to IR JSON
mql --validate-ir program.json                                              # validate and canonicalize IR
mql program.mql                                                             # legacy 0.1 parser
```

### 15.2 Python

```py
import pylibmql
inst = open("majors/2627/yale-institution.json").read()
ir = pylibmql.compile_program(open(path).read(), path, inst)   # raises ValueError with diagnostics
ir.version()      # "0.2.0"
ir.json()         # compact IR JSON
pylibmql.validate_semantic_ir(ir.json())
pylibmql.__version__  # "0.3.0"
```

### 15.3 Rust

```rust
use libmql::compiler::compile;
use libmql::institution::Institution;
use libmql::semantic_ir::SemanticProgram;
```

### 15.4 Repository validation

```console
python validate.py        # upgrades pylibmql, then compiles every program listed by every major
python validate.py -v     # also prints each compiled IR
```

`validate.py` requires pylibmql 0.3.0 or later and exits non-zero on any error.

## Appendix A. Quick reference

```mql
program id { catalog 2026-2027  institution "<schema-id>" @ "<version>"  credit_scale 2 }

choice c "…": declared | solver | planning one of "a", "b";
fact f "…": [approval] <fact_type> { param: "value" };

[required | optional | advisory] requirement r "…" [role, …] when <condition> {
  slot | courses | canonical courses | credits | assignments | children
    [exactly n | at least n | at most n | between a and b | (c: "a" => n, "b" => m)]
    [from [CODE 1234, …] | from requirements [x, y] | where <predicate>] [each n credits];
  requirement child "…" { … }
  constraint k "…": <body>;
}

constraint k "…" [when <condition>] in direct r | subtree r | requirements [..] | roles [..] | branch c = "v" | program:
  at least n attempts where p | all where p | group course.subject distinct at least n
  | limit n credits where p | total at least n attempts | repeat at most n times where p | order p before q;

share s "…": a, b;      exclusive s "…": a, b;
effect e "…" when fact f: waive r | activate r | deactivate r | set lower of r to n
                        | substitute r with r2 | make r optional | permit r where p;
```

## Appendix B. Migrating from MQL 0.1.12

| 0.1.12 construct | 0.2 form |
| --- | --- |
| `SELECT 1 FROM [A, B] : "d"` | `requirement r "d" { slot from [A, B]; }` |
| `SELECT 4 FROM [$x, $x, $x, $x]` (repeated pool) | `courses at least 4 where …` |
| `SELECT 2-4 FROM …` (credit approximation) | `credits at least n where …` |
| nested `SELECT k FROM [SELECT …, …]` | `children at least k` with nested requirements |
| `CLASS(MATH 2250)`, `MATH 2250` | `from [MATH 2250]` or `course.code = "MATH2250"` |
| `RANGE(ECON 2000, ECON 9999)` | `course.subject = "ECON" and course.number >= 2000` |
| `TAG("YC …")` | `course.attributes contains "YC …"` |
| `DIST("L5")`, `DIST_DEPT("HU", "AFST")` | `course.distributionals contains "L5"`; `… and course.subject = "AFST"` |
| `RANGE_TAG(A, B, "t")` | number range `and course.attributes contains "t"` |
| `PLACEMENT("approved by the DUS")` | `attempt.approved_for contains "<req>"` |
| `PLACEMENT("AP score …")` | `fact … : placement {…};` with `effect … waive` |
| `PLACEMENT("orientation completed")` | approval fact, requirement, and waive effect (§12.4) |
| `LIMIT n FROM …` | `constraint … in <scope>: limit n attempts where …;` |
| a comment saying courses may be shared | `share` rules |
| duplicated branches for tracks | `choice` and `when`, or a choice-table bound |
| `$var = …`, `extern $X` | removed; repeated expressions are written out or generated |
| priority (`: 2`) | removed; the audit objective is fixed by RFC 0001 |

## Appendix C. Source basis

- `docs/rfcs/0001-semantic-ir.md` and `docs/rfcs/0002-surface-grammar.md` — normative semantics and syntax;
- `libmql/src/mql2.pest` — concrete grammar;
- `libmql/src/compiler.rs` and `libmql/src/institution.rs` — lowering, typing, and diagnostics;
- `docs/schemas/*.schema.json` — IR and institution schemas;
- `docs/fixtures/semantic-ir/source/*.mql` — reference programs;
- `pylibmql.pyi` and `cli/src/cli.rs` — Python and CLI contracts;
- this repository's `majors/2627/yale-institution.json`, `validate.py`, and 189 programs, all of which compile with pylibmql 0.3.0 and validate against `mql-ir-0.2.schema.json`.
