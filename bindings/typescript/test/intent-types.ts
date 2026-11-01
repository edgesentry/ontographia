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
