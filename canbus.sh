if pgrep -af "python3 canbus.py"  ; then echo canbus.py is already running; exit; fi
cd $HOME/rav4dash
python3 canbus.py
