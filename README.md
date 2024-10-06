# rav4dash
upgrade a Generation 1 Toyota RAV4 Electric Vehicle to be a modern EV

to redirect output with linux tee command, you must use python3 in unbuffered output mode:
date > output.txt ; python3 -u rav4dash.py | tee -a output.txt

or run 
./startlogging.sh

see 20231231_093359.log for a rare glimpse at charge termination

to run webui.sh you need flask
sudo apt install python3-flask
