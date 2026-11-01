CYPHER 25
MATCH (product:Product)-[:has_part]->(part:Part)-[:supplied_by]->(supplier:Supplier)
FILTER product.sku = $param_0
RETURN supplier.name AS supplier_name
LIMIT 20
