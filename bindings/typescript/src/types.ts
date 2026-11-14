/**
 * Intent JSON types aligned with `ontographia_core::intent`.
 * Unknown keys are rejected by the Rust core (`deny_unknown_fields`), not by these types.
 */

/** JSON value shape used for filter literals and bound parameters. */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

/** Dialects implemented by `ontographia-core`. Other strings fail at build time. */
export type Dialect = "cypher25" | "cypher5" | "gql";

export type Direction = "out" | "in" | "both";

export type FilterOp =
  | "eq"
  | "neq"
  | "lt"
  | "lte"
  | "gt"
  | "gte"
  | "in"
  | "contains";

export type AggregateFn = "count" | "collect";

export interface NodeRef {
  class: string;
  alias: string;
}

export interface TraverseStep {
  relationship: string;
  direction: Direction;
  to: NodeRef;
  min_hops?: number;
  max_hops?: number;
}

export interface FilterExpr {
  alias: string;
  property: string;
  op: FilterOp;
  value: JsonValue;
}

/**
 * Correlated `NOT EXISTS { MATCH … }` sub-pattern. At least one alias must be
 * bound in the main pattern (correlation), and at least one traverse step is
 * required. Sub-pattern-only aliases cannot be used in `return`, `order_by`, or
 * the main `filter`.
 */
export interface SubPattern {
  start: NodeRef;
  traverse?: TraverseStep[];
  filter?: FilterExpr[];
}

export interface ReturnItem {
  alias: string;
  property?: string;
  aggregate?: AggregateFn;
  as_name?: string;
}

export interface OrderBy {
  alias: string;
  property?: string;
  descending?: boolean;
}

export interface Intent {
  start: NodeRef;
  traverse?: TraverseStep[];
  filter?: FilterExpr[];
  not_exists?: SubPattern[];
  return: ReturnItem[];
  order_by?: OrderBy;
  limit?: number;
  skip?: number;
  optional?: boolean;
}

/** Intent object or the same document already encoded as JSON text. */
export type IntentInput = string | Intent;

/** Successful `Engine.build` result. Filter literals live in `params`, never in `query`. */
export interface BuildResult {
  query: string;
  params: Record<string, JsonValue>;
}
