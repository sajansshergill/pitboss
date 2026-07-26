// Bonus-abuse rings: three or more "distinct" players who share a single
// payment instrument AND all claimed the same promotion. This is the classic
// signup-bonus farm — accounts that are separate on paper, one entity in fact.
MATCH (p:Player)-[:USES_CARD]->(c:PaymentInstrument)
MATCH (p)-[:CLAIMED]->(pr:Promotion)
WITH c, pr, collect(DISTINCT p.id) AS players, count(DISTINCT p) AS n
WHERE n >= 3
RETURN c.id        AS shared_card,
       pr.id       AS promotion,
       n           AS ring_size,
       players
ORDER BY ring_size DESC;