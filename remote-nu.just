_default:
    @just --choose

dev2-server:
    with-env { LANG : "en_US.UTF-8", TERM : "xterm-256color" } { ssh -Y vimkim@192.168.4.2 }

dev2-container-1:
    with-env { LANG : "en_US.UTF-8", TERM : "xterm-256color" } { ssh -Y vimkim@192.168.4.151 }

dev2-container-2:
    with-env { LANG : "en_US.UTF-8", TERM : "xterm-256color" } { ssh -Y vimkim@192.168.4.152 }

dev2-container-9:
    with-env { LANG : "en_US.UTF-8", TERM : "xterm-256color" } { ssh -Y vimkim@192.168.4.159 }

vpn:
    sudo openfortivpn cubrid1.fortiddns.com:10443 --username=

dev2-server-mount:
    sshfs vimkim@dev2-server:toast-ppt ~/dev2-mount -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,cache=no

dev2-server-unmount:
    umount ~/dev2-mount

sshfs-list:
    findmnt -t fuse.sshfs
