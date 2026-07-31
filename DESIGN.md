# Reprobate Rendering Engine Rebuild

- Status: Draft
- Target: `0.2.x`
- Scope: Replace the rendering engine, preserve API compatibility, and add one
  keyword-only inference policy.

## Summary

Reprobate will keep its existing role and public surface: turn an arbitrary Python
object into a useful, single-line diagnostic representation that does not exceed a
character budget.

The current recursive allocator will be replaced. The new engine will model values
semantically, establish a useful structural skeleton, and then spend the remaining
budget on progressively more informative refinements. Real values take priority
when they are affordable. Type and schema information preserve meaning when real
values are too expensive.

The rebuild is an internal rewrite with an evolutionary cutover:

- Keep the public API and extension protocol.
- Establish behavioral contracts and characterization fixtures first.
- Implement a new engine alongside the legacy engine.
- Port built-in and optional types in stages.
- Cut over once the new contract suite passes, then remove the legacy engine.

## Motivation

The existing engine proves the core concept, but its allocation model makes further
improvement difficult:

- A complete representation can be replaced by a summary even when it fits.
- Every container renderer independently accounts for punctuation, separators,
  omission markers, and child budgets.
- Fixed minimum child budgets can leave useful space unspent.
- Nested mappings tend to spend budget inside early values before communicating the
  shape of the overall result.
- Type information is available only as a late object-attribute fallback, rather
  than as a general representation option.
- Adding path awareness, schema metadata, redaction, alternate cost functions, or
  bounded inference would require more ambient global state.

These are properties of the allocator rather than isolated defects. Replacing the
allocator is simpler than incrementally modifying every renderer around it.

## Goals

### Required behavior

1. **Hard character budget**

   For every nonnegative budget, the returned string has `len(result) <= budget`.

2. **Full representation when it fits**

   For supported values, if the canonical complete representation fits, return it
   without degradation.

3. **Useful nested structure**

   For mappings and record-like objects, preserve keys and high-level shape before
   spending most of the budget deep inside an early child.

4. **Values before schema**

   Show exact scalar values when affordable. Use type and schema summaries when
   values or containers cannot be shown economically.

5. **Configurable runtime inference**

   Let callers choose whether aggregate type hints are disabled, exhaustively
   established within the work limit, or inferred through bounded best-effort
   sampling. Best-effort type expressions are diagnostic hints, not validation
   guarantees.

6. **Bounded work**

   A small output budget must not require rendering, scanning, or allocating an
   unbounded representation of a large object.

7. **Stable extension behavior**

   Preserve registered renderers, `__budget_repr__`, recursive child rendering,
   policy propagation, and cycle detection.

8. **Escaped, single-line output**

   Strings and bytes preserve quoting and escapes. Truncation must not introduce raw
   control characters or split an escape sequence into a misleading fragment.

9. **Predictable allocation policies**

   Retain `greedy` and `even`, with documented behavior that applies recursively.

### Non-goals

- Producing an expression accepted by `eval` in every degraded case.
- Replacing a general pretty-printer or supporting multiline layouts in `0.2`.
- Treating a character budget as an exact LLM token, byte, or terminal-width budget.
- Finding a mathematically optimal representation with a global knapsack solver.
- Consuming arbitrary iterators to infer their contents.
- Sandboxing user-defined `repr` methods or custom renderers.
- Publishing schema-aware API additions as part of the initial cutover.

## Public API compatibility

The existing surface remains supported, with one additive keyword-only option:

```python
render(
    obj,
    budget=200,
    policy="greedy",
    *,
    inference="best_effort",
)
register(MyType)
obj.__budget_repr__(budget)
render_child(obj, budget)
render_attrs(attrs, type_name, budget)
```

### Intentional validation changes

- `budget=0` returns `""`.
- Negative budgets raise `ValueError`.
- Unknown policy names raise `ValueError`.
- Unknown inference policy names raise `ValueError`.

`inference` accepts `"off"`, `"exact"`, or `"best_effort"`. It is orthogonal to
`policy`: inference controls how aggregate type and shape hints are discovered,
while `policy` controls where the output budget is spent. The default is
`"best_effort"`.

### Registered renderers and the protocol

Existing renderers continue to receive `(obj, budget)` and return a string. Their
result is an opaque leaf to the new planner and is clipped at the public boundary as
a final safety measure.

`render_child()` delegates through the active render context, retaining the current
allocation policy, inference policy, and cycle state. Calling it outside an active
`render()` remains an error.

