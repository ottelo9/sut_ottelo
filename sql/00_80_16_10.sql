-- Making sense of the data with duckdb
-- duckdb :memory: -f sql/00_80_16_10.sql

-- Install the JSON extension (only needed once per database)
INSTALL json;

-- Load the JSON extension
LOAD json;

CREATE TEMPORARY TABLE rx_split AS
WITH SplitCTE AS (
    SELECT
        *,
        STRING_SPLIT(tx, ' ') AS tx_parts,
        STRING_SPLIT(rx, ' ') AS rx_parts
    FROM read_ndjson_auto('./data/**/*.ndjson')
    WHERE rx LIKE '00 80 16 10 %'
)
SELECT * FROM SplitCTE;

/*Trying to figure out when byte 17 is E3*/
-- I now thinkg byte 16 shows MAX temperature, and 17 shows average. 
-- I think the MAX calculation ignores outlandish temperatures (like 433°c) but AVG doesn't
-- Additionally 433 doesn't fit in a byte, so perhaps that's why MAX ignores it.
-- So the disconnected TH003 showed very high, 433 to get average E3.
/*
SELECT DISTINCT intent, rx_parts[17] FROM rx_split WHERE rx_parts[17] = 'E3';
SELECT DISTINCT intent, rx_parts[17] FROM rx_split WHERE rx_parts[17] != 'E3';
*/

/*
SELECT DISTINCT rx_parts[5] AS 'CONTEXT' FROM rx_split;
SELECT DISTINCT rx_parts[6] AS 'STATE/MODE' FROM rx_split;

SELECT * FROM rx_split where rx_parts[5] = '35';
*/

/*
SELECT DISTINCT intent, rx_parts[7], rx_parts[8], rx_parts[9] FROM rx_split ORDER BY rx_split.t;
*/

SELECT tx_parts, rx_parts FROM rx_split ORDER BY t DESC LIMIT 10;

SELECT DISTINCT rx_parts[19] FROM rx_split;
SELECT DISTINCT rx_parts[20] FROM rx_split;
SELECT DISTINCT rx_parts[21],rx_parts[22],rx_parts[23],rx_parts[24],rx_parts[25] FROM rx_split;

SELECT
    intent,
    /*
    rx_parts[1] AS 'Delimiter', -- 0x00
    rx_parts[2] AS 'Header | Seq'
    */
    rx_parts[3] AS 'Length',
    /*
    rx_parts[4] AS 'Type',
    rx_parts[5] AS 'Context',
    rx_parts[6] AS 'State/Mode (?)',
    rx_parts[7] AS '?',
    rx_parts[8] AS '?',
    rx_parts[9] AS '?',
    */
    (CAST('0x' || rx_parts[11] AS INTEGER) << 8) | CAST('0x' || rx_parts[10] AS INTEGER) AS 'Pack Voltage (mV)',
    rx_parts[12] AS 'Current A', -- uint16_t Discharge current?
    rx_parts[13] AS '?',         --    
    rx_parts[14] AS 'Current B', -- uint16_t Charge current?
    rx_parts[15] AS '?',         --
    rx_parts[16] AS 'TH003/TH004 MAX',
    rx_parts[17] AS 'TH003/TH004 AVG',
    rx_parts[18] AS 'TH002',
    rx_parts[19] AS 'STATUS A (?)',
    rx_parts[20] AS 'STATUS B (?)',
    rx_parts
FROM rx_split WHERE intent = 'Voltage 003'; --'10v on CN001'
