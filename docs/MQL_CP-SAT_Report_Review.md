# Review of MQL for CP-SAT Auditing and Planning

Reviewed against `MQL_CP-SAT_Report.md` (dated 2026-10-28) and the current MQL grammar, AST, and language specification.

The direction is strong: treat MQL as a declarative front end, compile course eligibility outside CP-SAT, and use one assignment model for auditing and planning. That is the right architectural center.

Before syntax design, however, the solver semantics need a tighter intermediate model. Several apparent syntax questions are actually unresolved mathematical questions.

## The most important issues

### 1. A pool cannot remain an ordinary leaf

The report introduces:

```mql
SELECT 4 COURSES FROM RANGE(ECON 2000, ECON 9999)
```

but the core model still says a leaf contributes “filled or not” to `k[n]`. A four-course pool must contribute `0..4`, not one Boolean unit.

A generalized contribution variable is needed:

- Ordinary slot: `q[l] in {0,1}`
- Course-counted pool: `q[l] = sum_c x[c,l]`
- Credit-counted pool: `q[l] = sum_c credits[c] * x[c,l]`

A node can then count child contributions, except where a nested node intentionally contributes one Boolean unit. This distinction should live in the semantic IR, not be inferred later from syntax.

### 2. `y[n]` needs equivalence, not only implication

The proposed constraint is:

```text
y[n] => lo <= k[n] <= hi
```

That allows a solver to set `y[n] = false` even when the node is satisfied. Maximizing top-level roots partially masks this, but nested nodes and progress objectives remain vulnerable.

The model needs semantics equivalent to:

```text
y[n] = 1 iff lo <= k[n] <= hi
```

or a carefully defined one-sided version if exceeding `hi` is allowed but only `hi` items count.

This connects directly to the report's open question about upper bounds. There are at least three possible meanings:

- **Cap:** no more than `hi` eligible assignments may be attached to the requirement.
- **Counting cap:** extras are allowed but only `hi` count here.
- **Exact selected set:** the solver chooses at most `hi`; unselected matching transcript courses are irrelevant.

The third interpretation is preferable. A transcript course matching a requirement should not itself violate that requirement; only assignments to it should be capped.

### 3. Assignments beneath inactive branches must be gated

For alternative tracks and conditional branches, courses must not be assigned inside an inactive branch merely to improve progress, totals, or usage.

Every assignment and descendant satisfaction variable needs an activation condition inherited from its branch:

```text
x[c,l] <= active[l]
y[n] <= active[n]
```

Without this, `TOTAL`, `u[c]`, and secondary objectives can silently draw credit from requirements that were not chosen.

### 4. Sharing is more precise than a course-level capacity

The report says:

```text
sum_l x[c,l] <= cap(c)
```

and suggests sharing rules replace that with pair permissions. A single `cap(c)` cannot express:

- sharing between region and seminar;
- no sharing between seminar and senior;
- several requirements within one declared sharing group.

The natural model is an incompatibility relation between assignment scopes:

```text
x[c,l1] + x[c,l2] <= 1
```

for every forbidden pair. The language must also settle:

- whether two slots within the same requirement may reuse a course;
- whether `SHARE A, B, C` permits one course in all three;
- whether sharing is attached to requirement identities or roles;
- how nested requirements inherit the enclosing identity.

Default-exclusive is the safest default and appears closest to Yale's prose.

### 5. Global `u[c]` is insufficient for scoped totals

A single global:

```text
u[c] = OR_l x[c,l]
```

works for a whole-program distinct-course total, but not for:

```mql
TOTAL 7 COURSES FROM ROLE econ
TOTAL 5 COURSES FROM ROLE math
```

Scoped usage is required, conceptually:

```text
u[c,S] = OR of x[c,l] for leaves in scope S
```

The language must then define whether totals count:

- distinct transcript rows;
- distinct canonical courses;
- course credits;
- assignments.

That distinction matters for repeated courses, cross-listings, and shared requirements.

### 6. The “useful match” test is path-dependent

The report proposes fixing the student's current best audit and testing whether candidate `c` raises `k[R]`. There may, however, be many equally optimal audits. A candidate could be useless relative to the chosen assignment and useful after rearranging courses without lowering the audit's objective.

A better definition is counterfactual:

> Candidate `c` is useful for `R` if there exists an assignment using `c` whose primary audit objective is no worse than the baseline optimum and whose progress or satisfaction for `R` is better.

That means fixing objective values, not fixing the exact baseline assignment. “Counts only if moved from another slot” can then be derived by comparing assignment witnesses.

## Where the current implementation stands

The repository currently implements a parser and serialized query tree, not a language with solver-ready semantics:

- Selector lists are explicitly described as “alternatives or a pool as interpreted by the consumer.”
- `SELECT` and `LIMIT` are preserved, but their enforcement is delegated to consumers.
- Nested queries have no identity, description, priority, role, or scope.
- Variables are expanded during parsing, so they are macros rather than named semantic sets.
- `priority` is a `u16`, defaulting to `1`; it has no defined operational meaning.
- `LIMIT` cannot be nested.
- The AST has no stable requirement IDs.

The last point is particularly important: sharing, totals, roles, conditions, diagnostic explanations, and planner results all require stable semantic identities. Descriptions should not serve as identifiers.

## Recommended design sequence

Do not begin by adding all ten syntax extensions directly to the current AST. Settle the semantic IR first.

### 1. Identity and hierarchy

- Named requirement IDs
- Node IDs and parent relationships
- Activation conditions
- Roles and source spans

### 2. Quantity algebra

- Units: slots, courses, credits
- Bounds and upper-bound behavior
- Pool contributions versus nested-node Boolean contributions

### 3. Assignment policy

- Default exclusivity
- Explicit sharing relations
- Repeatable transcript rows
- Cross-listed-course identity

### 4. Scopes

- Requirement subtree
- Named requirement set
- Role set
- Whole program
- Chosen branch only

### 5. Conditions and facts

- Typed facts rather than arbitrary strings
- Choice variables
- Transcript predicates
- Adviser overrides as explicit profile facts

### 6. Objectives and explanations

- Satisfaction ordering
- Progress definition
- Planner costs
- Named constraints for “why this course does not count”

Only after that should concrete MQL syntax be frozen.

## Recommended answers to the report's open questions

- **Leaf semantics:** Preserve current leaves as single slots; add explicit course and credit pools as different semantic node kinds.
- **Sharing default:** Exclusive across named requirements, with explicit sharing exceptions.
- **Priority:** Make it display-only for now or remove it from solver semantics. Lexicographic priority levels are powerful but can create surprising audits.
- **Upper bounds:** Cap assignments selected for that node; extra transcript courses neither count nor invalidate it.
- **Unscoped `LIMIT`:** Reject it or give it an explicit, documented local scope. Implicit program-wide scope is too easy to misuse.
- **Credits:** Use integer atomic units in the solver, but do not hard-code half credits. Store a program or catalog denominator, or use a normalized integer scale.
- **Composition:** Add imports or modules only after requirement identity and override behavior are defined.
- **Facts:** Validate against a typed schema supplied by the consuming institution, not a parser-embedded universal list.

## Conclusion

The report has the correct destination. Its main weakness is that the “core CP-SAT model” is not yet general enough to encode several of the extensions it proposes. The next artifact should be a semantic IR and formal counting and scope rules—not grammar changes or solver code.
