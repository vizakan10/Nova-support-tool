#!/usr/bin/env bash
# Nova CLI — bash tab completion (installed to ~/.nova/nova_completion.sh)

_nova_complete() {
    local cur prev
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD - 1]}"

    local commands="up ask add search csetup csync sync-confluence syncconfluence confluence-setup confluencesetup kb list config setup add-llm use set-provider test rm model apikey help version install-hooks ano update add-kb rm-kb use-kb fresh providers -a s -h --help -v --version"
    local kb_subcmds="list rm path search"

    if [[ ${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=($(compgen -W "${commands}" -- "${cur}"))
        return 0
    fi

    local cmd="${COMP_WORDS[1]}"
    case "${cmd}" in
        kb)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "${kb_subcmds}" -- "${cur}"))
            fi
            ;;
        csetup|confluence-setup|confluencesetup)
            ;;
        csync|sync-confluence|syncconfluence)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                COMPREPLY=($(compgen -W "-r --refresh" -- "${cur}"))
            fi
            ;;
        update)
            if [[ ${COMP_CWORD} -ge 2 ]]; then
                COMPREPLY=($(compgen -W "--pull -p --setup" -- "${cur}"))
            fi
            ;;
        search|ask|-a|s|up)
            ;;
        use|rm|model|apikey|test)
            if [[ ${COMP_CWORD} -eq 2 ]]; then
                local nicks
                nicks=$(nova list 2>/dev/null | awk '/^  / {print $1}' || true)
                COMPREPLY=($(compgen -W "${nicks}" -- "${cur}"))
            fi
            ;;
        *)
            ;;
    esac
}

complete -F _nova_complete nova 2>/dev/null || true
