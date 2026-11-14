import type { Intent } from "../src/index.js";

// Compile-time alignment with examples/sample_intent.json and the Rust Intent struct.
const intent: Intent = {
  start: { class: "Product", alias: "product" },
  traverse: [
    {
      relationship: "has_part",
      direction: "out",
      to: { class: "Part", alias: "part" },
      min_hops: 1,
      max_hops: 1,
    },
    {
      relationship: "supplied_by",
      direction: "out",
      to: { class: "Supplier", alias: "supplier" },
    },
  ],
  filter: [
    { alias: "product", property: "sku", op: "eq", value: "SPX-100" },
  ],
  return: [
    {
      alias: "supplier",
      property: "name",
      aggregate: "collect",
      as_name: "supplier_name",
    },
  ],
  order_by: { alias: "supplier_name", descending: false },
  limit: 20,
  skip: 0,
  optional: false,
};

void intent;

// Correlated NOT EXISTS sub-pattern, as emitted for the anti-join example.
const antiJoinIntent: Intent = {
  start: { class: "Part", alias: "part" },
  filter: [
    {
      alias: "part",
      property: "category_slug",
      op: "eq",
      value: "fasteners-and-hardware",
    },
  ],
  not_exists: [
    {
      start: { class: "Usage", alias: "u" },
      traverse: [
        {
          relationship: "USES_ITEM",
          direction: "out",
          to: { class: "Part", alias: "part" },
        },
      ],
      filter: [
        { alias: "u", property: "match_method", op: "eq", value: "exact" },
      ],
    },
  ],
  return: [{ alias: "part", property: "name", as_name: "part" }],
  limit: 200,
};

void antiJoinIntent;
