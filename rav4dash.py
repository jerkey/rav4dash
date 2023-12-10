#!/usr/bin/env python3

import serial
from time import sleep

init_rav4evmon3 = '81D5F181C8'

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
print('response: '+ s.read_all().hex())
sleep(1)
print('response: '+ s.read_all().hex())






exit()
s.setRTS(False)
sleep(1)
s.setRTS(True)
