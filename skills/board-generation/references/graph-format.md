# Graph format

Use `diagram` for a linear flow: at most 10 nonempty labels, each at most 60 characters.
For branches, groups or feedback, use `graph` and leave `diagram` empty.

```json
{
  "groups": [{"id": "user", "label": "User"}, {"id": "agent", "label": "Agent"}],
  "nodes": [
    {"id": "request", "label": "Describe task", "detail": "Goal and selected material", "group": "user", "row": 0, "kind": "process"},
    {"id": "draft", "label": "Propose result", "detail": "Not automatically saved", "group": "agent", "row": 1, "kind": "process"}
  ],
  "edges": [{"from": "request", "to": "draft", "label": "", "kind": "flow"}]
}
```

- 1-5 groups, 2-32 nodes and 1-60 edges. IDs start with a letter and use letters, digits, `_` or `-`.
- Each node belongs to an existing group; row is an integer from 0 to 11. At most one node per group per row.
- Node label: 36 characters maximum; detail: 72. Kinds: `process`, `decision`, `note`.
- Edge label: 24 characters maximum. Kinds: `flow`, `reference`, `feedback`.
- Edges connect different existing nodes. Every node has a relationship; every group has a node.
- Use the user's language for labels. Show meaningful roles and decisions, not filler nodes.
- Return data only, without scripts, coordinates or fabricated source citations.
