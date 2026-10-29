# MQL Implementation Requirements for Complete Yale Major Modeling

**Audience:** MQL parser, language, SDK, and solver-integration teams  
**Catalog target:** Yale College Programs of Study, 2026–2027  
**Current implementation baseline:** `libmql` / `pylibmql` 0.1.12  
**Purpose:** Define the language work required before `./majors` is rewritten in an expanded MQL syntax.

## Goal and completion standard

MQL must be able to represent every auditable rule in all 82 Yale College majors and all 189 program variants with the same meaning as the Yale catalog. The language must support both degree auditing and course planning without relying on consumer-specific guesses.

“100% fidelity” means:

1. Every catalog rule that affects whether a student has completed a major is represented structurally in MQL.
2. A conforming consumer can determine the same result from the serialized MQL program, course catalog, transcript, and student-profile facts without reading comments or Yale prose.
3. `PLACEMENT` or an adviser-approval fact is used only when the catalog genuinely delegates a decision to a person, placement result, petition, or external credential. It must not substitute for a missing language feature.
4. The same program representation supports audits, explanations, and planning.
5. Parser output has normative semantics. Selector lists, nesting, quantities, `LIMIT`, sharing, and upper bounds must no longer be “interpreted by the consumer.”

The MQL team may choose syntax different from the sketches in this document. The semantics and acceptance criteria are mandatory.

This document is the governing requirements specification, not permission to begin surface-grammar work. The first approved implementation deliverable is the semantic IR RFC defined below. Grammar and complete solver implementation begin only after that RFC freezes every normative decision in this document.

## Why the current language is insufficient

MQL 0.1.12 can represent fixed course choices, basic ranges and tags, nested alternatives, and opaque placement conditions. It cannot faithfully represent many catalog rules, including:

- several courses from one open pool without repeating a selector;
- credit totals involving half-, one-and-a-half-, or two-credit courses;
- scoped caps and exclusions;
- distinct-department, same-language, or same-concentration grouping;
- subconditions on the courses selected for another requirement;
- selective sharing between requirements;
- program-wide totals when courses overlap;
- conditional counts and mutually exclusive tracks;
- grade, grading-mode, term, source, and study-abroad restrictions;
- repeatability and course-order rules;
- typed waivers, substitutions, and placement facts.

The present AST also lacks stable requirement identities, roles, activation conditions, and explicit scopes. Variables expand as parse-time macros rather than remaining named semantic sets. Nested queries have no identity or metadata. These omissions prevent precise sharing, totals, diagnostics, and planner explanations.

## Required semantic foundation

The implementation must define a solver-ready semantic IR before freezing new grammar. The IR should not be CP-SAT-specific, but every construct must have an unambiguous constraint interpretation.

### 1. Stable identity and hierarchy

Every requirement and constraint must have:

- a stable author-supplied ID;
- a generated node ID unique within the program;
- parent and child relationships;
- a human-readable description;
- source span information;
- zero or more roles such as `prerequisite`, `core`, `elective`, `concentration`, and `senior`;
- an activation condition inherited from any enclosing choice or conditional branch.

Descriptions must not serve as identifiers. Nested requirements must be able to carry IDs and metadata.

Illustrative syntax:

```mql
REQ cs_core ROLE core =
  SELECT 5 COURSES FROM [CPSC 2010, CPSC 2020, CPSC 2230, CPSC 3230, CPSC 3650]
  : "Computer Science core";
```

### 2. Explicit quantity units and contribution rules

MQL must distinguish three concepts:

- **Slot:** one selector occurrence can be filled at most once.
- **Course pool:** a selector denotes a set from which multiple distinct courses may be selected.
- **Credit pool:** selected courses contribute their catalog credit values.

Illustrative syntax:

```mql
SELECT 1 FROM [CPSC 3650, CPSC 3660] : "Algorithms";
SELECT 4 COURSES FROM RANGE(ECON 2000, ECON 9999) : "Economics electives";
SELECT 4 CREDITS FROM $advanced_chemistry : "Advanced chemistry";
```

The semantic IR must include a contribution expression `q[node]`:

