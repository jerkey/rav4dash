LOGFILE=$(date +"%Y%m%d_%H%M%S").log
python3 -u rav4dash.py | tee $LOGFILE
