"""Schema data models for database metadata."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ColumnInfo(BaseModel):
    """Column metadata."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: str
    nullable: bool
    is_primary_key: bool = False
    default: str | None = None
    comment: str | None = None


class ForeignKeyInfo(BaseModel):
    """Foreign key constraint info."""

    model_config = ConfigDict(populate_by_name=True)

    constraint_name: str
    source_column: str
    target_table: str
    target_column: str


class IndexInfo(BaseModel):
    """Index metadata."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    columns: list[str] = Field(default_factory=list)
    index_type: str = "btree"
    is_unique: bool = False


class TableInfo(BaseModel):
    """Table metadata."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str
    table_name: str
    table_type: str  # "table" | "view"
    columns: list[ColumnInfo] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = Field(default_factory=list)
    indexes: list[IndexInfo] = Field(default_factory=list)
    comment: str | None = None
    view_definition: str | None = None
    row_estimate: int | None = None


class EnumTypeInfo(BaseModel):
    """Enum type metadata."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str
    type_name: str
    values: list[str] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    """Full database schema metadata."""

    model_config = ConfigDict(populate_by_name=True)

    database_name: str
    schemas: list[str] = Field(default_factory=list)
    tables: list[TableInfo] = Field(default_factory=list)
    enum_types: list[EnumTypeInfo] = Field(default_factory=list)
    collected_at: str  # ISO 8601 timestamp