- ordinary slot: `q` is 0 or 1;
- course-counted pool: `q` is the number of selected distinct course attempts;
- credit-counted pool: `q` is the sum of normalized credit units;
- nested requirement used as an alternative: `q` is its satisfaction Boolean unless explicitly flattened.

Credit arithmetic must use normalized integers with a declared scale or denominator stored in the serialized program or institution data schema. Consumers must not choose their own scale. It must not hard-code half credits; the data model must also support values such as 1.5 and 2 credits.

Credit contribution has one authoritative source by operation:

- auditing uses earned credit recorded on the transcript attempt;
- planning uses catalog credit for the proposed course offering;
- a requirement may explicitly declare a fixed credit treatment that overrides the ordinary source;
- failed, withdrawn, or otherwise non-credit-bearing attempts contribute zero and are ineligible unless a rule explicitly states otherwise.

### 3. Normative satisfaction and upper-bound behavior

For every active bounded node, selected assignments are constrained first and satisfaction is defined second:

```text
0 <= q[node] <= upper[node]
satisfied[node] iff active[node] AND q[node] >= lower[node]
```

For a node without a finite upper bound, the first constraint is omitted. For an inactive node:

```text
q[node] = 0
satisfied[node] = false
```

Upper bounds therefore cap assignments selected for that requirement and are not separately reified in the satisfaction test. Extra transcript courses that happen to match a selector neither count nor invalidate the requirement.

Courses and descendant nodes in inactive branches must not contribute to progress, totals, usage, or satisfaction:

```text
assignment(course, leaf) <= active(leaf)
satisfied(node) <= active(node)
```

### 4. Course and transcript identity

The language and serialized model must distinguish:

- a canonical catalog course;
- a transcript course attempt;
- cross-listed or renamed course codes;
- repeated attempts that may or may not both count.

Default behavior must be that one transcript attempt cannot fill two slots within the same requirement. Reuse across requirements is governed by explicit sharing rules.

Assignment and sharing operate on transcript attempts. Canonical-course restrictions are separate constraints used for rules such as “only one of,” repeat limits, and duplicate-credit policy. Credits are properties contributed by attempts; credits are not independently shared.

## Required language capabilities

### A. Boolean course predicates and set operations

Selectors must support composition with `AND`, `OR`, and `NOT`, plus set difference or exclusions. Predicates must cover catalog fields rather than requiring a new selector function for every combination.

Required predicate fields include:

- canonical course and all cross-listed codes;
- department and course number/level;
- Yale Course Search attributes;
- distributional designations;
- credits;
- course format such as lecture, seminar, lab, research, or independent study;
- language of instruction;
- catalog term and offering information.

The IR RFC must define a predicate type system, not an untyped expression string. Every field declaration must specify:

- its target record: catalog course, transcript attempt, student profile, or offering;
- its scalar, enum, set, course-code, credit, grade, or term type;
- whether it is nullable and how `null` behaves;
- valid comparison and membership operators;
- canonical string normalization and case behavior;
- enum and institution-schema validation;
- whether cross-listed codes match by enrolled-under code, canonical identity, or either;
- permitted joins between catalog and transcript fields.

Missing data does not match an ordinary predicate. It may be tested only through explicit `IS UNKNOWN`/`IS NULL` semantics. String comparison is exact after schema-defined normalization. Grades use an institution-supplied ordered grade type; expressions such as `grade >= "B"` must never use lexical string ordering.

Illustrative syntax:

```mql
COURSES WHERE level >= 2000 AND dist = "SC" AND format != "research"
RANGE(MATH 2250, MATH 5999) EXCEPT [MATH 4700]
TAG("YC CPSC Elective") AND NOT CLASS(CPSC 4900)
```

This must cover catalog patterns P12 and P13: exclusions and compound attributes.

### B. Constraints on the selected set

A requirement must be able to constrain the same courses it selects. A second, duplicated requirement is not equivalent because it can use different courses.

Illustrative syntax:

```mql
SELECT 4 COURSES FROM $ee_electives
  HAVING AT LEAST 3 WHERE level >= 4000
  : "Four engineering electives, at least three at the 4000 level";
```

Required selected-set constraints include:

