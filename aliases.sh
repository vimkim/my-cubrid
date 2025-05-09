# vim: filetype=zsh

export PATH=$HOME/CTP/bin:$HOME/CTP/common/script:$PATH

export MY_CUBRID="$HOME/my-cubrid"

alias mycubrid='cd $MY_CUBRID'
alias mycub='mycubrid'

alias mypg='cd $(fd -t d -p "gh.*pgvector$" $HOME)'

alias cualias='$EDITOR ~/my-cubrid/aliases.sh'
alias cuali='$EDITOR ~/my-cubrid/aliases.sh'
alias socuali='source ~/my-cubrid/aliases.sh'

alias cu_dir='cd $ISSUE_DIR'
alias cud='cu_dir'

alias jcub='print -z "$(just.sh -j $MY_CUBRID/stow/cubrid/justfile -d .)"'
alias cubstow='stow --dir=$MY_CUBRID/stow --target=. cubrid'
alias jc='jcub'
alias nc='jcub'
alias jce='$EDITOR $MY_CUBRID/stow/cubrid/justfile'
alias nce='jce'
alias nl='print -z "$(just.sh -j ./.just/justfile -d .)"'
alias nu='print -z "$(just.sh -j ./.just/justfile -d .)"'
alias nle='$EDITOR ./.just/justfile'
alias nue='$EDITOR ./.just/justfile'


# alias justfile for work
alias jw='print -z "$(just.sh -j $MY_CUBRID/work.just -d .)"'
alias jwe='$EDITOR $MY_CUBRID/work.just'

# alias cu_build='. ~/my-cubrid/build.sh'
alias cu_build='cmake --preset profile && cmake --build --preset profile --target install'
alias cub='cu_build'

alias cu_rmdb='. ~/my-cubrid/remove-db.sh'

alias cu_createdb='~/my-cubrid/create-db.sh'
alias cuc='cu_createdb'

alias cub-nix-install-bison-305='nix-env -iA bison -f https://github.com/NixOS/nixpkgs/archive/0bcbb978795bab0f1a45accc211b8b0e349f1cdb.tar.gz'

alias cu_prepare='. ~/my-cubrid/prepare.sh'
alias cu_prepare_edit='$EDITOR ~/my-cubrid/prepare.sh'
alias cup='cu_prepare'
alias cupe='cu_prepare_edit'

alias cu_run='. ~/my-cubrid/run.sh'
alias cu_run_edit='$EDITOR ~/my-cubrid/run.sh'
alias cur='cu_run'
alias cure='cu_run_edit'

alias cu_all='cub && cu_rmdb && cu_createdb && cup && cur'
alias cua='cu_all'

### trace
alias cu_trace='. ~/my-cubrid/trace.sh'
# alias cut='cu_trace' # somehow causes problem
alias cu_trace_edit='$EDITOR ~/my-cubrid/trace.sh'
alias cu_tracee='cu_trace_edit'
alias cute='cu_trace_edit'

### trace dump
alias cu_trace_dump='uftrace dump'
alias cutd='cu_trace_dump'
alias cu_trace_dump_edit='$EDITOR ~/my-cubrid/trace-dump.sh'
alias cutde='cu_trace_dump_edit'
alias cu_trace_dump_flame='. ~/my-cubrid/trace-dump-flame-graph.sh'
alias cu_trace2html='trace2html uftrace-dump-chrome.json'
#alias cu_trace_serve='python3 ~/my-cubrid/serve_and_open.py'
alias cu_trace_dump_serve='open uftrace-dump-chrome.html'
alias cu_trace_dump_all='cu_trace_dump && cu_trace2html && cu_trace_dump_serve'

alias cu_trace_success='. ~/my-cubrid/trace-success.sh'
alias cu_trace_fail='. ~/my-cubrid/trace-fail.sh'
alias cu_trace_both='. ~/my-cubrid/trace-both.sh'

alias cu_format='~/my-cubrid/style/codestyle.sh'

alias cpenv='cp ~/my-cubrid/.envrc-template ./.envrc'
alias cpjust='cp $MY_CUBRID/Justfile ./Justfile'
alias cpvscode='cp $MY_CUBRID/.vscode/launch.json ./.vscode/launch.json'
alias lnvscode='ln -s $MY_CUBRID/.vscode/launch.json ./.vscode/launch.json'
alias cppreset='cp $MY_CUBRID/CMakeUserPresets.json ./CMakeUserPresets.json'
alias lnpreset='ln -s $MY_CUBRID/CMakeUserPresets.json ./CMakeUserPresets.json'

alias cubrid_initialize='cpenv && mkdir -p .vscode && lnvscode && lnpreset'
alias cubi='cubrid_initialize'

cubrid-error-message-to-enum() {
    rg -- "$1" msg/en_US.utf8/cubrid.msg | awk '{print $1}' | xargs -I{} rg -- "-{}" src/base/error_code.h
}

alias cuberr='cubrid-error-message-to-enum'

# CTP

function ctp_update_answer {
    local filename="$1"
    local new_ans_path=$(realpath "$filename")

    # Ensure the file is indeed in a 'cases' directory
    if [[ "$new_ans_path" != */cases/* ]]; then
        echo "Error: The file is not in a 'cases' directory."
        return 1
    fi

    # before
    ctp_diff "$filename"

    local old_path=$(echo "$new_ans_path" | sed 's|/cases/|/answers/|' | sed 's|\.result$|\.answer|')

    echo "Renaming $new_ans_path to $old_path"
    cp "$new_ans_path" "$old_path"

    # after
    ctp_diff "$filename"
}

function ctp_diff {
    local filename="$1"
    local new_ans_path=$(realpath "$filename")

    # Ensure the file is indeed in a 'cases' directory
    if [[ "$new_ans_path" != */cases/* ]]; then
        echo "Error: The file is not in a 'cases' directory."
        return 1
    fi

    local old_path=$(echo "$new_ans_path" | sed 's|/cases/|/answers/|' | sed 's|\.result$|\.answer|')

    echo "Comparing $new_ans_path to $old_path"
    delta "$old_path" "$new_ans_path"
}

function ctp_diff_all {

    for file in $(fd -I -e result); do
        ctp_diff "$file"
    done

}

alias cublog='$EDITOR $HOME/cublog/worklog-$(date +%Y-%m-%d).md'

# Add CUBRID binaries to PATH if MY_CUBRID is defined and the directory exists
if [ -n "$MY_CUBRID" ] && [ -d "$MY_CUBRID/bin" ]; then
    case ":$PATH:" in
        *":$MY_CUBRID/bin:"*) ;;
        *) export PATH="$MY_CUBRID/bin:$PATH" ;;
    esac
else
    echo "Warning: MY_CUBRID is not set or $MY_CUBRID/bin does not exist."
fi


