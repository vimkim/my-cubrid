_default:
    @just --choose

dev2-server:
    with-env { LANG : "en_US.utf8", TERM : "xterm-256color" } { ssh -Y vimkim@192.168.4.2 }

dev2-container-1:
    with-env { LANG : "en_US.utf8", TERM : "xterm-256color" } { ssh -Y vimkim@192.168.4.151 }

dev2-container-2:
    with-env { LANG : "en_US.utf8", TERM : "xterm-256color" } { ssh -Y vimkim@192.168.4.152 }

dev2-container-9:
    with-env { LANG : "en_US.utf8", TERM : "xterm-256color" } { ssh -Y vimkim@192.168.4.159 }

vpn:
    sudo openfortivpn cubrid1.fortiddns.com:10443 --username=
