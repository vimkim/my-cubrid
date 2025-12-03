#!/bin/bash
# cub.sh — CUBRID wrapper with required options

set -e

usage() {
  echo "Usage: $0 -b <branch_name> -p <preset_mode> <cubrid_command> [args...]"
  echo
  echo "Example:"
  echo "  $0 -b scope-exit -p release_gcc8 broker start"
  echo "  $0 -b scope-exit -p release_gcc8 server start testdb"
  exit 1
}

# Parse required options
while getopts ":b:p:" opt; do
  case "$opt" in
    b) BRANCH_NAME="$OPTARG" ;;
    p) PRESET_MODE="$OPTARG" ;;
    *) usage ;;
  esac
done

shift $((OPTIND - 1))

# Validate required options
if [[ -z "$BRANCH_NAME" || -z "$PRESET_MODE" ]]; then
  echo "Error: branch name (-b) and preset mode (-p) are required."
  usage
fi

# Validate that a cubrid subcommand is provided
if [[ $# -lt 1 ]]; then
  echo "Error: cubrid command is required."
  usage
fi

###############################################################################
# Do not modify
###############################################################################

export CUBRID="/home/vimkim/.cub/install/$BRANCH_NAME/$PRESET_MODE"
export CUBRID_BUILD_DIR="/home/vimkim/gh/cb/$BRANCH_NAME/build_preset_$PRESET_MODE"
export CUBRID_DATABASES="/home/vimkim/.cub/db/$BRANCH_NAME/commondb"
export PATH="$CUBRID/bin:$PATH"

###############################################################################
# Forward remaining arguments to cubrid
###############################################################################

exec cubrid "$@"

