#!/bin/bash

# in xxx.sh,  command source ~/.bashrc not useful

set -x

# conda install
mkdir -p ~/download/anaconda
cd ~/download/anaconda
wget https://repo.anaconda.com/archive/Anaconda3-2020.11-Linux-x86_64.sh
chmod +x Anaconda3-2020.11-Linux-x86_64.sh
./Anaconda3-2020.11-Linux-x86_64.sh -b
eval "$(~/anaconda3/bin/conda shell.bash hook)"
#~/anaconda3/bin/conda init bash
~/anaconda3/bin/conda init
echo "conda deactivate" >> ~/.bashrc

# change conda source url
~/anaconda3/bin/conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
~/anaconda3/bin/conda config --set show_channel_urls yes
~/anaconda3/bin/conda clean -i
