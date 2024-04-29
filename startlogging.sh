LOGFILE=$(date +"%Y%m%d_%H%M%S").log
while true; do
  python3 -u rav4dash.py | tee -a $LOGFILE
done