- at least, at most, and exactly `n` matching a predicate;
- credit subtotal conditions;
- membership in a named subgroup;
- all selected courses satisfying a predicate.

Every selected-set constraint has an explicit scope in the IR. The default surface form observes the distinct transcript attempts directly assigned to that requirement and contributing to its quantity. It does not automatically observe assignments made only by descendants, ancestors, shareable sibling requirements, or inactive branches. Syntax must permit an explicit subtree or named scope when descendant assignments are intended. Sharing the same attempt into another requirement does not duplicate it within one selected-set scope.

This must cover P9.

### C. Grouping rules

MQL must express constraints over attribute values of selected courses:

```mql
DISTINCT department >= 3
SAME language
SAME concentration
MAX 2 COURSES PER department
```

The IR must support group cardinality, exactly-one chosen group, and per-group caps. This must cover:

- courses from different departments or breadth areas (P6);
- several courses in the same language, region, or concentration (P7);
- per-department and similar caps (P5).

### D. Explicit scopes and scoped limits

Every cap, total, sharing rule, and selected-set constraint must name or inherit a precise scope. Required scopes are:

- one requirement's selected assignments;
- one requirement subtree;
- a named set of requirements;
- all requirements with specified roles;
- the active branch of a choice;
- the whole program.

Illustrative syntax:

```mql
LIMIT 2 COURSES FROM $outside IN REQ electives;
LIMIT 1 COURSE WHERE grading_mode = "CR/D/F" IN PROGRAM;
```

An unscoped `LIMIT` must either have a single documented local meaning or be rejected. It must never silently change between consumers.

This must close P5.

### E. Requirement sharing and exclusivity

Default behavior must be exclusive use across named requirements. MQL must allow explicit exceptions:

```mql
EXCLUSIVE ALL;
SHARE regions, preindustrial, seminars;
```

Sharing must be represented as an allowed or forbidden relation between requirement scopes, not as one global reuse count per course. The model must answer:

- whether one course may count in two or three named requirements;
- whether descendants inherit the enclosing requirement identity;
- whether sharing applies to course attempts, canonical courses, or credits;
- whether roles can define sharing policy.

The normative answers are:

- sharing applies to transcript attempts;
- `SHARE a, b, c` permits the same attempt in all three scopes by allowing every pair in the declared set;
- descendants inherit the nearest enclosing named requirement identity unless a nested requirement declares its own ID;
- sharing never permits one attempt to fill multiple slots inside the same requirement;
- canonical-course and repeat restrictions are evaluated separately and may still forbid an otherwise shareable assignment;
- each assignment contributes the attempt's credit value to the requirement receiving it, while a scoped distinct-credit total counts that attempt once in that total's scope.

The safe default is:

- no attempt fills two slots in one requirement;
- no attempt is shared across requirements unless a rule explicitly permits it.

This must close P8 and support P17.

### F. Roles and scoped program totals

Requirements must have roles, and totals must operate over distinct course usage within a named scope:

```mql
TOTAL 12 COURSES FROM ALL : "Twelve courses in the major";
TOTAL 7 COURSES FROM ROLE econ;
TOTAL 5 COURSES FROM ROLE math;
TOTAL 11 COURSES WHERE subject = "literature" FROM PROGRAM;
```

The IR needs scoped usage variables conceptually equivalent to:

```text
used(course, scope) = OR of assignments of that course within scope
```

Each total must explicitly count one of:

- distinct transcript attempts;
- distinct canonical courses;
- credits;
- assignments.

This must close P11 and P17, including totals where another rule permits overlap.

### G. Choices, tracks, and conditional rules

MQL must support typed, exactly-one choices and conditional activation:

```mql
CHOOSE systems IN {split, combined};

IF systems = split THEN
  REQ systems_core = SELECT 2 FROM [CPSC 3231, CPSC 3232];
ELSE
  REQ systems_core = SELECT 1 FROM CPSC 3230;

REQ electives = SELECT
  (IF systems = split THEN 5 ELSE 6)
  COURSES FROM TAG("YC CPSC Elective");
```

Choices must support:

