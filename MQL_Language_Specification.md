---
title: Major Query Language (MQL)
subtitle: Language Specification
date: 28 October 2026
---

## Abstract

Major Query Language (MQL) is a declarative language for expressing Yale major requirements as ordered, human-described constraints over courses and catalog-derived categories. An MQL source file may declare externally supplied values, define local variables, and emit top-level `SELECT` or `LIMIT` requirements. Each emitted requirement has a quantity, one or more selectors, a description, and an optional priority. The reference implementation parses an MQL file into a versioned JSON document.

This specification describes the language implemented by `libmql` 0.1.12. It covers lexical rules, grammar, static and dynamic validity conditions, selector functions, variables, external values, nesting, serialization, diagnostics, and the supported CLI, Rust, and Python entry points. Where the repository README and the implementation differ, this document follows the implementation.

**Implementation baseline:** `libmql` 0.1.12  
**Repository revision:** `ba7f276fd32b8b08cd0dcf7fe875bb830a9341d2`  
**Status:** Implementation-derived reference

## 1. Conformance and terminology

The key words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** describe requirements on conforming source files or implementations.

- A **source file** is UTF-8 text conventionally stored with the `.mql` extension.
- A **requirement** is a top-level special statement emitted into the output.
- A **query** is a `SELECT` or `LIMIT` expression containing a quantity and selectors.
- A **selector** identifies a course, category, distribution, placement condition, range, or nested query.
- A **class value** is a validated Yale department symbol plus a four-digit course number and optional lab suffix.
- A **quantity** is either a positive single integer or an inclusive integer range.
- A **variable** is a named, typed value whose name begins with `$`.

This is an implementation-derived specification. The normative sources used to resolve ambiguity are, in descending order: semantic behavior in `libmql/src/parser.rs`; grammar in `libmql/src/mql.pest`; integration tests; public interfaces; examples and README prose.

## 2. Source model

An MQL file has three ordered regions:

1. zero or more external declarations;
2. zero or more local assignments and top-level requirements, interleaved;
3. end of file.

Every external declaration, assignment, and top-level requirement MUST end with a semicolon. An empty file and a file containing only declarations or assignments are syntactically valid and serialize with an empty `requirements` array.

External declarations MUST precede all assignments and requirements. Local assignments are evaluated in source order. A variable is therefore usable only after it has been provided by an external declaration or evaluated by an earlier assignment.

### 2.1 Minimal requirement

```mql
SELECT 1 FROM MATH 2250 : "Take linear algebra";
```

The explicit `CLASS` form is equivalent:

```mql
SELECT 1 FROM CLASS(MATH 2250) : "Take linear algebra";
```

### 2.2 Complete example

```mql
extern $TRACK;

$linear = [MATH 2250, MATH 2260];
$senior = RANGE(MATH 4800, MATH 4890);
$priority = 2;

SELECT 1 FROM $linear : "Linear algebra with proofs" : $priority;
SELECT 1 FROM [$senior, PLACEMENT("MATH 4750 with DUS approval")]
  : "Senior requirement";
LIMIT 2 FROM [TAG_DEPT("YC Elective", $TRACK), DIST("QR")]
  : "At most two courses from this group" : 3;
```

The caller must provide `$TRACK` as an MQL string expression, for example `"MATH"`.

## 3. Lexical structure

### 3.1 Character set and encoding

The CLI reads source as UTF-8. Keywords, identifiers, department symbols, quantities, and course identifiers are constrained to ASCII by the grammar. String contents may contain arbitrary non-newline characters representable in the input encoding.

### 3.2 Whitespace

Space, horizontal tab, carriage return, and line feed are insignificant wherever the grammar permits token separation. Whitespace may occur around punctuation and operators. Whitespace is not permitted inside a variable name, numeric literal, or course number. A class value permits zero or more ordinary space characters between its department symbol and course number; tabs and newlines are not accepted at that particular internal boundary.

### 3.3 Comments

A line comment begins with `//` and continues through the last character before the next line feed. Comments are treated as whitespace.

```mql
// This requirement permits either course.
SELECT 1 FROM [MATH 2250, MATH 2260] : "Linear algebra";
```

There are no block comments. A `//` sequence inside a string is string content, not a comment.

