LOGFILE=$(date +"%Y%m%d_%H%M%S").log
#ignition_on.sh
EXITCODE=0
while [ ${EXITCODE}sdfsdf == "0sdfsdf" ] ; do
  python3 -u rav4dash.py | tee -a $LOGFILE
  EXITCODE=$?
  echo EXITCODE=$EXITCODE
done
read
