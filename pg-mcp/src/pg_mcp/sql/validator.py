"""SQL security validator using SQLGlot AST."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from pg_mcp.errors import ValidationError

# Root node types allowed (read-only queries)
ALLOWED_ROOT_TYPES = (
    exp.Select,
    exp.Union,
    exp.Intersect,
    exp.Except,
    exp.With,
)

# Statement types that are always blocked (including when nested)
BLOCKED_STATEMENT_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Grant,
    exp.Set,
    exp.Command,
)

# Default blocked functions (30+)
DEFAULT_BLOCKED_FUNCTIONS = frozenset({
    # System management / DoS
    "pg_sleep",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "pg_rotate_logfile",
    # File / network I/O
    "pg_read_file",
    "pg_write_file",
    "pg_read_binary_file",
    "pg_stat_file",
    "lo_export",
    "lo_import",
    "lo_unlink",
    "lo_create",
    # Advisory locks
    "pg_advisory_lock",
    "pg_advisory_lock_shared",
    "pg_try_advisory_lock",
    "pg_try_advisory_lock_shared",
    "pg_advisory_xact_lock",
    "pg_advisory_xact_lock_shared",
    # Replication
    "pg_create_logical_replication_slot",
    "pg_create_physical_replication_slot",
    "pg_drop_replication_slot",
    "pg_logical_slot_get_changes",
    "pg_logical_slot_peek_changes",
    # Config / session
    "set_config",
    "pg_notify",
    "pg_listening_channels",
    # Extensions / external
    "dblink",
    "dblink_exec",
    "dblink_connect",
    "dblink_disconnect",
    "dblink_send_query",
    "dblink_get_result",
    # Backup
    "pg_start_backup",
    "pg_stop_backup",
    "pg_switch_wal",
    "pg_create_restore_point",
})


class SQLValidator:
    """Validates SQL for read-only safety using SQLGlot AST."""

    def __init__(
        self,
        max_length: int = 10000,
        blocked_functions: set[str] | frozenset[str] | list[str] | None = None,
        allow_explain_analyze: bool = False,
        allow_explain: bool = False,
        table_whitelist: list[str] | None = None,
        table_blacklist: list[str] | None = None,
    ):
        self.max_length = max_length
        self.blocked_functions = (
            DEFAULT_BLOCKED_FUNCTIONS
            | frozenset(blocked_functions or [])
        )
        self.allow_explain_analyze = allow_explain_analyze
        self.allow_explain = allow_explain
        self.table_whitelist = [t.lower() for t in table_whitelist] if table_whitelist else None
        self.table_blacklist = [t.lower() for t in table_blacklist] if table_blacklist else None

    def validate(self, sql: str) -> exp.Expression:
        """
        Validate SQL and return the AST if valid.
        Raises ValidationError on failure.
        """
        if sql is None:
            raise ValidationError("INVALID_INPUT", "SQL cannot be None")

        sql_str = sql.strip() if isinstance(sql, str) else ""
        if not sql_str:
            raise ValidationError("INVALID_INPUT", "SQL cannot be empty")

        # Check length before strip to prevent DoS (reject oversized input)
        if len(sql) > self.max_length:
            raise ValidationError(
                "QUERY_TOO_LONG",
                f"SQL exceeds {self.max_length} characters",
            )

        try:
            statements = sqlglot.parse(sql_str, dialect="postgres")
        except sqlglot.errors.ParseError as e:
            raise ValidationError("PARSE_ERROR", f"Invalid SQL syntax: {e}") from e

        if not statements:
            raise ValidationError("PARSE_ERROR", "No statement parsed")

        if len(statements) != 1:
            raise ValidationError(
                "MULTIPLE_STATEMENTS",
                f"Expected 1 statement, got {len(statements)}",
            )

        ast = statements[0]

        # EXPLAIN handling (exp.Explain may not exist in all sqlglot versions)
        explain_type = getattr(exp, "Explain", None)
        is_explain = explain_type and isinstance(ast, explain_type)
        if not is_explain and isinstance(ast, exp.Command):
            cmd = str((ast.this or "") if hasattr(ast, "this") else "").upper()
            is_explain = cmd == "EXPLAIN"
        if is_explain:
            self._check_explain(ast)
            return ast

        root = ast
        # Handle WITH (CTE) - validate the body
        if isinstance(ast, exp.With):
            body = ast.this
            if body is None:
                raise ValidationError(
                    "DISALLOWED_STATEMENT",
                    "WITH clause has no body",
                )
            ast = body

        # Root node whitelist
        if not isinstance(ast, ALLOWED_ROOT_TYPES):
            raise ValidationError(
                "DISALLOWED_STATEMENT",
                f"Only SELECT statements are allowed, got {type(ast).__name__}",
            )

        # SELECT INTO check (walk full tree including CTEs)
        self._check_select_into(root)

        # Walk full AST (including CTE bodies) for blocked nodes and functions
        for node in root.walk():
            if isinstance(node, BLOCKED_STATEMENT_TYPES):
                raise ValidationError(
                    "DISALLOWED_STATEMENT",
                    f"Statement type {type(node).__name__} is not allowed",
                )
            # Blocked functions (schema-qualified matching by basename)
            if isinstance(node, (exp.Anonymous, exp.Func)):
                func_name = self._get_func_name(node)
                if func_name and func_name.lower() in self.blocked_functions:
                    raise ValidationError(
                        "BLOCKED_FUNCTION",
                        f"Function '{func_name}' is not allowed",
                    )

        # Table access validation (whitelist / blacklist)
        if self.table_whitelist is not None or self.table_blacklist is not None:
            self._check_table_access(root)

        return statements[0]

    def _get_func_name(self, node: exp.Expression) -> str:
        """Extract function name from Func/Anonymous node (schema-qualified → basename)."""
        # Simple case: node.name (e.g. pg_sleep)
        if hasattr(node, "name") and node.name:
            return node.name
        # Schema-qualified: this might be Dot(schema, func) - we want the func (right side)
        if hasattr(node, "this"):
            this = node.this
            if isinstance(this, exp.Identifier):
                return this.name or ""
            if isinstance(this, exp.Dot):
                right = getattr(this, "expression", None) or getattr(this, "that", None)
                if isinstance(right, exp.Identifier):
                    return right.name or ""
                if hasattr(right, "name"):
                    return right.name or ""
        return ""

    def _check_select_into(self, ast: exp.Expression) -> None:
        """Reject SELECT INTO."""
        for node in ast.walk():
            if isinstance(node, exp.Into):
                raise ValidationError("SELECT_INTO", "SELECT INTO is not allowed")

    def _check_explain(self, ast: exp.Expression) -> None:
        """Check EXPLAIN permissions: block by default, allow with allow_explain=True."""
        sql_upper = (ast.sql(dialect="postgres") or "").upper()
        has_analyze = "ANALYZE" in sql_upper

        if has_analyze:
            if not self.allow_explain_analyze:
                raise ValidationError(
                    "EXPLAIN_ANALYZE",
                    "EXPLAIN ANALYZE is not allowed by default",
                )
        else:
            if not self.allow_explain:
                raise ValidationError(
                    "EXPLAIN_BLOCKED",
                    "EXPLAIN is not allowed; set allow_explain=True to enable",
                )

    def _check_table_access(self, ast: exp.Expression) -> None:
        """Validate table references against whitelist and blacklist."""
        for node in ast.walk():
            if not isinstance(node, exp.Table) or not node.name:
                continue

            table_name = node.name.lower()
            schema_name = (node.db or "").lower()
            full_name = f"{schema_name}.{table_name}" if schema_name else table_name
            display_name = full_name

            if self.table_whitelist is not None:
                allowed = any(
                    (
                        entry == full_name
                        if "." in entry
                        else entry == table_name
                    )
                    for entry in self.table_whitelist
                )
                if not allowed:
                    raise ValidationError(
                        "TABLE_NOT_ALLOWED",
                        f"Table '{display_name}' is not in the allowed list",
                    )

            if self.table_blacklist is not None:
                blocked = any(
                    (
                        entry == full_name
                        if "." in entry
                        else entry == table_name
                    )
                    for entry in self.table_blacklist
                )
                if blocked:
                    raise ValidationError(
                        "TABLE_BLOCKED",
                        f"Table '{display_name}' is blocked",
                    )
