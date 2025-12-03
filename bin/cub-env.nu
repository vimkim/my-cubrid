# cub-env.nu
# Usage:
#   overlay use cub-env.nu
#   cubenv -b develop -p release_gcc8

export def --env cubenv [
  --branch (-b): string
  --preset (-p): string
] {
  if ($branch | is-empty) or ($preset | is-empty) {
    error make { msg: "branch (-b) and preset (-p) are required" }
  }

  let cubrid    = $"/home/vimkim/.cub/install/($branch)/($preset)"
  let build_dir = $"/home/vimkim/gh/cb/($branch)/build_preset_($preset)"
  let db_dir    = $"/home/vimkim/.cub/db/($branch)/commondb"

  # Modify caller environment
  $env.CUBRID = $cubrid
  $env.CUBRID_BUILD_DIR = $build_dir
  $env.CUBRID_DATABASES = $db_dir

  if not ($env.PATH | any { |it| $it == $"($cubrid)/bin" }) {
    $env.PATH = [$"($cubrid)/bin"] ++ $env.PATH
  }

  print $"CUBRID environment configured:"
  print $"  BRANCH_NAME=($branch)"
  print $"  PRESET_MODE=($preset)"
  print $"  CUBRID=($cubrid)"
}
