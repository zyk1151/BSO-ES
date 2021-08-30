#!/bin/bash

# sudoer
# mujoco config
# execute by bash, one-by-one, not just execute .sh


mkdir -p ~/.mujoco
cd ~/.mujoco/
wget https://www.roboti.us/download/mjpro150_linux.zip
unzip mjpro150_linux.zip
#copy mjkey.txt to ~/.mujoco
# ubuntu
sudo apt-get install libosmesa6-dev
sudo apt-get install libgl1-mesa-dev
sudo apt-get install patchelf
## centos
#sudo yum install mesa*
#sudo yum install patchelf