### 3.4 Case sensitivity

The statement keywords `SELECT`, `LIMIT`, and `FROM` are uppercase-only. The declaration keyword `extern` is lowercase-only. Selector function names accept exactly uppercase or lowercase spellings, such as `CLASS` and `class`; mixed-case spellings such as `Class` are not recognized. Variable names are case-sensitive. Department symbols are uppercase-only except that `&` is also permitted as a symbol character.

### 3.5 Strings

A string begins and ends with a double quote. It MUST NOT contain a literal carriage return or line feed. A literal double quote is represented by two consecutive double quotes.

```mql
$note = "The DUS said ""approved"".";
```

The value of `$note` is `The DUS said "approved".`. Backslash escaping is not supported; `\"` does not escape a quote.

### 3.6 Variables

A variable has this lexical form:

```text
$ ( ASCII letter | _ ) ( ASCII letter | ASCII digit | _ )*
```

Examples of valid names are `$x`, `$_track`, and `$linearAlgebra2`. `$2nd` is invalid. The `$` sigil is part of the variable name in the Rust and Python external maps.

### 3.7 Quantities

A single quantity is one or more ASCII decimal digits. A quantity range consists of two single quantities separated by `-`, with optional insignificant whitespace around the hyphen.

All values are parsed as unsigned 16-bit integers and therefore MUST be in the range 0 through 65,535 at the lexical conversion boundary. Additional semantic restrictions on zero and ordering are specified in Section 7.

### 3.8 Class values

A class value consists of:

- a department symbol of exactly three or four characters, each an uppercase ASCII letter or `&`;
- zero or more ordinary spaces;
- exactly four decimal digits;
- an optional uppercase `L` lab suffix.

Examples include `MATH2250`, `MATH 2250`, `CPSC 2010L`, and `S&DS 1234`. The department symbol MUST also occur in the implementation's embedded Yale department list. Course number `0000` is lexically and semantically accepted. The lab suffix is retained as a boolean in JSON.

The grammar recognizes one- or two-letter and five-or-more-letter alphabetic department candidates so the semantic layer can issue a targeted length error. Other malformed symbols fail at the grammar layer.

## 4. Concrete grammar

The following EBNF is a readable equivalent of the Pest grammar plus the implemented variable and selector alternatives. `{ X }` means zero or more repetitions; `[ X ]` means optional; alternatives are separated by `|`.

```ebnf
File               ::= { ExternalDeclaration ";" }
                       { ( Assignment | Requirement ) ";" } ;

ExternalDeclaration ::= "extern" Variable ;
Assignment          ::= Variable "=" VariableValue ;

Requirement         ::= Statement ":" ( String | Variable )
                       [ ":" ( UnsignedInteger | Variable ) ] ;

Statement           ::= ( "SELECT" | "LIMIT" ) Quantity "FROM" Selector ;
Quantity            ::= QuantityRange | UnsignedInteger | Variable ;
QuantityRange       ::= UnsignedInteger "-" UnsignedInteger ;

Selector            ::= SelectorList | SelectorSingle ;
SelectorList        ::= "[" SelectorSingle { "," SelectorSingle } "]" ;
SelectorSingle      ::= Statement | Variable | SelectorFunction | ClassValue ;

SelectorFunction    ::= FunctionName "(" FunctionArgument
                       { "," FunctionArgument } ")" ;
FunctionArgument    ::= String | Variable | ClassValue ;

FunctionName        ::= "CLASS" | "class"
                      | "PLACEMENT" | "placement"
                      | "TAG" | "tag"
                      | "TAG_DEPT" | "tag_dept"
                      | "DIST" | "dist"
                      | "DIST_DEPT" | "dist_dept"
                      | "RANGE" | "range"
                      | "RANGE_DIST" | "range_dist"
                      | "RANGE_TAG" | "range_tag" ;

VariableValue       ::= SelectorList | SelectorFunction | QuantityRange
                      | UnsignedInteger | String | ClassValue ;

Variable            ::= "$" ( Letter | "_" ) { Letter | Digit | "_" } ;
UnsignedInteger     ::= Digit { Digit } ;
String              ::= '"' { '""' | AnyExceptQuoteCRLF } '"' ;
ClassValue          ::= DepartmentSymbol { " " } CourseId ;
DepartmentSymbol    ::= DeptChar DeptChar DeptChar [ DeptChar ] ;
DeptChar            ::= UppercaseLetter | "&" ;
CourseId            ::= Digit Digit Digit Digit [ "L" ] ;
```

