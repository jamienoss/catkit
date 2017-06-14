# -*- coding: utf-8 -*-
"""
Created on Wed Jun 14 09:46:25 2017

@author: segron
"""

import subprocess
import time 

########
#General comments
########

# I'm using Python 2.7
# The control of the laser, calling a .exe is pretty much the same as the DM control. 
#Charles was involved in both codes. 


########
#What do you have to change? 
########

#We use C or C++ to generate the .exe . We should not need C or C++ anymore. The .exe is located at 
# C:\\Users\\jost\\Desktop\\SourceLaser\\debug\\SourceLaser.exe" , copy paste it on Hicat. 
# update the paths lines 32 & 33 of this script.
#Make sure that Hicat uses the laser channel 2, if not, change line 32
#You need a USB connection between Hicat computer and the laser


########
# Step by step
########

#When you start the experiment, to control the laser, you have to: 
# switch it on by turning the key
# press the button "enable laser"
#And that should be it, the code will connect to the channel spesified (the green light will turn on)

#Run the script
#If the script runs as it should, the laser will be on for 60 second and then off (check by eye).  

#Then the code quits the laser: the channel green light will turn off. 
#But, "enable laser" and the laser will still be on . Don't forget to turn them off manually. 




# INITIALIZE SOURCE LASER:
channel=2       # Channel 2 for Hicat?, same numbering as the one on the laser 
current=0.0
LASERexePath = "C:\\Users\\jost\\Desktop\\SourceLaser\\debug\\"
LASER = subprocess.Popen(["C:\\Users\\jost\\Desktop\\SourceLaser\\debug\\SourceLaser.exe", str(channel), str(current)], 
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                            cwd=LASERexePath, bufsize=1)
                            
#current: values are in mA 
#the first value: 0 is for the laser off. The second, 51.3 is for the focus image, The third is for the defocus image. 
# I am sure you can increase the current vector size.                             
current=[0,51.3,75.0]   

print "switching on the laser"
LASER.stdin.write(str(current[1])+"\n")
LASER.stdin.flush()     

#time.sleep(1) pauses the script for 1 second, I would recommand using it to make sure that the laser has changed to the right 
#intensity when you take exposures. 
time.sleep(60)

print "switching off the laser"
LASER.stdin.write(str(current[0])+"\n")  
LASER.stdin.flush()   

LASER.stdin.write("quit\n")
LASER.stdin.close()

#Achtung!
#If the code crashes, the laser doesn't quit the right way. Using a "try" in the python code would be the best. 
#If this is not implemented, unplug and replug USB before starting again. 