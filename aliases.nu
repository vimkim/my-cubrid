export-env { $env.MY_CUBRID = $"($env.HOME)/my-cubrid" }
alias cuali = nvim ~/my-cubrid/aliases.nu
alias nr = commandline edit (just.nu -f ~/my-cubrid/remote-nu.just -d .)
alias nre = nvim ~/my-cubrid/remote-nu.just
alias ncub = commandline edit (just.nu -f ~/my-cubrid/stow/cubrid/justfile -d .)
alias ncube = nvim ~/my-cubrid/stow/cubrid/justfile
