if pgrep -af "python3 -u rav4dash.py"  ; then echo rav4dash.py is already running; exit; fi
cd $HOME/rav4dash
./startlogging.sh
