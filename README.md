# Overview: Drone on a Stick
is a physical simulation of an autonomous drone platform designed for 
Search and rescue 
It leverages [Computer vision, GPS-denied navigation, and machine learning] 
using a control loop from the drone to a laptop and then from laptop to human, the program on the laptop controls the drone via the human element giving control commands to the human to move the drone using the stick.
 
# Features ✨
Autonomous Navigation:
Real-time path planning and dynamic obstacle avoidance.
Computer Vision: Onboard object detection, tracking, and [e.g., thermal imaging/facial recognition].
Fail-Safe Protocols: Automatic Return-to-Launch (RTL) on low battery or signal loss.
Telemetry & Control: 
Web-based dashboard:
for live mission monitoring and waypoint injection.
 
# Tech Stack & Hardware 🛠️
Flight Controller: XIAO S3 xpressif esp32
Sensors: Camera
Software Frameworks: Python, Micropython

# Requirements:
Ensure you have the following installed before setting up the project:
Windows or linux:
droneonastick/setup.sh
PIP3 - package managemnet for each system.
Python3 - python
Micropython - smaller python

# STEPS
## Basics & Calibration (Ground Control)

### Software
Install dependencies
pip install -r requirements.txt

### April Tags
Place the apriltag set on your desk
Talk about April tags
Xiao camera setup - April tag detection firmware
droneonastick/esp32s3/firmware.mpy
Fiducial Calibration

## Control Loop
### Concept
SENSE: XIAO Cam sees the april tag computes dist to center tag
THINK: The code on the camera and the computer computes the distance and power needed to move.
ACT: Commnads sent to human/drone
Proportional Control (P-Loop): Correction = Error * Kp

## Flight Mission State Machine
Launch, Active hold, Command trick, Land.
 
## Hardware
### Parts
Drone on a stick
April tags
Personal Laptop

## Software 
micropython using Thonny
c++ using arduino










