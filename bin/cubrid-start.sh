#!/bin/bash

###############################################################################
# Required arguments:
#   1) Branch name
#   2) Preset mode
###############################################################################

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <BRANCH_NAME> <PRESET_MODE>"
  exit 1
fi

export BRANCH_NAME="$1"
export PRESET_MODE="$2"

###############################################################################
# Do not modify
###############################################################################

export CUBRID="/home/vimkim/.cub/install/$BRANCH_NAME/$PRESET_MODE"
export CUBRID_BUILD_DIR="/home/vimkim/gh/cb/$BRANCH_NAME/build_preset_$PRESET_MODE"
export CUBRID_DATABASES="/home/vimkim/.cub/db/$BRANCH_NAME/commondb"
export PATH="$CUBRID/bin:$PATH"

cubrid server start testdb
cubrid broker start

