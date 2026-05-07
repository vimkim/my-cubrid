export-env { $env.MY_CUBRID = $"($env.HOME)/my-cubrid" }
alias cs = csql.sh
alias cuali = nvim ~/my-cubrid/aliases.nu
alias nr = commandline edit (just.nu -f ~/my-cubrid/remote-nu.just -d . | str trim)
alias nre = nvim ~/my-cubrid/remote-nu.just
alias ncub = commandline edit (just.nu -f ~/my-cubrid/stow/cubrid/justfile -d . | str trim)
alias ncube = nvim ~/my-cubrid/stow/cubrid/justfile

alias tcsql = cd ~/gh/tc/cubrid-testcases/
alias tcshell = cd ~/cubrid-testcases-private-ex/

alias ooslog = do { nvim $"($env.CUBRID)/log/oos.log" }

# ──────────────────────────────────────────────────────────────────────
# CUBRID env switcher — pure nu, mirrors stow/cubrid/.envrc
#
#   cubrid-use release_gcc                          # use cwd as source dir
#   cubrid-use debug_clang --dir ~/gh/cb/feat-oos   # explicit source dir
#   cubrid-use --env-file .env                      # read PRESET_MODE / SOURCE_DIR from a .env
#
# Re-running in the same session switches cleanly: the first call snapshots
# PATH / LD_LIBRARY_PATH so subsequent calls rebuild from that pristine baseline
# instead of accumulating stale entries from a previous CUBRID install.
# ──────────────────────────────────────────────────────────────────────
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

  let current_dir       = ($src | path basename)
  let cubrid            = $"($env.HOME)/.cub/install/($current_dir)/($preset)"
  let cubrid_databases  = $"($env.HOME)/.cub/db/($current_dir)/commondb"
  let cubrid_build_dir  = $"($src)/build_preset_($preset)"
  let bison_path        = $"($env.HOME)/temp/bison-install"
  let ctp_home          = $"($env.HOME)/gh/ctp/run-sql/CTP"

  # First call ever: snapshot pristine PATH / LD_LIBRARY_PATH. Subsequent calls
  # always rebuild from this baseline so switching CUBRIDs doesn't leak.
  if ($env | get --optional CUBRID_BASELINE_PATH) == null {
    $env.CUBRID_BASELINE_PATH = $env.PATH
    $env.CUBRID_BASELINE_LD_LIBRARY_PATH = ($env | get --optional LD_LIBRARY_PATH | default "")
  }

  let baseline_path = $env.CUBRID_BASELINE_PATH
  let base_path = (
    if ($baseline_path | describe | str starts-with "list") { $baseline_path }
    else { $baseline_path | split row (char esep) }
  )
  let base_ld = ($env.CUBRID_BASELINE_LD_LIBRARY_PATH | split row ":" | where {|x| $x != "" })

  $env.PRESET_MODE      = $preset
  $env.CURRENT_DIR      = $current_dir
  $env.CUBRID           = $cubrid
  $env.CUBRID_DATABASES = $cubrid_databases
  $env.CUBRID_BUILD_DIR = $cubrid_build_dir
  $env.BISON_PATH       = $bison_path
  $env.CTP_HOME         = $ctp_home
  $env.init_path        = $"($ctp_home)/shell/init_path"
  $env.ASAN_OPTIONS     = "halt_on_error=0:log_path=./asan.log"
  $env.LSAN_OPTIONS     = "halt_on_error=0:log_path=./lsan.log"

  $env.PATH = ([
    $"($bison_path)/bin"
    $"($cubrid)/bin"
    $"($ctp_home)/common/script"
    $"($ctp_home)/bin"
  ] ++ $base_path | uniq)

  $env.LD_LIBRARY_PATH = ([
    $"($bison_path)/lib"
    $"($cubrid)/cci/lib"
    $"($cubrid)/lib"
    $"($env.HOME)/CUB3LIB/lib"
    "/usr/local/lib"
  ] ++ $base_ld | uniq | str join ":")

  # mirror .envrc: refresh the compile_commands.json symlink when the build dir exists
  if ($cubrid_build_dir | path exists) {
    ^ln -sf $"build_preset_($preset)/compile_commands.json" $"($src)/compile_commands.json"
  }

  print $"Preset Mode: ($preset)"
  print $"Source Dir:  ($src)"
  print $"Install Dir: ($cubrid)"
  print $"DB Dir:      ($cubrid_databases)"
  print $"Build Dir:   ($cubrid_build_dir)"
}

# Restore PATH / LD_LIBRARY_PATH to the snapshot taken at the first cubrid-use call.
# Note: CUBRID/PRESET_MODE/etc. vars are left in place — `hide-env` does not
# propagate across a `def --env` boundary in nushell. They get overwritten on
# the next `cubrid-use` call, or you can start a fresh shell.
def --env cubrid-reset [] {
  if ($env | get --optional CUBRID_BASELINE_PATH) == null {
    print "no baseline captured; nothing to reset"
    return
  }
  $env.PATH            = $env.CUBRID_BASELINE_PATH
  $env.LD_LIBRARY_PATH = $env.CUBRID_BASELINE_LD_LIBRARY_PATH
  print "PATH / LD_LIBRARY_PATH restored to baseline"
}
