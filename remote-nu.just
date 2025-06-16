_default:
    @just --choose

dev2-server:
    LANG=en_US.utf8 TERM=xterm ssh -Y vimkim@192.168.4.2

dev2-container-1:
    with-env { LANG : "en_US.utf8" } { ssh -Y vimkim@192.168.2.151 }

dev2-container-2:
    with-env { LANG : "en_US.utf8" } { ssh -Y vimkim@192.168.2.152 }

vpn:
    sudo openfortivpn cubrid1.fortiddns.com:10443 --username=
