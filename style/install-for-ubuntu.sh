sudo apt-get -yq install build-essential texi2html wget

# install astyle
sudo apt-get -yq install astyle

# indent 2.2.11, the lastest version (2.2.12) make a different result
wget https://ftp.gnu.org/gnu/indent/indent-2.2.11.tar.gz
tar xf indent-2.2.11.tar.gz
cd indent-2.2.11
./configure
sudo make -j install
cd ..

