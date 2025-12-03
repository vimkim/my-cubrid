# cub-env.sh
# Usage:
#   source cub-env.sh -b <branch_name> -p <preset_mode>

cubenv_usage() {
  echo "Usage: source cub-env.sh -b <branch_name> -p <preset_mode>"
  return 1
}

# When sourced, $0 may not be the script name, so use $BASH_SOURCE
SCRIPT_NAME="${BASH_SOURCE[0]}"

# Parse options
while getopts ":b:p:" opt; do
  case "$opt" in
    b) BRANCH_NAME="$OPTARG" ;;
    p) PRESET_MODE="$OPTARG" ;;
    *) cubenv_usage; return 1 ;;
  esac
done

# Validate required options
if [[ -z "$BRANCH_NAME" || -z "$PRESET_MODE" ]]; then
  echo "Error: -b and -p are required."
  cubenv_usage
  return 1
fi

###############################################################################
# Environment setup
###############################################################################

export CUBRID="/home/vimkim/.cub/install/$BRANCH_NAME/$PRESET_MODE"
export CUBRID_BUILD_DIR="/home/vimkim/gh/cb/$BRANCH_NAME/build_preset_$PRESET_MODE"
export CUBRID_DATABASES="/home/vimkim/.cub/db/$BRANCH_NAME/commondb"

# Prepend to PATH only if not already present
case ":$PATH:" in
  *":$CUBRID/bin:"*) ;;
  *) export PATH="$CUBRID/bin:$PATH" ;;
esac

echo "CUBRID environment configured:"
echo "  BRANCH_NAME=$BRANCH_NAME"
echo "  PRESET_MODE=$PRESET_MODE"
echo "  CUBRID=$CUBRID"

