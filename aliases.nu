export-env { $env.MY_CUBRID = $"($env.HOME)/my-cubrid" }
alias cs = csql.sh
alias cuali = nvim ~/my-cubrid/aliases.nu
alias nr = commandline edit (just.nu -f ~/my-cubrid/remote-nu.just -d . | str trim)
alias nre = nvim ~/my-cubrid/remote-nu.just
alias ncub = commandline edit (just.nu -f ~/my-cubrid/stow/cubrid/justfile -d . | str trim)
alias ncube = nvim ~/my-cubrid/stow/cubrid/justfile
