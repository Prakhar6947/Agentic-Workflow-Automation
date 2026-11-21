import ast
import operator
from typing import Any

_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def evaluate_condition(expr: str | None, ctx: dict[str, Any]) -> bool:
    """
    Safely evaluates condition expressions using Python AST.
    Supported variables: alert_count, critical_count, tickets_created_count, down_links.
    No eval/exec; rejects arbitrary code or function calls.
    """
    if not expr or expr.strip().lower() in ("always", "true", "1"):
        return True
    if expr.strip().lower() in ("never", "false", "0"):
        return False

    env = {
        "alert_count": ctx.get("alert_count", 0),
        "critical_count": ctx.get("critical_count", 0),
        "tickets_created_count": ctx.get("tickets_created_count", 0),
        "down_links": ctx.get("down_links", 0),
    }

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return env.get(node.id, 0)
        if isinstance(node, ast.BoolOp):
            vals = [_eval(v) for v in node.values]
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not _eval(node.operand)
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = _eval(comp)
                op_type = type(op)
                if op_type not in _CMP_OPS:
                    raise ValueError(f"Unsupported comparator operator: {op_type.__name__}")
                if not _CMP_OPS[op_type](left, right):
                    return False
                left = right
            return True
        raise ValueError(f"Unsupported condition node: {type(node).__name__}")

    try:
        parsed = ast.parse(expr.strip(), mode="eval")
        return bool(_eval(parsed.body))
    except Exception as exc:
        raise ValueError(f"Invalid condition expression '{expr}': {exc}") from exc
