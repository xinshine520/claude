"""Tests for SQL validator (Phase 2)."""

from __future__ import annotations

import pytest

from pg_mcp.errors import ValidationError
from pg_mcp.sql.validator import SQLValidator, DEFAULT_BLOCKED_FUNCTIONS


@pytest.fixture
def validator():
    return SQLValidator(max_length=10000)


# --- Design §10 test matrix ---


def test_valid_simple_select(validator):
    """Valid: SELECT * FROM users"""
    validator.validate("SELECT * FROM users")


def test_valid_cte(validator):
    """Valid: WITH t AS (SELECT 1) SELECT * FROM t"""
    validator.validate("WITH t AS (SELECT 1) SELECT * FROM t")


def test_valid_union(validator):
    """Valid: SELECT 1 UNION SELECT 2"""
    validator.validate("SELECT 1 UNION SELECT 2")


def test_multiple_statements_rejected(validator):
    """Reject: SELECT 1; DROP TABLE x"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT 1; DROP TABLE x")
    assert exc.value.code == "MULTIPLE_STATEMENTS"


def test_insert_rejected(validator):
    """Reject: INSERT INTO t VALUES (1)"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("INSERT INTO t VALUES (1)")
    assert exc.value.code == "DISALLOWED_STATEMENT"


def test_update_rejected(validator):
    """Reject: UPDATE t SET a=1"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("UPDATE t SET a = 1")
    assert exc.value.code == "DISALLOWED_STATEMENT"


def test_delete_rejected(validator):
    """Reject: DELETE FROM t"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("DELETE FROM t")
    assert exc.value.code == "DISALLOWED_STATEMENT"


def test_create_rejected(validator):
    """Reject: CREATE TABLE t (a int)"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("CREATE TABLE t (a int)")
    assert exc.value.code == "DISALLOWED_STATEMENT"


def test_select_into_rejected(validator):
    """Reject: SELECT * INTO t FROM users"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT * INTO t FROM users")
    assert exc.value.code == "SELECT_INTO"


def test_cte_with_insert_rejected(validator):
    """Reject: WITH t AS (SELECT 1) INSERT INTO x SELECT * FROM t"""
    with pytest.raises(ValidationError) as exc:
        validator.validate(
            "WITH t AS (SELECT 1) INSERT INTO x SELECT * FROM t"
        )
    assert exc.value.code == "DISALLOWED_STATEMENT"


def test_pg_sleep_rejected(validator):
    """Reject: SELECT pg_sleep(100)"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT pg_sleep(100)")
    assert exc.value.code == "BLOCKED_FUNCTION"


def test_dblink_rejected(validator):
    """Reject: SELECT * FROM dblink('...')"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT * FROM dblink('host=localhost dbname=mydb', 'SELECT 1') x")
    assert exc.value.code == "BLOCKED_FUNCTION"


def test_lo_export_rejected(validator):
    """Reject: SELECT lo_export(12345, '/tmp/x')"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT lo_export(12345, '/tmp/x')")
    assert exc.value.code == "BLOCKED_FUNCTION"


def test_explain_allowed(validator):
    """Valid: EXPLAIN SELECT 1"""
    validator.validate("EXPLAIN SELECT 1")


def test_explain_analyze_rejected(validator):
    """Reject: EXPLAIN ANALYZE SELECT 1"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("EXPLAIN ANALYZE SELECT 1")
    assert exc.value.code == "EXPLAIN_ANALYZE"


def test_explain_analyze_allowed_when_enabled(validator):
    """Valid when allow_explain_analyze=True"""
    v = SQLValidator(allow_explain_analyze=True)
    v.validate("EXPLAIN ANALYZE SELECT 1")


def test_query_too_long(validator):
    """Reject: SQL exceeding max_length"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT 1" + " " * 10000)
    assert exc.value.code == "QUERY_TOO_LONG"


def test_copy_rejected(validator):
    """Reject: COPY t TO '/tmp/x'"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("COPY t TO '/tmp/x'")
    assert exc.value.code == "DISALLOWED_STATEMENT"


def test_set_rejected(validator):
    """Reject: SET statement_timeout = 0"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SET statement_timeout = 0")
    assert exc.value.code == "DISALLOWED_STATEMENT"


def test_advisory_lock_rejected(validator):
    """Reject: SELECT pg_advisory_lock(1)"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT pg_advisory_lock(1)")
    assert exc.value.code == "BLOCKED_FUNCTION"