- mutually exclusive concentrations and tracks;
- one- versus two-term senior options that change other counts;
- course substitutions that change elective totals;
- program variants sharing a common base.

Every choice has an ownership kind in the IR:

- `DECLARED`: fixed from the student's profile, such as a concentration or degree track;
- `SOLVER`: selected by the audit from equivalent catalog alternatives, such as either valid course sequence;
- `FACT`: determined by a typed fact, such as an AP result;
- `PLANNING`: selected only while constructing a future plan.

An audit must never choose or change a `DECLARED` track to make completion easier. Missing required declared-choice data is an explicit indeterminate/error state, not permission for solver selection. A `PLANNING` choice does not alter the student's current audit.

Inactive branches must be fully gated. This must close P10 and P18.

### H. Transcript predicates

Eligibility and caps must be able to use transcript fields:

```mql
WHERE grade >= "B"
WHERE grading_mode = "letter"
WHERE academic_level = "senior"
WHERE source IN {"Yale", "study_abroad", "transfer", "summer"}
```

Required transcript data includes:

- term and academic level;
- grade and grading mode;
- source institution/category;
- enrolled-under course code;
- earned credits;
- repeat/attempt identity.

The language must support caps such as at most one Credit/D/Fail course or at most four study-abroad credits. This must close P14.

### I. Repeats and ordering

MQL must express when repeated attempts count and when courses must occur in order:

```mql
REPEATABLE 2 [PHYS 4710, PHYS 4720] IN REQ senior;
LIMIT 1 ATTEMPT FROM RANGE(CGSC 4710, CGSC 4740) IN PROGRAM;
BEFORE(PHYS 4010, PHYS 4020);
```

Planning semantics must interpret `BEFORE` through term variables. Audit semantics must inspect transcript terms. This must close P15 and the ordering portion of P14.

### J. Typed facts, waivers, substitutions, and human approval

Opaque placement strings are insufficient for auditable substitutions. MQL must reference typed facts supplied by an institution-defined schema:

```mql
FACT("ap_psychology_5")
FACT("language_proficiency", language = "Russian", level >= 4)
APPROVAL("dus_substitution", for = electives)
```

Facts must be usable in choices and substitution rules. The language must support consequences such as:

- waive a prerequisite;
- replace two waived biology modules with one additional core course;
- require extra electives when language proficiency is demonstrated without coursework;
- allow a specifically approved substitute.

The first IR version must use a closed set of typed conditional effects rather than arbitrary scripts:

- activate or deactivate a requirement/branch;
- replace a lower or upper bound with a typed value;
- waive a requirement while preserving the waiver as the satisfaction witness;
- substitute one requirement node for another;
- add a named obligation;
- permit a particular assignment or selector as a substitution.

Effects execute declaratively from typed conditions, must be order-independent, and must reject conflicting simultaneous effects unless the IR defines an explicit precedence rule. Every applied effect remains visible in the audit explanation.

Human approvals should remain explicit actions or facts, be visible in audit explanations, and be unavailable to automatic course planning. This must close P16 and preserve the legitimate use case in P20.

### K. Composition and reuse

The 189 programs contain families with large shared bases, including MB&B and MCDB degrees by concentration and Sociology standard/intensive tracks. After stable identity and override semantics exist, MQL should support modules or imports to avoid divergent copies.

Composition must define:

- namespace and ID behavior;
- parameter types;
- whether requirements may be extended, replaced, or disabled;
- how sharing, roles, scopes, and source spans survive composition;
- cycle detection and deterministic expansion.

Composition is strongly recommended but is not a substitute for any semantic capability above.

## Catalog patterns the implementation must pass

The implementation is not complete until it can represent all twenty observed requirement patterns without semantic workarounds:

