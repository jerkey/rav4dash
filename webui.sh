#!/bin/bash
if [ "$(cat /sys/class/gpio/gpio60/direction)" == "in" ] ; then
  echo high | sudo tee  /sys/class/gpio/gpio60/direction # HIGH turns ignition off
fi
# sending high or low to direction initializes it with the desired state
cd ~/rav4dash/
FLASK_APP=webui.py flask run  --host=0.0.0.0 2>&1 | grep -v 'GET .status HTTP.1.1' # https://stackoverflow.com/questions/14888799/disable-console-messages-in-flask-server
