# reprobate 🖨️

Budget-controlled repr for Python objects.

Renders any Python object into a string that fits within a character budget. Nested structures degrade gracefully: full values, then type stubs, then counts. Zero dependencies. Pluggable via a type registry and a `__budget_repr__` protocol.

## Features

- **Hard budget guarantee** -- output is always `<= budget` characters
- **Three-phase degradation** -- full render, then `name=<type(len)>` stubs, then `...N more` counts
- **Greedy and even policies** -- prioritize depth (first fields in detail) or breadth (all fields equally)
- **Uniform collapse** -- sequences of one repeated value render as the lossless product form `[0.0] * 97`
- **Bounded type inference** -- exact or best-effort aggregate hints such as `<list[str](200)>`, with complete sample values when space allows: `<list[{'id': int}](80): {'id': 0}, ...>`
- **Cycle detection** -- circular references render as `<...>` instead of stack overflows
- **Type registry** -- `@register(MyType)` for custom budget-aware renderers
- **Protocol method** -- `__budget_repr__(self, budget)` on any class
- **Optional extensions** -- typed table/array summaries for Arrow, NumPy, pandas, Polars, Pillow, and Pydantic (guarded imports, zero cost if absent)

## Install

```bash
pip install reprobate
```

Zero dependencies. Optional renderers activate automatically when their libraries are already installed (numpy, pandas, polars, pyarrow, Pillow, pydantic).

## Quick example

```python
import reprobate

reprobate.render({"name": "alice", "scores": [98, 87, 95, 72, 88]}, 60)
# "{'name': 'alice', 'scores': [98, 87, 95, 72, 88]}"

reprobate.render({"name": "alice", "scores": [98, 87, 95, 72, 88]}, 30)
# "{'name': 'alice', ...1 more}"

reprobate.render(list(range(1000)), 40)
# "[0, 1, 2, 3, 4, 5, 6, 7, 8, ...991 more]"
```

## Policies

```python
from dataclasses import dataclass

@dataclass
class Agent:
    desc: str = "A very long description that eats the budget"
    important_note: str = "critical info here"
    status: str = "running"
    config: dict = None
    history: list = None

agent = Agent()

# Greedy: first fields get full detail
reprobate.render(agent, 100, policy="greedy")
# "Agent(desc='A very long d...', important_note=<str(18)>, status=<str(7)>, config=None, history=None)"

# Even: all fields get comparable detail
reprobate.render(agent, 100, policy="even")
# "Agent(desc='A very l...', important_note='critical...', status='running', config=None, history=None)"
```

`"even"` uses max-min allocation among visible siblings. A bounded planning probe
identifies children whose complete representation needs less than their initial
share, then redistributes the unused characters among siblings that can still
improve. Opaque custom renderers are not called speculatively.

## Inference

Aggregate type hints are controlled independently from budget allocation:

```python
values = ["alice" * 30] * 1000

reprobate.render(values, 25)
# "<list[str](1000)>"

reprobate.render(values, 25, inference="exact")
# "<list(1000)>" -- too large for exhaustive inspection

reprobate.render(values, 25, inference="off")
# "[<str(150)>, ...999 more]"

result = {"users": ["alice" * 30] * 200, "cursor": "abc" * 100}
reprobate.render(result, 42)
# "<{'users': list[str], 'cursor': str}>"
```

`"best_effort"` is the default and uses bounded sampling for large containers.
`"exact"` emits aggregate types only after exhaustive bounded inspection; `"off"`
disables aggregate runtime inference. Type expressions are diagnostic hints, not
validation guarantees.

Small string-keyed mappings are treated as fixed records, so their compact schemas
retain the association between each literal key and its value type. Larger or
non-string-keyed mappings use `dict[key_type, value_type]` summaries instead.

## Custom renderers

Register a renderer for any type:

```python
@reprobate.register(MyType)
def render_my_type(obj: MyType, budget: int) -> str:
    return f"MyType({obj.key})"[:budget]
```

Or implement the protocol directly:

```python
class MyType:
    def __budget_repr__(self, budget: int) -> str:
        return f"MyType({self.key})"[:budget]
```

For renderers that recurse into child objects, use `render_child` (inherits policy and cycle detection) and `render_attrs` (standard `TypeName(key=val, ...)` pattern):

```python
from reprobate import register, render_child, render_attrs

@register(MyContainer)
def render_my_container(obj: MyContainer, budget: int) -> str:
    # render_child for recursive rendering
    inner = render_child(obj.value, budget - 10)
    return f"MyContainer({inner})"

@register(MyModel)
def render_my_model(obj: MyModel, budget: int) -> str:
    # render_attrs for the standard object pattern
    attrs = {"name": obj.name, "data": obj.data}
    return render_attrs(attrs, "MyModel", budget)
```

## Part of the agex stack

reprobate renders agent workspace objects for LLM context windows in [agex](https://github.com/ashenfad/agex), fitting complex types like DataFrames and nested structures within token budgets.

## Supported types

| Category | Types | Behavior |
|----------|-------|----------|
| Primitives | `None`, `bool`, `int`, `float` | `repr()`, or a `<int>`-style stub when it cannot fit |
| Strings | `str`, `bytes` | Quoted, escaped previews with `...`, plus length metadata when space allows: `<str(150): 'xxx...'>` |
| Containers | `list`, `tuple`, `set`, `frozenset` | Head items + `...N more`, schema summaries when items cannot fit |
| Dicts | `dict` | Key-value pairs + `...N more`; subclasses keep their own `repr` |
| Collections | `deque`, `defaultdict`, `Counter` | Type-aware wrappers (factory name, most-common order) |
| Structured | `dataclass`, `namedtuple` | Field-aware decomposition, respects `repr=False` |
| Objects | anything with `__dict__` or `__slots__` | Attribute decomposition, public attrs only |
| Optional | numpy, pandas, polars, pyarrow, Pillow, pydantic | Shape, dtype, typed-column schema, and bounded value summaries (auto-activates when installed) |

## Development

```bash
uv sync --extra dev
uv run pytest
```
