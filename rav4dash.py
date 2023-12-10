#!/usr/bin/env python3

import serial
from time import sleep

init_rav4evmon3 = '81d5f181c8'
init_rav4evmon3_response = '83f1d5c1e98f82'

s = serial.Serial(port='/dev/ttyS4',baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=None, xonxoff=0, rtscts=0)

def writehex(hexbytes):
    print('writing ',end='')
    for i in bytearray.fromhex(hexbytes):
        print(hex(i),end=' ')
        s.write(i)
        sleep(0.01)

s.write(bytearray.fromhex('00'))
s.break_condition = True # https://forums.raspberrypi.com/viewtopic.php?t=239406
sleep(0.035)
s.break_condition = False
s.write(bytearray.fromhex('00'))
sleep(0.01)
#writehex('8116F18109') # got response ff03150016 with 0.01 delay
#writehex(init_rav4evmon3)
#writehex('daedbeeff00d')
#s.write(bytearray.fromhex('8116F18109'))
s.write(bytearray.fromhex(init_rav4evmon3))
sleep(0.5)
readback = s.read_all().hex()
print('readback: '+ readback)
whatwesent = readback.find(init_rav4evmon3)
response = readback[whatwesent+len(init_rav4evmon3):]
print('thats '+readback[:whatwesent]+'and then init_rav4evmon3 and then '+response)
if response == init_rav4evmon3_response:
    print('correct response to init')


exit()
s.setRTS(False)
sleep(1)
s.setRTS(True)
