from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SelectSpec(BaseModel):
    column: str
    alias: str | None = None


class AggregateSpec(BaseModel):
    function: Literal["COUNT", "SUM", "AVG", "MIN", "MAX"]
    column: str
    alias: str


class JoinSpec(BaseModel):
    left: str
    right: str
    join_type: Literal["INNER"] = "INNER"


class FilterSpec(BaseModel):
    column: str
    operator: Literal["=", "<>", ">", ">=", "<", "<=", "IN", "BETWEEN", "LIKE"]
    value: Any


class OrderBySpec(BaseModel):
    expression: str
    direction: Literal["ASC", "DESC"] = "ASC"


class QueryPlan(BaseModel):
    base_table: str
    selects: list[SelectSpec] = Field(default_factory=list)
    aggregates: list[AggregateSpec] = Field(default_factory=list)
    joins: list[JoinSpec] = Field(default_factory=list)
    filters: list[FilterSpec] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    order_by: list[OrderBySpec] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=1000)

    @field_validator("group_by")
    @classmethod
    def remove_duplicate_group_by(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_shape(self) -> "QueryPlan":
        if not self.selects and not self.aggregates:
            raise ValueError("query plan must include at least one select or aggregate")
        return self


class QueryResult(BaseModel):
    sql: str
    rows: list[dict[str, Any]]
