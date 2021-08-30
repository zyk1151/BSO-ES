#!/bin/bash

# conda virtual environment create
# in xxx.sh,  command source ~/.bashrc not useful

set -x

vname='vtest'

# before, need install anaconda, conda_install.sh

# conda virtual environment create
mkdir -p ~/zyk/programming/conda/envs
cd ~/zyk/programming/conda/envs

#conda create --prefix ./${vname} -y -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda create --prefix ./${vname} -y
echo "alias ${vname}=\"conda activate $HOME/zyk/programming/conda/envs/${vname}\"" >> ~/.bashrc
eval "$(conda shell.bash hook)"
conda activate ./${vname}

conda install -y --prefix ./${vname} python=3.7.6

pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple/ numpy==1.19.5 scipy==1.5.1 gym==0.17.2 tensorflow==1.15 redis==3.5.3 click

# gym mujoco
# after mujoco_install
pip install -U 'mujoco-py>=1.5.0, <2.0'






