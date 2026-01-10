# AirMouse
THe airmouse project utilizes motion sensors and camera data to collectively allow a mobile device to act as a mouse. The iOS or Android phone would be able to move the mouse, by moving on a stable plane, and act the same as a real mouse. This means, no air, or trackpad capability on the AirMouse Project.

## Connection
The inital connection screen allows for IP address, port, and camera selection to occur. We can customize sensitivity, camera capture FPS, and what sensors and if camera should be used. This should be a checkbox lsit so that we can enable or disable any number of sensors and camera. The mobile device acts as the client and will send data to the "server", which will be the computer. The computer will use PyAutoGUI to move the mouse and simulate mouse movement and actions.

## Mouse screen (mobile)
After the connection is established, the screen on the mobile phone should change to left mouse button, right mouse button and scroll wheel. THis would act like the real mouse, and would maintain connection.

## Tech Stack
using Python for the server, and nextJS for the client, we can accurately and correctly build a working airmouse.

