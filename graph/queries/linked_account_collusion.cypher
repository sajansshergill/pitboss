// Linked-account collusion: players who share BOTH a device and a session
// fingerprint. Sharing one signal can be a household or shared PC; sharing both
// is a strong indicator the accounts are operated by a single actor.
MATCH (p1:Player)-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(p2:Player)
WHERE p1.id < p2.id
MATCH (p1)-[:HAS_FINGERPRINT]->(f:Fingerprint)<-[:HAS_FINGERPRINT]-(p2)
RETURN d.id        AS shared_device,
       f.id        AS shared_fingerprint,
       collect(DISTINCT p1.id + ' <-> ' + p2.id) AS linked_pairs,
       count(*)    AS pair_count
ORDER BY pair_count DESC;