def test_pg_notify_rejected(validator):
    """Reject: SELECT pg_notify('ch', 'msg')"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT pg_notify('ch', 'msg')")
    assert exc.value.code == "BLOCKED_FUNCTION"


def test_replication_rejected(validator):
    """Reject: pg_create_logical_replication_slot"""
    with pytest.raises(ValidationError) as exc:
        validator.validate(
            "SELECT pg_create_logical_replication_slot('s', 'p')"
        )
    assert exc.value.code == "BLOCKED_FUNCTION"


def test_file_read_rejected(validator):
    """Reject: SELECT pg_read_file('/etc/passwd')"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT pg_read_file('/etc/passwd')")
    assert exc.value.code == "BLOCKED_FUNCTION"


# --- Boundary cases from impl plan ---


def test_nested_dangerous_function_rejected(validator):
    """Reject: SELECT * FROM (SELECT pg_sleep(1)) t"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT * FROM (SELECT pg_sleep(1)) t")
    assert exc.value.code == "BLOCKED_FUNCTION"


def test_cte_body_insert_rejected(validator):
    """Reject: WITH t AS (INSERT INTO x VALUES(1) RETURNING *) SELECT * FROM t"""
    with pytest.raises(ValidationError) as exc:
        validator.validate(
            "WITH t AS (INSERT INTO x VALUES(1) RETURNING *) SELECT * FROM t"
        )
    assert exc.value.code == "DISALLOWED_STATEMENT"


def test_function_mixed_case_rejected(validator):
    """Reject: SELECT PG_SLEEP(1) - case insensitive matching"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT PG_SLEEP(1)")
    assert exc.value.code == "BLOCKED_FUNCTION"


def test_comment_with_dangerous_content(validator):
    """Comment contains pg_sleep - only actual AST nodes are checked, not comments"""
    # The comment does not add pg_sleep to the AST, so this passes
    validator.validate("SELECT 1 -- pg_sleep(100)")


def test_empty_string_rejected(validator):
    """Reject: empty string"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("")
    assert exc.value.code == "INVALID_INPUT"


def test_none_rejected(validator):
    """Reject: None input"""
    with pytest.raises(ValidationError) as exc:
        validator.validate(None)  # type: ignore[arg-type]
    assert exc.value.code == "INVALID_INPUT"


def test_exactly_max_length_allowed(validator):
    """Exactly 10000 chars is allowed"""
    sql = "SELECT 1" + " " * 9992  # 8 + 9992 = 10000
    assert len(sql) == 10000
    validator.validate(sql)


def test_10001_chars_rejected(validator):
    """10001 chars is rejected"""
    sql = "SELECT 1" + " " * 9993  # 8 + 9993 = 10001
    with pytest.raises(ValidationError) as exc:
        validator.validate(sql)
    assert exc.value.code == "QUERY_TOO_LONG"


def test_whitespace_only_rejected(validator):
    """Reject: whitespace only"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("   \n\t  ")
    assert exc.value.code == "INVALID_INPUT"


def test_valid_intersect(validator):
    """Valid: SELECT 1 INTERSECT SELECT 2"""
    validator.validate("SELECT 1 INTERSECT SELECT 2")


def test_valid_except(validator):
    """Valid: SELECT 1 EXCEPT SELECT 2"""
    validator.validate("SELECT 1 EXCEPT SELECT 2")


def test_default_blocked_functions_count():
    """DEFAULT_BLOCKED_FUNCTIONS has 30+ entries"""
    assert len(DEFAULT_BLOCKED_FUNCTIONS) >= 30


def test_schema_qualified_pg_sleep_rejected(validator):
    """Reject: SELECT public.pg_sleep(1) - schema-qualified"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELECT public.pg_sleep(1)")
    assert exc.value.code == "BLOCKED_FUNCTION"


def test_parse_error_on_invalid_sql(validator):
    """Invalid SQL syntax raises PARSE_ERROR"""
    with pytest.raises(ValidationError) as exc:
        validator.validate("SELEC FRM x")
    assert exc.value.code == "PARSE_ERROR"
