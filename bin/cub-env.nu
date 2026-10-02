# overlay use cub-env.nu; cubenv -b develop -p debug_gcc
export def --env cubenv [--branch (-b): string, --preset (-p): string, --worktree (-w): path] {
  if (($branch | is-empty) and ($worktree | is-empty)) or ($preset | is-empty) {
    error make {msg: "worktree (-b) and preset (-p) are required"}
  }
  let helper = ($env.MY_CUBRID? | default ($env.HOME | path join 'my-cubrid') | path join 'bin/cub-env.sh')
  let target = if ($worktree | is-not-empty) { $worktree | path expand } else { ($env.CUB_WORKENV_WORKTREE_ROOT? | default ($env.HOME | path join 'gh/cb')) | path join $branch }
  let result = (^bash -c 'source "$1" -w "$2" -p "$3"; status=$?; python3 -c "import json,os; print(json.dumps(dict(os.environ)))"; exit "$status"' bash $helper $target $preset | complete)
  let selected = ($result.stdout | from json)
  for key in ($env | columns | where {|key| $key | str starts-with 'CUBRID'}) {
    hide-env $key
  }
  hide-env --ignore-errors LD_PRELOAD
  $env.PATH = ($selected.PATH | split row ':')
  $env.LD_LIBRARY_PATH = ($selected.LD_LIBRARY_PATH? | default '')
  if $result.exit_code != 0 {
    error make {msg: $"cub-workenv selection failed: ($result.stderr)"}
  }
  load-env ($selected | transpose key value | where {|row| ($row.key | str starts-with 'CUBRID') or $row.key == 'PRESET_MODE'} | transpose --header-row --as-record)
}