The concrete grammar admits any alphanumeric/underscore function name in the function position so that the implementation can report a spelling suggestion. Names outside the recognized function set are nevertheless semantically invalid.

## 5. Requirements and queries

### 5.1 Top-level requirement form

```mql
SELECT quantity FROM selector : description : priority;
LIMIT  quantity FROM selector : description : priority;
```

The final `: priority` is optional. If omitted, priority is `1`. The description is mandatory and MUST evaluate to a string. Priority MUST be a single integer or a variable containing a single quantity; a quantity range is invalid as a priority.

`SELECT` and `LIMIT` are preserved in the output as query types `Select` and `Limit`. MQL itself only models the constraint; interpretation or enforcement of the distinction belongs to the consuming application.

### 5.2 Nested queries

A statement can appear anywhere a selector can appear:

```mql
SELECT 1 FROM [
  SELECT 2 FROM [TAG("Core"), TAG("Methods")],
  MATH 3500
] : "Complete either the grouped option or MATH 3500";
```

A nested query is serialized as a `Query` selector. Nested queries do not carry a description or priority. `LIMIT` MUST NOT be nested; only top-level requirements may use it.

### 5.3 Selector lists

A selector list is non-empty. Its members are alternatives or a pool as interpreted by the consumer, and their order is preserved. Lists cannot contain a trailing comma. A variable containing a selector list expands in place when used as a selector; its members are inserted into the surrounding selector vector rather than wrapped as a nested list.

```mql
$pair = [MATH 2250, MATH 2260];
SELECT 1 FROM [MATH 1150, $pair] : "One of three courses";
```

The resulting selector vector contains three class selectors.

## 6. Selector functions

Function arguments are type-checked after parsing. Variables used as arguments MUST resolve to either a string or class value, as appropriate.

| Function | Required arguments | Resulting selector | Intended payload |
|---|---|---|---|
| `CLASS` | one class | `Class` | One catalog course |
| `PLACEMENT` | one string | `Placement` | Placement, approval, substitution, or prose condition |
| `TAG` | one string | `Tag` | Catalog tag/category |
| `TAG_DEPT` | string tag, string code | `TagCode` | Tag scoped by a code |
| `DIST` | one string | `Dist` | Distribution designation |
| `DIST_DEPT` | string distribution, string code | `DistCode` | Distribution scoped by a code |
| `RANGE` | class start, class end | `Range` | Inclusive course endpoints |
| `RANGE_DIST` | class start, class end, string distribution | `RangeDist` | Course range filtered by distribution |
| `RANGE_TAG` | class start, class end, string tag | `RangeTag` | Course range filtered by tag |

### 6.1 `CLASS`

```mql
CLASS(CPSC 2010)
```

The shorthand `CPSC 2010` produces the same selector when used directly in a selector position. `CLASS` exists primarily for explicitness and for assignment as a selector value.

### 6.2 `PLACEMENT`

```mql
PLACEMENT("5 on AP Calculus")
```

The implementation does not interpret the string.

### 6.3 `TAG` and `TAG_DEPT`

```mql
TAG("YC MATH Distribution")
TAG_DEPT("YC GLBL Elective", "HU")
```

`TAG_DEPT`'s second argument is a free string. It is not validated against the embedded department list.

### 6.4 `DIST` and `DIST_DEPT`

```mql
DIST("QR")
DIST_DEPT("L4", "ARBC")
```

Both arguments of `DIST_DEPT` are free strings. The function name's first parameter is called `dist` and its second `code` in serialized output.

### 6.5 Range selectors

```mql
RANGE(MATH 2250, MATH 4699L)
RANGE_DIST(CPSC 2000, CPSC 4999, "QR")
RANGE_TAG(ECON 1000, ECON 4999, "YC Elective")
```

Range endpoints are validated individually as class values. The implementation does not require matching departments, ascending course numbers, or a particular treatment of the endpoint lab flag. Those meanings are left to the consumer.

## 7. Quantities and validity rules