`render_attrs()` becomes a compatibility adapter that creates a record-like node and
uses the same allocator as mappings and dataclasses.

Built-in extensions may use internal node APIs to expose richer shape information.
Those internal APIs are not a new contract for third-party renderers.

## Output semantics

The result is a **bounded diagnostic representation**. Complete renderings should
look like normal Python representations where practical. Degraded renderings use
angle-bracketed summaries to make it clear that information has been replaced.

### Representation ladders

Each semantic value has an ordered set of truthful representations. The planner
selects and refines these representations under the available budget.

Scalar values are atomic:

```text
1.852 -> <float> -> omitted
True  -> <bool>  -> omitted
None  -> <None>  -> omitted
```

Integers and floating-point values are not textually truncated. A prefix such as
`1234...` can be mistaken for a different value; the type stub is safer.

Strings and bytes can be previewed:

```text
'a long escaped value'
<str(1842): 'a long escap...'>
'a long escap...'
<str(1842)>
<str>
omitted
```

Previews retain valid quoting and escapes. A useful value preview takes priority
over length metadata. Once that preview fits, the planner may add total length when
there is sufficient additional budget. A size-only stub is useful when preserving
outer structural breadth matters more than showing content. String counts use Python
characters; bytes counts use bytes.

Sequences can communicate values, element shape, and count:

```text
['alice', 'bob', ...198 more]
<list[str](200): 'alice', 'bob', ...>
<list[str](200)>
<list(200)>
omitted
```

Mappings have both record-like and open-mapping forms:

```text
{'parse': 0.012, 'run': 1.84, 'total': 1.852}
{'parse': 0.012, 'run': 1.84, 'total': <float>}
<{'parse': float, 'run': float, 'total': float}>
<dict[str, float](3)>
<dict(3)>
omitted
```

The schema-only fixed-record form is a fallback, not the preferred representation
when the real values fit.

### Fixed records versus open mappings

The notation distinguishes literal fields from key and value types:

```text
<{'id': int, 'name': str, 'active': bool}>
<dict[str, float](84)>
<dict[int, User](42)>
<dict[str, int | str | None](20)>
```

- `{literal_key: value_type}` describes a known record shape.
- `dict[key_type, value_type]` describes an open-ended homogeneous or union-typed
  mapping.
- Literal string keys remain quoted, so their type is not merely implicit.

A sequence of records can share one shape instead of repeating it:

```text
<list[{'id': int, 'name': str, 'active': bool}](200)>
```

Optional fields in a merged record shape use `?` on the literal key:

```text
<list[{'id': int, 'error'?: str}](80)>
```

The key marker describes presence; a union with `None` describes value nullability:

```text
{'error'?: str}          # the key may be absent
{'error': str | None}    # the key is present and may contain None
{'error'?: str | None}   # both conditions apply
```

## Allocation model

The allocator has two major phases: a bounded complete-render probe and compact
planning.

### 1. Bounded complete-render probe

For supported built-in and structured values, attempt the canonical complete
rendering using a writer limited to `budget + 1` characters.

- Stop as soon as the limit is exceeded.
- Do not first construct an unbounded `repr` string.
- Preserve normal delimiters, separators, escapes, singleton tuple commas, and
  insertion order.
- Apply the same cycle detection used by compact rendering.

If the probe completes within the budget, return it unchanged. Otherwise, proceed
to compact planning. Probe results and inspected semantic nodes may be cached for the
duration of the render session to avoid duplicate work.

For an opaque custom renderer, the custom renderer controls what “complete” means;
the engine can only enforce its returned length.

### 2. Structural skeleton and refinement

Compact planning begins with the cheapest truthful representation of the outer
value. It then establishes structural coverage and applies refinements.

For a mapping:

1. Account for the mapping shell and a truthful omission marker.
2. Visit entries in insertion order.
3. Prefer a complete key representation.
4. Try the real scalar value first.
5. If the real value would prevent useful structural coverage, fall back to the
   value's type or shape stub.
6. Keep additional keys with stubs before deeply expanding an earlier complex child.
7. Spend remaining budget on refinements according to policy.
8. Omit entire entries only after their useful value and stub forms fail to fit.

This should make a tool-like result degrade along lines such as:

```python
{
    'status': 'ok',
    'result': {
        'users': <list[str](200): 'alice', 'bob', ...>,
        'cursor': 'abc...',
    },
    'timing': {'parse': 0.012, 'run': 1.84, 'total': 1.852},
}
```

