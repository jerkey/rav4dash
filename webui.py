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

@app.route('/test_brusa')
def test_brusa():
  serial = '/dev/ttyS2'
  subprocess.run(['stty', '-F', serial, '19200'])
  tty = open(serial, 'w')
  subprocess.run(['echo', '-ne', 'qq\n'], stdout=tty)
  time.sleep(0.5)
  subprocess.run(['echo', '-ne', 'profile\r\n'], stdout=tty)
  time.sleep(0.5)
  subprocess.run(['echo', '-ne', 'profile\r\n'], stdout=tty)
  time.sleep(5)
  subprocess.run(['echo', '-ne', r'\x02\x41\xf0\x01\x09\x04\x01\x41\x03'], stdout=tty)
  return ('', 204)

@app.route('/ignition_off')
def ignition_off():
  gpio60 = open('/sys/class/gpio/gpio60/value', 'w')
  subprocess.run(['echo', '1'], stdout=gpio60)
  return ('', 204)

def status_fields():
  status = last_status()
  parts = [x.split(':', 1) for x in status.split() if ':' in x]
  return {part[0]: part[1] for part in parts}

def last_status():
  last_log = 'statusfile.txt'
  with open(last_log) as f:
    lines = f.readlines()
    statuses = [x for x in lines if x.startswith('V:')]
    last_status = statuses.pop() if statuses else 'no status'
  last_update = datetime.fromtimestamp(os.path.getmtime(last_log), timezone.utc)
  return 'Time:%s ' % last_update.astimezone().strftime("%Y-%m-%dT%H:%M:%S") + last_status

if __name__ == '__main__':
  app.run()
