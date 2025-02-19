from datetime import datetime, timezone
from flask import Flask, render_template
import os
import subprocess
import time

app = Flask(__name__)

@app.route('/')
def webui():
  return render_template('app.html')

@app.route('/status')
def status():
  return render_template('status.html', fields=status_fields())

@app.route('/ignition_on')
def ignition_on():
  gpio60 = open('/sys/class/gpio/gpio60/value', 'w')
  subprocess.run(['echo', '0'], stdout=gpio60)
  return ('', 204)

@app.route('/startcharging')
def startcharging():  # tmux new-window -d -n 'charging' -t sess1:4 '$HOME/battbin/statusfilewatch.sh'
  subprocess.run(['/home/debian/bin/charging.sh'])
  return ('', 204)

@app.route('/stopcharging')
def stopcharging():  # kill $(pgrep -f statusfilewatch.sh)
  subprocess.run(['/home/debian/bin/killcharging.sh'])
  return ('', 204)

@app.route('/ignition_off')
def ignition_off():
  gpio60 = open('/sys/class/gpio/gpio60/value', 'w')
  subprocess.run(['echo', '1'], stdout=gpio60)
  return ('', 204)

def status_fields():
  status = last_status()
  parts = [x.split(':', 1) for x in status.split() if ':' in x]
  status_fields = {part[0]: part[1] for part in parts}
  cell_13, cell_mean = bms_status()
  diff = abs(cell_13 - cell_mean)
  badness = min(diff / 7.0, 1.0)
  tint = 255 - int(badness * 255)
  if cell_13 < cell_mean:
    bgcolor = f'ff{tint:02x}{tint:02x}'
  else:
    bgcolor = f'ff{tint:02x}ff'
  status_fields['_bgcolor'] = bgcolor
  status_fields['V13'] = f'{cell_13:.2f}'
  status_fields['Vmean'] = f'{cell_mean:.2f}'
  return status_fields

def last_status():
  last_log = 'rav4dash.status'
  with open(last_log) as f:
    lines = f.readlines()
    statuses = [x for x in lines if x.startswith('V:')]
    last_status = statuses.pop() if statuses else 'no status'
  last_update = datetime.fromtimestamp(os.path.getmtime(last_log), timezone.utc)
  return 'Time:%s ' % last_update.astimezone().strftime("%Y-%m-%dT%H:%M:%S") + last_status

def bms_status():
  last_log = 'bmsvoltages.txt'
  with open(last_log) as f:
    try:
      bms_voltages = f.readlines()[0].split(',')[1:25]
    except:
      bms_voltages = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
  return (float(bms_voltages[12]), sum([float(v) for i, v in enumerate(bms_voltages) if i != 12]) / 23)

if __name__ == '__main__':
  app.run()