At smaller budgets, complex fields lose samples and detail before cheap scalar
fields lose their real values:

```python
{
    'status': 'ok',
    'result': <dict(2)>,
    'timing': <dict[str, float](3)>,
}
```

Exact spellings and line wrapping in these examples are illustrative; actual output
remains single-line.

### Greedy policy

`greedy` uses insertion order and prefers depth in the earliest visible child after
a viable outer skeleton has been established. It does not allow the first complex
child to erase all evidence of later inexpensive siblings when stubs for those
siblings fit.

### Even policy

`even` prefers sibling breadth. It establishes comparable representations for
visible siblings, then uses max-min allocation for refinements. Before allocation,
bounded complete-render probes identify children with finite demand. Children that
complete below their initial share return the unused characters to the common pool,
which is redistributed among siblings that can still improve. Opaque custom
renderers are treated as open-ended and are not invoked speculatively. Nested
containers inherit the same policy.

Both policies share these higher-priority rules:

- Return the complete representation if it fits.
- Prefer truthful real scalar values to equally affordable type names.
- Preserve outer structure before optional deep detail.
- Never exceed the hard budget.

## Schema and type information

Schema is evidence about a value, not a substitute for a value that can be shown
economically.

### Evidence levels and output semantics

The internal schema model records how each fact was obtained:

1. **Authoritative**

   Supplied by validated or structural library metadata such as an Arrow schema or
   NumPy dtype.

2. **Declared**

   Supplied by an annotation or an external schema that may not itself validate the
   runtime value.

3. **Exact**

   Every relevant item was inspected safely and within the work limit.

4. **Sampled**

   A deterministic, bounded subset was inspected.

5. **Unknown**

   No defensible type or shape conclusion is available.

Evidence remains available internally for precedence and planning, but it is not
encoded as sample counts or sigils in the rendered text. Aggregate type expressions
are diagnostic hints whose confidence is governed by the call-time inference policy:

```text
<list[str](200)>
```

Under `"best_effort"`, the same compact form may describe exhaustive inspection of a
small collection or bounded sampling of a large one. The output does not include
`sample=32` or a marker such as `~str`. This spends the budget on the value rather
than inference provenance.

### Inference policies

`"off"` disables aggregate runtime inference. Intrinsic type information, basic
per-value type stubs, and authoritative metadata from known extensions remain
available.

`"exact"` emits an inferred aggregate type only when every relevant element can be
inspected within the internal work limit. Larger or more complex containers fall
back to a less specific summary:

```text
<list(100000)>
```

`"best_effort"` first attempts exact inference under the same work limit, then uses a
bounded deterministic sample for larger containers. It is the default and may emit:

```text
<list[str](100000)>
<list[str | None](100000)>
<list[{'id': int, 'name': str}](100000)>
```

These expressions summarize the engine's best available observation; they are not
runtime validation guarantees.

### Authoritative sources

Built-in adapters can derive declared schema from:

- Dataclass field annotations.
- Pydantic model fields.
- Named-tuple annotations.
- NumPy dtypes and shapes.
- Pandas and Polars schemas.
- Arrow schemas.
- A future external schema supplied through the render context.

The engine should normalize these sources into its own small schema model rather
than directly embedding arbitrary `typing` representations.

### Runtime inference

Runtime inference may provide:

- A common exact type for a small built-in list or tuple.
- A union of observed types for a heterogeneous sequence.
- Key and value types for an open mapping.
- A merged record shape for a sequence of mappings.
- Required fields present in every inspected record.
- Optional fields present in only some inspected records.

Inference is conservative:

- Do not consume one-shot iterators.
- Prefer safe inspection of built-in containers and known extensions.
- Cap schema depth, inspected elements, and merged record fields.
- Preserve exact type distinctions unless a deliberate normalization exists.
- Treat user code reached through `__len__`, indexing, properties, or `repr` as
  potentially expensive or fallible.

## Bounded work

The character budget controls output size. A separate internal inspection budget
controls CPU work and temporary memory.

An inspection budget limits at least:

- Semantic nodes visited.
- Sequence elements examined for type inference.
- Mapping entries examined for shape inference.
- Schema recursion depth.
- Fields retained in a merged record shape.
- Characters accepted from opaque representations before aborting a probe where
  streaming or bounded production is possible.

