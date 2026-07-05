CREATE CONSTRAINT attack_node_id IF NOT EXISTS
FOR (n:AttackNode)
REQUIRE n.id IS UNIQUE;

CREATE INDEX attack_node_kind IF NOT EXISTS
FOR (n:AttackNode)
ON (n.kind);

CREATE INDEX attack_node_high_value IF NOT EXISTS
FOR (n:AttackNode)
ON (n.high_value);