### 7.1 Single quantities

A query quantity of zero is invalid. A locally assigned single quantity of zero is also invalid. Valid single quantities therefore range from 1 through 65,535.

### 7.2 Quantity ranges

For `n-k`, the implementation requires `k >= n`. Both endpoints MUST fit in `u16`.

A range beginning at zero is invalid when used by a top-level `SELECT` or `LIMIT` requirement. A zero-based range is accepted in a nested `SELECT`, because nested queries are parsed with the top-level restriction disabled. A zero-based range may also be assigned to a variable, but using that variable as a top-level quantity is rejected.

### 7.3 Priority

Priority defaults to `1`. A numeric priority is parsed directly as `u16`. Unlike query quantities and assigned single quantities, an explicit priority of `0` is accepted by the current implementation. A priority variable must contain `Quantity::Single`; a quantity range is rejected.

### 7.4 Function arity and argument types

The grammar permits one or more arguments for every selector function. The semantic layer enforces the exact arity and types listed in Section 6. Empty argument lists are syntactically invalid. Extra arguments, missing arguments, and wrong types produce function-specific errors.

## 8. Variables and evaluation

### 8.1 Value types

Variables are dynamically bound to one of five implementation types:

| Variable type | Assignment examples | Valid use sites |
|---|---|---|
| selector list | `[MATH 2250, MATH 2260]` | selector position; expands in place |
| selector | `TAG("Core")` | selector position |
| quantity | `3`, `1-2` | query quantity; single only for priority |
| string | `"Core requirement"` | description or compatible function argument |
| class | `MATH 2250` | selector position or compatible function argument |

Assignments cannot directly use a bare variable or statement as their right-hand side. They may, however, construct a new selector list or selector function that refers to earlier variables.

### 8.2 Sequential scope and rebinding

There is one file-wide variable environment. Assignment is sequential and a later assignment to the same name replaces the earlier value. Requirements emitted before rebinding retain values cloned during their evaluation. There are no block scopes and no forward references.

### 8.3 Type errors

Using a variable at an incompatible site is an error. For example, a string cannot be used as a selector, a selector list cannot be used as a function argument, and a range quantity cannot be used as priority. Error messages report the expected and actual implementation types.

## 9. External variables

An external declaration reserves a variable whose value must be supplied by the caller:

```mql
extern $LEVEL;
extern $DESCRIPTION;

SELECT 1 FROM DIST_DEPT($LEVEL, "ARBC") : $DESCRIPTION;
```

All external declarations MUST occur before any assignment or requirement. During evaluation, each declaration immediately looks up its exact variable name in the external map. If no value is present, parsing fails even if the variable is never subsequently used.

External values use the same expression language as assignment values: selector list, selector function, quantity range, single quantity, string, or class value. External expressions are parsed in an empty variable environment and therefore cannot refer to other variables.

The Rust and Python libraries expect external-map keys including the `$` sigil. The CLI `--var` option expects a name without `$` and adds the sigil itself:

```console
mql requirements.mql --var 'LEVEL="L4"' \
  --var 'DESCRIPTION="Must take Arabic at the L4 level"'
```

Providing an undeclared external-map key has no effect. Repeated external declarations are permitted and perform repeated lookup/insertion. A later local assignment may replace an externally supplied value.

## 10. Output data model and JSON

Parsing produces a versioned object:

```text
MQLQueryFile
├── version: string
└── requirements: MQLRequirement[]
    ├── query: MQLQuery
    │   ├── quantity: Quantity
    │   ├── type: Select | Limit
    │   └── selector: Selector[]
    ├── description: string
    └── priority: u16
```

Serde's default externally tagged enum representation is used. Field order follows the Rust structure definitions but consumers SHOULD treat JSON object order as insignificant.

### 10.1 Quantity JSON

```json
{ "Single": 3 }
```

```json
{ "Many": { "from": 1, "to": 2 } }
```

### 10.2 Class JSON

```json
{
  "department_id": "CPSC",
  "course_number": 2010,
  "lab": true
}
```

### 10.3 Selector JSON shapes