The initial internal limits are:

```text
Maximum elements for exact inspection: 256
Best-effort sample size:                 32
Maximum semantic nodes inspected:       1,024
Maximum schema depth:                    3
Maximum merged record fields:            32
Maximum cumulative record-key chars:  1,024
Maximum runtime type-name chars:         128
Render-planning work nodes: max(1,024, 4 * character budget)
```

These are implementation defaults to validate through tests and benchmarks, not
public API commitments.

For safely indexable built-in sequences larger than 256 elements, best-effort
sampling uses the first 8 elements, the last 8, and 16 evenly spaced interior
elements. It avoids head-only bias without random output or an O(n) reservoir scan.
Mappings use bounded insertion-order head and, where safely available, tail entries;
reaching evenly spaced mapping entries must not require walking the entire mapping.

`"exact"` does not force an unbounded scan. When exhaustive inspection cannot finish
within these limits, it emits a less specific shape. `"best_effort"` uses whatever
bounded evidence is available.

Sampling and planning must be deterministic for the same process, object state,
budget, and policy.

## Internal architecture

The proposed layers are conceptual; they may be consolidated into fewer modules if
that keeps the implementation clearer.

### Public facade

Validates arguments, creates a render session, adapts legacy protocols, and enforces
the final hard limit.

### Render session/context

Carries state that should be explicit inside the engine:

```python
@dataclass
class RenderContext:
    policy: Policy
    inference: InferencePolicy
    seen: set[int]
    inspection: InspectionBudget
    work: InspectionBudget
    schema_cache: dict
```

External schema input and path tracking remain deferred internally as well as
publicly. Possible future context fields include `schema`, `path`, redaction rules,
maximum depth, and a cost function for approximate token or byte budgeting.

### Semantic nodes

Inspection converts supported values into lazy nodes such as:

- `ScalarNode`
- `TextNode`
- `SequenceNode`
- `MappingNode`
- `RecordNode`
- `ObjectNode`
- `OpaqueNode`
- `CircularNode`

Nodes retain access to their source value but do not eagerly expand an entire large
object graph. They expose truthful representation choices and lazy child access.

### Schema model

A small internal schema vocabulary describes scalars, unions, sequences, mappings,
records, and unknown values. Every inferred component carries its evidence level.

### Planner

The planner selects a structural skeleton and refinements under the available
budget. It uses deterministic local decisions rather than a global optimizer. For
`even`, it performs bounded complete-demand probes at each visible sibling layer,
then max-min allocates the remaining characters. Probes share a work allowance
proportional to the possible output and do not invoke opaque customization hooks.

### Bounded writer

The writer owns delimiters, separators, omission markers, quoting, and the final
limit. It must make it difficult for an individual node renderer to introduce a
budget overrun through incorrect punctuation arithmetic.

## Safety and determinism

- Dictionaries preserve insertion order.
- Sets are never reordered by default. Complete and truncated representations follow
  native iteration order so the renderer does not replace observable runtime
  behavior with an invented presentation order. Set output is therefore not
  guaranteed to be stable across processes.
- Small sets may be inspected completely for aggregate type inference. Large sets
  under `"best_effort"` use a bounded native-order sample and are not scanned or
  sorted merely to manufacture reproducibility.
- Shared DAG nodes are not circular; only ancestors on the active path are treated
  as cycles.
- Exceptions from optional metadata or fallback inspection degrade to less specific
  representations where possible.
- Arbitrary properties are not invoked merely to discover object fields.
- String and bytes previews never emit raw newlines or malformed quote boundaries.
- Custom renderers retain their current trust model and may execute arbitrary user
  code.

## Extensions

Built-in optional renderers should produce semantic summaries rather than each
reimplementing allocation. Common helpers should cover:

- Shape and dtype.
- Column names and column types.
- Row or element count.
- Bounded representative values.
- Authoritative schema evidence.

Pandas, Polars, and Arrow table renderers should share the same conceptual table
summary logic. NumPy and Arrow arrays should share sequence-shape conventions.

Automatic activation remains compatible during the engine cutover. Lazy importing
of optional ecosystems is desirable but is a separable packaging change and should
not block the rendering rewrite.

## Testing strategy

### Contract tests

Add tests for:

- Every integer budget around important boundaries, including `0`.
- Negative budget and invalid allocation or inference policy validation.
- Complete output at exactly `len(full_representation)`.
- One character below and above the complete representation boundary.
- Singleton tuples and other syntax-sensitive built-ins.
- Quoted strings, backslashes, bytes escapes, Unicode, and control characters.
- Deeply nested tool-style results.
- Cheap scalar values retained alongside expensive containers.
- Homogeneous, heterogeneous, nullable, and empty sequences.
- Fixed record shapes and open mappings.
- `"off"`, `"exact"`, and `"best_effort"` inference behavior.
- Lists of records with required and optional keys.
- Optional key presence versus nullable field values.
- String and bytes previews with opportunistic original lengths.
- Native set iteration order without implicit sorting.
- Self-cycles, mutual cycles, and shared DAG children.
- Existing registered renderers and protocol methods.
- Nested `render_child()` and `render_attrs()` calls.

README examples should be executable tests so documentation cannot drift from actual
output again.

### Property tests

Use generated nested values and budgets to assert:

- `len(rendered) <= budget` for every nonnegative budget.
- Rendering terminates for bounded acyclic and cyclic structures.
- A complete supported representation is returned when the complete probe succeeds.
- Output contains no unescaped line-breaking control characters.
- Every selected representation corresponds to a valid refinement offered by its
  semantic node.

Strict textual prefix monotonicity is not required: adding budget may replace a type
stub with a differently shaped real value. The internal refinement rank should never
move toward less truthful or less informative information solely because the budget
increased.

### Characterization and differential tests

Run the legacy and new engines over a corpus of existing types to identify behavior
changes. Exact equality with legacy degraded output is not a goal. Differences should
be classified as:

- Required compatibility.
- Intentional improvement.
- Regression.

### Performance tests

Benchmark at least:

- Tiny scalar and small-container renders.
- Large flat sequences under a tiny budget.
- Deep nested mappings.
- Large lists of homogeneous records.
- Optional table and array types.
- Import time separately from render time.

Performance tests should verify bounded scaling with respect to inspection limits,
not only absolute wall-clock targets.

## Migration plan

1. **Freeze the contract**

   Add the new invariant, boundary, nested-result, and escaping tests. Correct README
   examples to reflect the intended contract.

2. **Isolate the legacy engine**

   Move the current implementation behind a private legacy entry point while leaving
   public imports unchanged.

3. **Build the new core path**

   Implement context, bounded writer, semantic nodes, and complete-render probing for
   primitives, strings, sequences, and mappings.

4. **Add schema inference**

   Implement sequence and mapping shapes, all three inference policies, bounded exact
   inspection, and deterministic best-effort sampling.

5. **Port structured Python objects**

   Move dataclasses, named tuples, `__dict__`, `__slots__`, and `render_attrs()` onto
   record nodes.

6. **Adapt customization hooks**

   Verify registry MRO behavior, protocol precedence, recursion, clipping, and cycles.

7. **Port optional extensions**

   Replace duplicated string assembly with shared semantic summaries and authoritative
   schemas.

8. **Cut over and remove legacy code**

   Switch the public facade after contract, property, characterization, and performance
   tests pass. Do not retain a permanent engine flag.

## Deferred API opportunities

The new internals should allow, but `0.2` will not publish:

```python
render(value, budget, schema=tool_output_schema)
render(value, budget, cost=token_cost)
render(value, budget, redact=rules)
```

The render context reserves internal schema support so a future public keyword does
not require another allocator redesign. A public keyword-only `schema=` argument is
the preferred direction once accepted schema formats and precedence rules have been
proven. A schema-bearing wrapper is not the primary planned API.

## Resolved design decisions

1. Sample counts and evidence sigils do not appear in output. The call-time
   `inference` policy defines whether aggregate type hints are disabled, exact within
   the work limit, or best-effort.
2. Optional record fields use `'key'?: Type`; `| None` independently describes a
   nullable value.
3. Initial internal inference limits are 256 exact elements, 32 sampled elements,
   1,024 inspected nodes, depth 3, and 32 merged fields. Large indexable sequences
   sample head, tail, and evenly spaced interior elements.
4. Truncated strings and bytes include original length opportunistically, after a
   useful preview fits.
5. Sets preserve native iteration order and make no cross-process stability promise.
6. Public and internal external-schema input remain deferred. A future keyword-only
   `schema=` argument is preferred over a wrapper.

The central architecture remains: bounded full rendering first, then outer
structural coverage, real values where affordable, schema as a compact fallback, and
policy-driven refinement of the remaining budget.
