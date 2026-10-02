export-env { $env.MY_CUBRID = ($env.MY_CUBRID? | default ($env.HOME | path join "my-cubrid")) }
use bin/cub-env.nu cubenv
alias cs = csql.sh
alias cuali = nvim ~/my-cubrid/aliases.nu
def --env nr [] {
  let justfile = ($env.MY_CUBRID | path join "remote-nu.just")
  let recipe = (just-pick-and-print.nu -f $justfile -d . | str trim)
  if ($recipe | is-not-empty) {
    commandline edit $"just -f ~/my-cubrid/remote-nu.just -d . ($recipe)"
  }
}
alias nre = nvim ~/my-cubrid/remote-nu.just
def --env nc [] {
  let justfile = ($env.MY_CUBRID | path join "cubrid-justfiles/justfile")
  let recipe = (just-pick-and-print.nu -f $justfile -d . | str trim)
  if ($recipe | is-not-empty) {
    commandline edit $"just -f ~/my-cubrid/cubrid-justfiles/justfile -d . ($recipe)"
  }
}
alias ncub = nc
alias ncube = nvim ~/my-cubrid/cubrid-justfiles/justfile

alias tcsql = cd ~/gh/tc/cubrid-testcases/
alias tcshell = cd ~/cubrid-testcases-private-ex/

def --env cc [] {
  let picker_command = $"($env.MY_CUBRID)/bin/cubrid-dir-picker.sh"
  let picker = (^$picker_command | complete)
  if $picker.exit_code != 0 {
    print -e ($picker.stderr | str trim)
    return
  }

  let target = ($picker.stdout | str trim)
  if ($target | is-not-empty) {
    cd $target
  }
}

alias ooslog = do { nvim $"($env.CUBRID)/log/oos.log" }

# Select a prepared host workenv; use direnv for build-only preparation.
def --env cubrid-use [
  preset_mode?: string         # e.g. release_gcc, debug_clang
  --dir: path                  # source dir (default: $env.PWD)
  --env-file: path             # optional .env with PRESET_MODE / SOURCE_DIR
] {
  mut preset = $preset_mode
  mut src    = (if $dir != null { $dir | path expand } else { $env.PWD })

  if $env_file != null {
    let kv = (open --raw $env_file
      | lines
      | each {|l| $l | str trim }
      | where {|l| $l != "" and not ($l | str starts-with "#") }
      | parse --regex '^(?:export\s+)?(?<k>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"?(?<v>[^"#\n]*?)"?\s*$'
      | update v {|r| $r.v | str replace --all '$HOME' $env.HOME }
      | reduce --fold {} {|row, acc| $acc | upsert $row.k $row.v })
    if $preset == null { $preset = ($kv | get --optional PRESET_MODE) }
    if $dir == null and ($kv | get --optional SOURCE_DIR) != null {
      $src = ($kv.SOURCE_DIR | path expand)
    }
  }

  if $preset == null {
    error make {msg: "PRESET_MODE not provided (pass as positional arg or via --env-file)"}
  }

  cubenv --worktree $src --preset $preset
}

# Clear the selected native environment and its PATH/library entries.
def --env cubrid-reset [] {
  let selected = ($env.CUBRID? | default '')
  if $selected != '' {
    $env.PATH = ($env.PATH | where {|p| $p != ($selected | path join 'bin')})
    $env.LD_LIBRARY_PATH = ($env.LD_LIBRARY_PATH? | default '' | split row ':' | where {|p| $p not-in [($selected | path join 'lib'), ($selected | path join 'cci/lib')]} | str join ':')
  }
  for key in ($env | columns | where {|key| $key | str starts-with 'CUBRID'}) {
    hide-env $key
  }
  hide-env --ignore-errors LD_PRELOAD
  hide-env --ignore-errors PRESET_MODE
}
