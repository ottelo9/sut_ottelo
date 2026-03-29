-- Charger/Battery telemetry analysis
-- Usage: duckdb :memory: -f sql/charger_telemetry.sql

INSTALL json;
LOAD json;

CREATE TEMPORARY TABLE rx_split AS
WITH SplitCTE AS (
    SELECT
        *,
        STRING_SPLIT(tx, ' ') AS tx_parts,
        STRING_SPLIT(rx, ' ') AS rx_parts
    FROM read_ndjson_auto('./data/**/*.ndjson')
    WHERE rx LIKE '00 __ 16 10 %'
)
SELECT * FROM SplitCTE;

SELECT
    intent,
    rx_parts[3] AS 'Length',
    (CAST('0x' || rx_parts[11] AS INTEGER) << 8) | CAST('0x' || rx_parts[10] AS INTEGER) AS 'Pack Voltage (mV)',
    rx_parts[12] AS 'Current A',
    rx_parts[13] AS '?',
    rx_parts[14] AS 'Current B',
    rx_parts[15] AS '?',
    rx_parts[16] AS 'TH003/TH004 MAX',
    rx_parts[17] AS 'TH003/TH004 AVG',
    rx_parts[18] AS 'TH002',
    rx_parts[19] AS 'STATUS A (?)',
    rx_parts[20] AS 'STATUS B (?)',
FROM rx_split
ORDER BY t;
