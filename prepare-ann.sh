#!/bin/bash

export ANN_BENCHMARKS_CUB_USER=ann
export ANN_BENCHMARKS_CUB_PASSWORD=ann
export ANN_BENCHMARKS_CUB_DBNAME=ann
# export ANN_BENCHMARKS_CUB_HOST=192.168.4.2
export ANN_BENCHMARKS_CUB_HOST=localhost
export ANN_BENCHMARKS_CUB_PORT=30004
export ANN_BENCHMARKS_CUB_SERVER_PORT=5560

export ANN_BENCHMARKS_CUB_NUM_CAS=1
export OPENBLAS_NUM_THREADS=1

echo "[ann]" >> $CUBRID/conf/cubrid.conf && \
echo "data_buffer_size=16G" >> $CUBRID/conf/cubrid.conf

sed -i "s/^cubrid_port_id *= *.*/cubrid_port_id = ${ANN_BENCHMARKS_CUB_SERVER_PORT}/" $CUBRID/conf/cubrid.conf && \
      cubrid server restart ann && \
      until cubrid server status | grep -q "Server ann"; do \
      echo "Waiting for 'ann' DB to start..."; \
      sleep 1; \
      done && \
      awk ' \
      BEGIN { skip=0 } \
      /^\[%query_editor\]/ { skip=1; next } \
      /^\[/ && skip { skip=0 } \
      !skip \
      ' $CUBRID/conf/cubrid_broker.conf > /tmp/cubrid_broker.conf && \
      mv /tmp/cubrid_broker.conf $CUBRID/conf/cubrid_broker.conf && \
      sed -i "s/^MIN_NUM_APPL_SERVER[ \t]*=.*/MIN_NUM_APPL_SERVER = ${ANN_BENCHMARKS_CUB_NUM_CAS}/" $CUBRID/conf/cubrid_broker.conf && \
      sed -i "s/^MAX_NUM_APPL_SERVER[ \t]*=.*/MAX_NUM_APPL_SERVER = ${ANN_BENCHMARKS_CUB_NUM_CAS}/" $CUBRID/conf/cubrid_broker.conf && \
      sed -i "s/^BROKER_PORT[ \t]*=.*/BROKER_PORT = ${ANN_BENCHMARKS_CUB_PORT}/" $CUBRID/conf/cubrid_broker.conf && \
      cubrid broker restart && \
      until cubrid broker status | grep -q "% broker1"; do \
      echo "Waiting for broker1 to start..."; \
      sleep 1; \
      done && \
      csql -u dba ann -c "CREATE USER ann;" && \
      csql -u dba ann -c "ALTER USER ann PASSWORD 'ann';"