| ID | Catalog pattern | Required capability |
| --- | --- | --- |
| P1 | Choose `n` from a fixed list | Existing slots/cardinality |
| P2 | `n` courses from an open pool | Course-counted pools |
| P3 | Alternative sequences | Nested Boolean contribution |
| P4 | Credit totals | Credit-counted pools/totals |
| P5 | Scoped and per-group caps | Scopes, `LIMIT`, grouping |
| P6 | Courses from distinct groups | `DISTINCT` grouping |
| P7 | Courses from one common group | `SAME`/chosen-group semantics |
| P8 | Selective sharing | Named requirements and sharing relation |
| P9 | Subconditions on selected courses | `HAVING`/selected-set constraints |
| P10 | Conditional counts | Choices and conditions |
| P11 | Program totals with overlap | Scoped distinct usage and totals |
| P12 | Exclusions | Boolean predicates/set difference |
| P13 | Compound catalog attributes | Predicate expressions |
| P14 | Grade, mode, source, and term rules | Transcript predicates and ordering |
| P15 | Repeat rules | Attempt identity and repeat constraints |
| P16 | Waivers and substitutions | Typed facts and conditional consequences |
| P17 | Prerequisite/core/senior roles | Requirement roles |
| P18 | Track choice | Typed choices and branch activation |
| P19 | Paired/fractional groups counting as one | Explicit nested contribution |
| P20 | Human approval | Adviser facts/actions |

Repeated selectors, duplicated whole-program branches, comments, and prose-only `PLACEMENT` strings do not count as support for P2–P18.

## Solver semantics the serialized model must permit

A conforming compiler should be able to construct the following conceptual model. Exact variable names and solver technology are implementation choices.

### Core variables

- `x[attempt, leaf]`: a transcript attempt is assigned to a selector leaf.
- `active[node]`: a requirement or branch participates in the selected program.
- `q[node]`: the node's contribution in its declared unit.
- `satisfied[node]`: the node meets its bounds while active.
- `used[attempt, scope]`: the attempt is used by at least one assignment in a scope.
- planning-only course-selection and term variables.

### Required invariants

1. Assignments exist only for eligible attempts and active leaves.
2. One attempt fills at most one slot in a requirement unless an explicit repeat/assignment rule says otherwise.
3. Node contribution is determined by its semantic node kind, not guessed from selector syntax.
4. Satisfaction is equivalent to meeting the active node's bounds.
5. Selected assignments, not all matching transcript courses, are capped by upper bounds.
6. Forbidden sharing pairs cannot use the same attempt.
7. Totals use scoped distinct usage or scoped credits as declared.
8. Inactive branches contribute nothing.
9. Every constraint retains an ID and source span for explanations.

## Audit and planning behavior

MQL must expose enough semantics for a consumer to perform both operations consistently.

### Audit

Completion is a feasibility property, not an optimization result:

```text
program_complete iff every active required root is satisfied
```

If a feasible complete assignment exists, the program is complete. If none exists, optimization may select the best explanatory partial assignment, but it must not report that assignment as completion.

For each active required root with positive lower bound, normative normalized progress is the exact rational value:

```text
progress[node] = min(q[node], lower[node]) / lower[node]
```

Inactive and optional unchosen roots do not contribute. Progress is computed only at required roots for the default objective, avoiding double-counting nested alternatives. A shareable attempt may legitimately improve multiple required roots because those are separate catalog obligations. Implementations must compare these rationals exactly, for example by using the least common multiple of active root lower bounds; floating-point rounding must not affect assignment choice.

For an incomplete audit, the default explanatory assignment optimizes lexicographically:

1. required top-level satisfaction;
2. the exact sum of normalized progress on unsatisfied active required roots;
3. preference for actual courses over manual approvals when both are valid.

Further tie-breaking may be deterministic but must not change completion or reported per-requirement progress. The selected assignment is an explanation witness, not the definition of degree completion.

`priority` should remain display-only unless the language specification defines a precise and tested optimization meaning. It must not silently change audit correctness.

### Candidate-course usefulness

A course is useful for requirement `R` when there exists a reassignment using that course that:

- preserves the baseline optimal audit objective; and
- improves satisfaction or progress for `R`.

The implementation must fix optimal objective values, not one arbitrary baseline assignment. Equal-quality rearrangements must be considered.

### Completion planning

Planning must support:

- minimizing additional courses, then credits and/or terms;
- prerequisite and `BEFORE` edges;
- term offerings and per-term credit caps;
- alternative equal-cost plans;
- explanation of blocked candidates by named constraint;
- non-course actions for approvals and external facts.