```json
{ "Class": { "department_id": "MATH", "course_number": 2250, "lab": false } }
{ "Placement": "5 on AP Calculus" }
{ "Tag": "YC MATH Distribution" }
{ "TagCode": { "tag": "YC Elective", "code": "HU" } }
{ "Dist": "QR" }
{ "DistCode": { "dist": "L4", "code": "ARBC" } }
{ "Range": { "from": { "department_id": "MATH", "course_number": 1000, "lab": false }, "to": { "department_id": "MATH", "course_number": 1999, "lab": false } } }
{ "RangeDist": { "from": { "department_id": "CPSC", "course_number": 2000, "lab": false }, "to": { "department_id": "CPSC", "course_number": 4999, "lab": false }, "dist": "QR" } }
{ "RangeTag": { "from": { "department_id": "ECON", "course_number": 1000, "lab": false }, "to": { "department_id": "ECON", "course_number": 4999, "lab": false }, "tag": "YC Elective" } }
{ "Query": { "quantity": { "Single": 2 }, "type": "Select", "selector": [] } }
```

The final `Query` illustration shows shape only; a source-level selector list cannot actually be empty.

### 10.4 Complete serialization example

Input:

```mql
SELECT 1 FROM [CPSC 2010L, PLACEMENT("approved equivalent")]
  : "Introductory requirement" : 2;
```

Output shape:

```json
{
  "version": "0.1.12",
  "requirements": [
    {
      "query": {
        "quantity": { "Single": 1 },
        "type": "Select",
        "selector": [
          {
            "Class": {
              "department_id": "CPSC",
              "course_number": 2010,
              "lab": true
            }
          },
          { "Placement": "approved equivalent" }
        ]
      },
      "description": "Introductory requirement",
      "priority": 2
    }
  ]
}
```

The `version` value is the `libmql` package version used to parse the source, not a version declared within the MQL file.

## 11. Diagnostics

The reference implementation reports both grammar errors and semantic errors with source spans. Selected semantic diagnostics include:

- undefined variable;
- incompatible variable type at a use site;
- external variable declared but not supplied;
- quantity cannot fit in `u16`;
- zero single quantity;
- top-level range beginning at zero;
- decreasing quantity range;
- nested `LIMIT`;
- invalid selector function name, with closest-name suggestion;
- wrong selector function arity or argument types;
- invalid department symbol length;
- department absent from the embedded Yale catalog list, with closest-symbol suggestion.

Diagnostics are part of the current user experience but their exact prose is not a stable serialization contract. Consumers SHOULD avoid program logic that depends on full error-message strings.

## 12. Interfaces

### 12.1 Command-line interface

```console
mql [OPTIONS] <INPUT>
```

`INPUT` MUST have the `.mql` extension. Without `--output`, pretty JSON is printed to standard output. An output path supplied with `-o` or `--output` MUST end in `.json`; the file is created or truncated. `-D` or `--var NAME=EXPR` supplies an external value and may be repeated. `-V` or `--version` prints both CLI and library versions; invoking the CLI with no input also prints version information.

Examples:

```console
mql examples/math_ba.mql
mql requirements.mql -o requirements.json
mql requirements.mql -D 'LEVEL="L4"' -D 'COUNT=2'
```

### 12.2 Rust library

The principal API is:

```rust
pub fn parse(text: &dyn AsRef<str>) -> anyhow::Result<ParseResult>;
pub fn parse_with_externals(
    text: &dyn AsRef<str>,
    externals: HashMap<String, VarValue>,
) -> anyhow::Result<ParseResult>;
pub fn parse_extern_value(expr: &str) -> anyhow::Result<VarValue>;
```

`ParseResult` exposes compact and pretty JSON serialization and access to the parsed Rust model. External keys include `$`.

### 12.3 Python library

```python
import pylibmql

result = pylibmql.parse(
    'SELECT 1 FROM MATH 2250 : "Take linear algebra";'
)
print(result.version())
print(result.json())
print(result.json_pretty())
```

External values are supplied as MQL expression strings:

```python
result = pylibmql.parse_with_externals(
    'extern $course; SELECT 1 FROM $course : "Required";',
    {'$course': 'MATH 2250'},
)
```

Python parse failures are raised as `ValueError`. `parse_extern_value(expr)` is exposed for inspection and returns a debug string, while `parse_with_externals` accepts the expression strings directly.

