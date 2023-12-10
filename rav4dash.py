#!/usr/bin/env python3

import serial
from time import sleep

init_BCS_mode = '81d5f181c8'
init_BCS_mode_response = '83f1d5c1e98f82'
init_EngineCS_mode = '8116f18109'
init_EngineCS_mode_response = '83f116c1e98fc3'
init_EngineCS_DTCquery = '8116f11398'

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
#writehex(init_BCS_mode)
#writehex('daedbeeff00d')
#s.write(bytearray.fromhex('8116F18109'))
#s.write(bytearray.fromhex(init_BCS_mode))
#sleep(0.5)
#readback = s.read_all().hex()
#print('readback: '+ readback)
#whatwesent = readback.find(init_BCS_mode)
#response = readback[whatwesent+len(init_BCS_mode):]
#print('thats '+readback[:whatwesent]+'and then whatwesent and then '+response)
#if response == init_BCS_mode_response:
#    print('correct response to BCS init')
#if response == init_EngineCS_mode_response:
#    print('correct response to EngineCS init')
#
#sleep(1)

s.write(bytearray.fromhex(init_EngineCS_mode))
sleep(1)
readback = s.read_all().hex()
print('readback: '+ readback)
whatwesent = readback.find(init_EngineCS_mode)
response = readback[whatwesent+len(init_EngineCS_mode):]
print('thats '+readback[:whatwesent]+'and then whatwesent and then '+response)
if response == init_BCS_mode_response:
    print('correct response to BCS init')
if response == init_EngineCS_mode_response:
    print('correct response to EngineCS init')

sleep(1)

s.write(bytearray.fromhex(init_EngineCS_DTCquery))
sleep(0.5)
readback = s.read_all().hex()
print('readback: '+ readback)
whatwesent = readback.find(init_EngineCS_DTCquery)
response = readback[whatwesent+len(init_EngineCS_DTCquery):]
print('thats '+readback[:whatwesent]+'and then whatwesent and then '+response)



exit()
s.setRTS(False)
sleep(1)
s.setRTS(True)