Multi-term planning is a second subsystem and is not required for the first auditing milestone. Before full planning is implemented, its RFC must additionally freeze:

- prerequisite expression semantics, including concurrent enrollment;
- behavior for unknown, cancelled, and irregular offerings;
- cross-listed course equivalence in scheduling;
- course-count and credit-count term caps;
- treatment of already planned approvals and facts;
- whether non-major prerequisites participate in each planning objective;
- ranking and bounded enumeration of equal-cost plans.

The initial semantic IR and schemas must preserve offering, prerequisite, term, and planning-choice fields so this subsystem can be added without changing existing audit meaning.

## Required data contracts

The MQL SDK must publish or accept schemas for the data referenced by predicates:

### Catalog course

- canonical ID and all cross-listed/renamed codes;
- subject, number, suffix, level, and format;
- exact credit value;
- distributions and Yale attributes;
- language of instruction;
- terms offered and prerequisites.

### Transcript attempt

- canonical course and enrolled-under code;
- term and academic level;
- grade and grading mode;
- earned credits;
- Yale, transfer, summer, or study-abroad source;
- attempt/repeat identity.

### Student profile

- declared program and track;
- class year;
- AP/IB and placement results;
- language proficiency;
- named adviser or committee approvals.

Institution-specific tags, department aliases, and fact names must be validated against a supplied schema. They should not be hard-coded forever into the parser binary.

## Parser, AST, and serialization requirements

The MQL team must deliver:

1. A normative language specification with every construct's counting, activation, scope, sharing, and error semantics.
2. A versioned AST/semantic IR containing stable IDs, roles, units, scopes, predicates, conditions, and source spans.
3. Versioned JSON serialization sufficient for a consumer to enforce every rule without MQL source text.
4. Rust, Python, and CLI interfaces exposing the same semantics.
5. Deterministic expansion of variables/modules and stable diagnostics.
6. A migration guide from MQL 0.1.12.
7. A released `pylibmql` version suitable for the repository validator.

Breaking serialization changes require a schema-version increment. The parser should either retain documented compatibility for 0.1.12 files or provide an automated migration tool; it must not silently reinterpret an old file under new semantics.

## Diagnostics and explanations

The parser must reject or diagnose:

- duplicate or unresolved requirement IDs;
- invalid scope references;
- cyclic choices or module imports;
- incompatible units in one quantity expression;
- totals or sharing rules referencing inactive/nonexistent requirements;
- predicates for fields absent from the declared data schema;
- unscoped limits if no normative default exists;
- attempts to plan an adviser approval as a course;
- ambiguous old selector-list semantics.

Serialized constraints must retain names and source spans so an audit can explain both success and failure, for example:

> CPSC 4900 matches the department range but cannot count as an elective because requirement `cs_electives` excludes courses with role `senior`.

## Conformance and acceptance tests

Before the majors repository is rewritten, the MQL implementation must pass a public conformance suite.

### Minimum semantic fixtures

The suite must include at least one positive and one negative case for every P1–P20 pattern, including:

- four distinct courses selected from one range;
- four credits satisfied by a mixture of half- and full-credit courses;
- extra matching transcript courses not violating an upper bound;
- three courses from distinct departments;
- several courses forced into one selected language or region;
- a selected-set 4000-level subtotal;
- History-style three-way sharing with other pairs remaining exclusive;
- a program total that does not double-count shared courses;
- a conditional elective count after a substitution;
- an inactive branch unable to contribute to totals or progress;
- letter-grade, Credit/D/Fail, senior-year, and study-abroad restrictions;
- repeated and ordered courses;
- a waiver that changes another requirement's count;
- a legitimate adviser approval surfaced as a non-course action;
- a useful-course test that requires reassignment between equal optimal audits.

### Reference catalog fixtures

The suite should include end-to-end reduced fixtures modeled on these high-value Yale cases:

- Computer Science systems substitution and changing elective count;
- History regions, preindustrial courses, seminars, sharing, and twelve-credit total;
- Electrical Engineering four electives with three at the 4000 level;
- Applied Mathematics breadth and same-area concentration rules;
- Chemistry mixed credit values;
- Psychology B.A./B.S., neuroscience track, grade/mode rules, and AP waiver;
- MB&B base degree plus concentration sharing;
- Sociology concentration plus standard/intensive choice.

Each fixture must assert parser output and audit/planner outcomes, not merely successful parsing.

## Implementation sequence

The recommended order is:

1. **Semantic IR:** identities, hierarchy, activation, roles, source spans.
2. **Quantity algebra:** slots, courses, credits, contributions, bounds.
3. **Assignment policy:** canonical/attempt identity, exclusivity, sharing, repeats.
4. **Scopes and totals:** local/subtree/role/program usage.
5. **Predicates and groups:** Boolean filters, exclusions, selected-set and group rules.
6. **Choices and facts:** conditional branches, transcript predicates, waivers, approvals.
7. **Objectives and explanations:** audit progress, planning, useful-course counterfactuals.
8. **Composition:** modules/imports after identity and override rules are stable.
9. **Grammar and SDK release:** finalize syntax over the proven IR.
10. **Conformance release:** publish fixtures, migration guide, and versioned packages.

Do not implement the proposed surface syntax directly on the current ambiguous AST. Doing so would preserve consumer-defined semantics and make apparently valid files disagree across audit engines.

### Required first deliverable: semantic IR RFC

Before parser or solver implementation, submit one RFC containing:

1. algebraic data types for every semantic IR node, predicate, scope, choice, fact, and effect;
2. a versioned JSON Schema with the normalized credit scale and institution-schema references;
3. formal invariants and evaluation rules for every node and constraint kind;
4. fully expanded IR documents for at least eight difficult Yale fixtures;
5. solver-independent reference evaluations for small positive, negative, incomplete, and ambiguous transcripts;
6. explicit decisions for sharing, bounds, predicate nullability/types, credit sources, selected-set attachment, choice ownership, facts, progress, and the auditing/planning boundary;
7. compatibility and migration behavior for MQL 0.1.12.

Approval levels are:

| Level | Approval condition |
| --- | --- |
| Requirements and architecture | This document accepted |
| Semantic IR implementation | RFC approved with no unresolved consequential semantic choices |
| Grammar and audit engine | IR implementation and reduced reference evaluations pass |
| Full planning engine | Separate planning RFC approved and audit semantics remain unchanged |

### First usable milestone

The first release should construct/parse the semantic IR and correctly audit reduced fixtures for P1–P13 and P17–P19, with stable serialization and explanations. P14–P16 follow after the institution catalog, transcript, grade-order, and profile-fact schemas are available. Full multi-term planning follows the separate planning RFC.

This staging reduces delivery risk but does not reduce the final 100%-fidelity acceptance standard.

## Rewrite gate for `./majors`

The majors rewrite should begin only when all of the following are true:

- [ ] The semantic IR RFC and versioned JSON Schema are approved.
- [ ] P1–P20 have normative language semantics.
- [ ] The semantic IR and JSON schema represent all required identities, units, scopes, conditions, predicates, facts, and source spans.
- [ ] The parser and SDKs pass the conformance suite.
- [ ] The reference audit/compiler passes the Yale end-to-end fixtures.
- [ ] The migration guide identifies every obsolete workaround in existing files.
- [ ] A released `pylibmql` package contains the new grammar and serialization.
- [ ] `MQL_Language_Specification.md` is updated to the released version.

After this gate passes, an agent can revisit `./majors`, replace repeated selectors, duplicated branches, comments, invented tags, and prose-only placements with the new structural syntax, and validate each program against the catalog. Until then, rewriting the 189 programs would encode unresolved semantics and require another full migration.

## Required handoff from the MQL team

Please return the following artifacts to the majors team:

1. The final syntax and normative specification.
2. The versioned semantic IR and JSON schema.
3. The conformance suite and results for P1–P20.
4. Rust and Python package versions and installation instructions.
5. A migration guide with before/after examples for every current workaround.
6. A statement of any catalog rule that remains inexpressible.

The handoff is accepted only if item 6 is empty except for genuinely human-discretionary decisions represented through typed approvals.
