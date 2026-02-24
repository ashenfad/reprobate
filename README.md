# reprobate 🖨️

Budget-controlled repr for Python objects.

Renders any Python object into a string that fits within a character budget. Nested structures degrade gracefully: full values, then type stubs, then counts. Zero dependencies. Pluggable via a type registry and a `__budget_repr__` protocol.

## Features

- **Hard budget guarantee** -- output is always `<= budget` characters
- **Three-phase degradation** -- full render, then `name=<type(len)>` stubs, then `...N more` counts
- **Greedy and even policies** -- prioritize depth (first fields in detail) or breadth (all fields equally)
- **Cycle detection** -- circular references render as `<...>` instead of stack overflows
- **Type registry** -- `@register(MyType)` for custom budget-aware renderers
- **Protocol method** -- `__budget_repr__(self, budget)` on any class
- **Optional extensions** -- numpy, pandas, pydantic renderers (guarded imports, zero cost if absent)

## Install

```bash
pip install reprobate              # core, zero dependencies
pip install reprobate[numpy]       # adds ndarray renderer
pip install reprobate[pandas]      # adds DataFrame/Series renderers
pip install reprobate[pydantic]    # adds BaseModel renderer
pip install reprobate[all]         # all optional renderers
```

## Quick example

```python
import reprobate

reprobate.render({"name": "alice", "scores": [98, 87, 95, 72, 88]}, 60)
# "{'name': 'alice', 'scores': [98, 87, 95, 72, 88]}"

reprobate.render({"name": "alice", "scores": [98, 87, 95, 72, 88]}, 30)
# "{'name': 'alice', ...1 more}"

reprobate.render(list(range(1000)), 40)
# "[0, 1, 2, 3, ...996 more]"
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

# Greedy: first fields get full detail
reprobate.render(agent, 100, policy="greedy")
# "Agent(desc='A very long description that eats the budget', important_note=<str(18)>, ...3 more)"

# Even: all fields get comparable detail
reprobate.render(agent, 100, policy="even")
# "Agent(desc='A very long...', important_note='critical info...', status='running', ...2 more)"
```

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

## Supported types

| Category | Types | Behavior |
|----------|-------|----------|
| Primitives | `None`, `bool`, `int`, `float` | `repr()`, truncated with `...` if needed |
| Strings | `str`, `bytes` | Quoted, truncated with `...` preserving quotes |
| Containers | `list`, `tuple`, `set`, `frozenset` | Head items + `...N more`, tail peek when budget allows |
| Dicts | `dict` | Key-value pairs + `...N more` |
| Collections | `deque`, `defaultdict`, `Counter` | Type-aware wrappers (factory name, most-common order) |
| Structured | `dataclass`, `namedtuple` | Field-aware decomposition, respects `repr=False` |
| Objects | anything with `__dict__` | Attribute decomposition, public attrs only |
| Optional | `ndarray`, `DataFrame`, `Series`, `BaseModel` | Shape/dtype + data peek (requires extras) |

## Development

```bash
uv sync --extra dev
uv run pytest
```
