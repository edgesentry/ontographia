// Manufacturing domain seed — BOM, site/line, lot traceability, suppliers
// ISA-95 inspired property graph for Neo4j 2025.06+ (Cypher 25)
//
//   cypher-shell -u neo4j -p <password> -f examples/neo4j/seed.cypher

CYPHER 25
CREATE CONSTRAINT product_sku IF NOT EXISTS
FOR (p:Product) REQUIRE p.sku IS UNIQUE;

CYPHER 25
CREATE CONSTRAINT part_number IF NOT EXISTS
FOR (p:Part) REQUIRE p.part_number IS UNIQUE;

CYPHER 25
CREATE CONSTRAINT lot_id IF NOT EXISTS
FOR (l:Lot) REQUIRE l.lot_id IS UNIQUE;

CYPHER 25
CREATE CONSTRAINT supplier_name IF NOT EXISTS
FOR (s:Supplier) REQUIRE s.name IS UNIQUE;

CYPHER 25
// Clear previous demo graph
MATCH (n)
WHERE n.sku = 'SPX-100'
   OR n.part_number IN ['P-MOT-001', 'P-HOU-002', 'P-DRV-010']
   OR n.lot_id IN ['LOT-2024-001', 'LOT-2024-002']
   OR n.name IN ['MikroMotors', 'FormTech', 'Nagoya Plant', 'Osaka Plant', 'Line-1', 'Line-2', 'SURFACE_SCRATCH']
DETACH DELETE n;

CYPHER 25
// --- BOM (multi-level) ---
// Product SPX-100 = SmartPump X
//   ├─ P-DRV-010 Drive Unit (sub-assembly)
//   │     └─ P-MOT-001 Motor
//   └─ P-HOU-002 Housing
MERGE (product:Product {sku: 'SPX-100', name: 'SmartPump X'})
MERGE (drive:Part {part_number: 'P-DRV-010', name: 'Drive Unit', lead_time_days: 14})
MERGE (motor:Part {part_number: 'P-MOT-001', name: 'Servo Motor', lead_time_days: 21})
MERGE (housing:Part {part_number: 'P-HOU-002', name: 'Aluminum Housing', lead_time_days: 10})
MERGE (product)-[:has_part]->(drive)
MERGE (product)-[:has_part]->(housing)
MERGE (drive)-[:has_sub_part]->(motor)
// Flattened BOM edge — leaf parts often linked directly for traceability queries
MERGE (product)-[:has_part]->(motor);

CYPHER 25
// --- Suppliers (tiered — supply chain risk) ---
MERGE (mikro:Supplier {name: 'MikroMotors', tier: 1, country: 'JP'})
MERGE (formtech:Supplier {name: 'FormTech', tier: 2, country: 'TW'})
MERGE (motor:Part {part_number: 'P-MOT-001'})
MERGE (housing:Part {part_number: 'P-HOU-002'})
MERGE (motor)-[:supplied_by]->(mikro)
MERGE (housing)-[:supplied_by]->(formtech);

CYPHER 25
// --- Site / Line (ISA-95) ---
MERGE (nagoya:Plant {name: 'Nagoya Plant', region: 'APAC'})
MERGE (osaka:Plant {name: 'Osaka Plant', region: 'APAC'})
MERGE (line1:Line {name: 'Line-1'})
MERGE (line2:Line {name: 'Line-2'})
MERGE (line1)-[:located_at]->(nagoya)
MERGE (line2)-[:located_at]->(osaka);

CYPHER 25
// --- Lot traceability ---
MERGE (defect:DefectType {code: 'SURFACE_SCRATCH', description: 'Surface scratch on housing'})
MERGE (lot1:Lot {lot_id: 'LOT-2024-001', quantity: 100, status: 'released'})
MERGE (lot2:Lot {lot_id: 'LOT-2024-002', quantity: 50, status: 'quarantine'})
MERGE (line1:Line {name: 'Line-1'})
MERGE (line2:Line {name: 'Line-2'})
MERGE (motor:Part {part_number: 'P-MOT-001'})
MERGE (housing:Part {part_number: 'P-HOU-002'})
MERGE (lot1)-[:produced_on]->(line1)
MERGE (lot2)-[:produced_on]->(line2)
MERGE (lot1)-[:contains_part]->(motor)
MERGE (lot1)-[:contains_part]->(housing)
MERGE (lot2)-[:contains_part]->(housing)
MERGE (lot2)-[:has_defect]->(defect);
