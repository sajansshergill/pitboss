// Referral farming: referral chains whose members also share a fingerprint —
// i.e. someone "referring" accounts that are really themselves to harvest
// referral rewards. Walks the REFERRED_BY chain and checks for a shared device
// signal across the chain.
MATCH path = (head:Player)-[:REFERRED_BY*2..]->(tail:Player)
WITH head, tail, nodes(path) AS chain
MATCH (a:Player)-[:HAS_FINGERPRINT]->(f:Fingerprint)<-[:HAS_FINGERPRINT]-(b:Player)
WHERE a IN chain AND b IN chain AND a.id < b.id
RETURN [n IN chain | n.id] AS referral_chain,
       f.id                AS shared_fingerprint,
       length(path) + 1    AS chain_length
ORDER BY chain_length DESC;