#!/bin/bash

set -euo pipefail

# Database connection parameters
DB_USER="dba"
DB_NAME="testdb"

# Create vector table and insert test data
csql -u $DB_USER $DB_NAME -S -c "
    DROP TABLE IF EXISTS vector_table;
    CREATE TABLE vector_table (
        id INT PRIMARY KEY,
        vec VECTOR
    );
    
    INSERT INTO vector_table VALUES 
    (1, '[2, 3, 4]'),
    (2, '[3, 4, 5]'),
    (3, '[4, 5, 6]'),
    (4, '[5, 6, 7]');"

echo "Vector table created and populated."

# Test L2_DISTANCE with direct vectors
echo -e "\nTesting L2_DISTANCE with direct vectors:"
csql -u $DB_USER $DB_NAME -S -c "SELECT L2_DISTANCE('[1, 2, 3]', '[2, 3, 4]') AS distance FROM dual;"

# Test L2_DISTANCE with stored vectors
echo -e "\nTesting L2_DISTANCE with stored vectors:"
csql -u $DB_USER $DB_NAME -S -c "
    SELECT 
        id,
        vec,
        L2_DISTANCE('[1, 2, 3]', vec) AS distance 
    FROM vector_table 
    ORDER BY distance;"

csql -u $DB_USER $DB_NAME -S -c "
    SELECT 
        id,
        vec,
        L2_DISTANCE(vec, '[1, 2, 3]') AS distance 
    FROM vector_table 
    ORDER BY distance;"

csql -u $DB_USER $DB_NAME -S -c "
    SELECT 
        id,
        vec,
        L2_DISTANCE(vec, vec) AS distance 
    FROM vector_table 
    ORDER BY distance;"

csql -u $DB_USER $DB_NAME -S -c "
    SELECT 
        id,
        vec,
        L2_DISTANCE(null, vec) AS distance 
    FROM vector_table 
    ORDER BY distance;"

csql -u $DB_USER $DB_NAME -S -c "
    SELECT 
        id,
        vec,
        L2_DISTANCE('[1, 2, 3]', null) AS distance,
        L2_DISTANCE(null, '[1, 2, 3]') AS distance2
    FROM vector_table 
    ORDER BY distance;"

# Optional: Test with different vector dimensions
echo -e "\nTesting with different vector:"
csql -u $DB_USER $DB_NAME -S -c "SELECT L2_DISTANCE('[0, 0, 0]', vec) AS distance FROM vector_table ORDER BY distance;"