## 13. Implementation-defined catalog validation

The reference implementation embeds `yale_departments.txt` and accepts a class value only if its department symbol exactly matches one of those entries. This makes accepted class values dependent on the library build. The current file contains 124 lines, but the list itself is data rather than language grammar and may change between releases.

String codes supplied to `TAG_DEPT` and `DIST_DEPT` are not checked against that list. Only syntactic class values are catalog-validated.

## 14. Edge cases and portability notes

- `SELECT`, `LIMIT`, and `FROM` have no lowercase forms.
- Selector function names have uppercase and lowercase forms only; mixed case is invalid.
- `extern` has no uppercase form.
- A selector list must contain at least one item and cannot end with a trailing comma.
- Strings are single-line and use doubled quotes, not backslashes, for embedded quotation marks.
- A class may omit the space between department and number.
- Only literal ordinary spaces, not tabs, are accepted inside a class value.
- Class ranges are not checked for endpoint ordering or matching departments.
- Priority zero is accepted even though a query quantity or assigned single quantity zero is rejected.
- External values cannot reference variables.
- Extra entries in an external-value map are ignored.
- Local variable rebinding is allowed.
- The output schema may evolve with the library version. Consumers SHOULD inspect `version` and SHOULD tolerate additive fields.

## 15. Authoring guidance

For maintainable MQL:

1. Prefer one requirement per visual block and give every requirement a concise, user-facing description.
2. Use direct class shorthand for simple course selectors and named variables for reused pools.
3. Use `PLACEMENT` only for conditions that cannot be represented structurally.
4. Reserve priority for a documented consumer policy; omission already means `1`.
5. Keep external declarations at the top and use them for caller-specific track, level, or catalog values.
6. Use uppercase statement and function spelling consistently, even where lowercase function aliases exist.
7. Run the same `libmql` version in validation and production because catalog data and output fields are versioned with the library.

## Appendix A. Quick reference

```mql
// External inputs first
extern $CODE;

// Local values
$course = MATH 2250;
$pool = [$course, MATH 2260];
$tag = TAG_DEPT("YC Elective", $CODE);
$count = 1-2;
$description = "Complete linear algebra";
$priority = 2;

// Emitted requirements
SELECT $count FROM [$pool, $tag] : $description : $priority;
LIMIT 1 FROM PLACEMENT("DUS-approved substitution") : "Substitution cap";
```

## Appendix B. Selector-to-JSON mapping

| Source construct | Rust selector variant | JSON tag |
|---|---|---|
| `MATH 2250`, `CLASS(MATH 2250)` | `Class` | `Class` |
| `PLACEMENT("…")` | `Placement` | `Placement` |
| `TAG("…")` | `Tag` | `Tag` |
| `TAG_DEPT("…", "…")` | `TagCode` | `TagCode` |
| `DIST("…")` | `Dist` | `Dist` |
| `DIST_DEPT("…", "…")` | `DistCode` | `DistCode` |
| `RANGE(A, B)` | `Range` | `Range` |
| `RANGE_DIST(A, B, "…")` | `RangeDist` | `RangeDist` |
| `RANGE_TAG(A, B, "…")` | `RangeTag` | `RangeTag` |
| nested `SELECT` | `Query` | `Query` |

## Appendix C. Known documentation divergences

Older README and Python stub examples show JSON without the query `type` field and class `lab` field. The current Rust structures serialize both fields. The README grammar also omits variables, externals, `LIMIT`, bare class selectors, department-scoped and range-filter functions, the optional lab suffix, and semantic catalog validation. This specification includes those implemented features.

## Appendix D. Source basis

This specification was derived from the following repository artifacts at the stated revision:

- `libmql/src/mql.pest` — concrete grammar;
- `libmql/src/parser.rs` — semantic checks, data model, and evaluation;
- `libmql/src/lib.rs` — Rust parsing and serialization API;
- `libmql/src/yale_departments.txt` — embedded department allowlist;
- `libmql/tests/integration_tests.rs` and test inputs — variable and external behavior;
- `cli/src/cli.rs` and `cli/src/main.rs` — CLI contract;
- `src/lib.rs` and `pylibmql.pyi` — Python binding contract;
- `examples/*.mql` and `README.md` — examples and legacy documentation.

