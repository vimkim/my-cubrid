# Source cub-env.sh -b WORKTREE_NAME -p PRESET to load a prepared environment.
# Directory selection is explicit; missing/partial state never initializes it.
cubenv_load()
{
  local branch="" preset="" worktree="" option OPTIND=1 selection status=0
  while getopts ':b:p:w:' option; do
    case "$option" in
      b) branch="$OPTARG" ;;
      w) worktree="$OPTARG" ;;
      p) preset="$OPTARG" ;;
      *) printf 'Usage: source cub-env.sh -b WORKTREE_NAME -p PRESET\n' >&2; return 64 ;;
    esac
  done
  [[ ( -n "$branch" || -n "$worktree" ) && -n "$preset" ]] || { printf 'Worktree and preset are required.\n' >&2; return 64; }
  worktree="${worktree:-${CUB_WORKENV_WORKTREE_ROOT:-$HOME/gh/cb}/$branch}"
  selection="$("${CUB_WORKENV_CLI:-cub-workenv}" env --worktree "$worktree" --preset "$preset")" || status=$?
  export PRESET_MODE="$preset"
  eval "$selection" || status=$?
  [[ "$status" == 0 && "${CUBRID_RUNTIME_READY:-0}" == 1 ]] || return 1
  export PRESET_MODE="$preset"
  export CUBRID_BUILD_DIR="$worktree/build_preset_$preset"
}
cubenv_load "$@"
