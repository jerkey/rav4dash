#!/usr/bin/env python3

import serial
from time import sleep

# RTS will go True upon opening serial port, and False when program closes
s = serial.Serial(port='/dev/ttyS4',baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=None, xonxoff=0, rtscts=0)

BCS = 0xD5 # battery controller
ECS = 0x16 # engine controller

def sendPacket(destination, data):
    toSend = [0x80 + len(data), destination, 0xF1] + data
    checksum = 0
    for i in toSend:
        checksum += i;
    toSend.append(checksum % 256)
    s.write(bytearray(toSend))

def initECS():
    s.write(bytearray.fromhex('00'))
    s.break_condition = True # https://forums.raspberrypi.com/viewtopic.php?t=239406
    sleep(0.035)
    s.break_condition = False
    s.write(bytearray.fromhex('00'))
    sleep(0.01)
    sendPacket(ECS,[0x81])
    parseReply()
    sendPacket(ECS,[0x12,0x1F,0])
    parseReply()
    sendPacket(ECS,[0x12,0x1F,1])
    parseReply()

def initBCS():
    s.write(bytearray.fromhex('00'))
    s.break_condition = True # https://forums.raspberrypi.com/viewtopic.php?t=239406
    sleep(0.035)
    s.break_condition = False
    s.write(bytearray.fromhex('00'))
    sleep(0.01)
    sendPacket(BCS,[0x81])
    parseReply()
    sendPacket(BCS,[0x12,0,0])
    parseReply()
    sendPacket(BCS,[0x12,0,1])
    parseReply()

def writehex(hexbytes):
    print('writing ',end='')
    for i in bytearray.fromhex(hexbytes):
        print(hex(i),end=' ')
        s.write(i)
        sleep(0.01)

init_BCS_mode = '81d5f181c8'
init_BCS_mode_response = '83f1d5c1e98f82'
init_EngineCS_mode = '8116f18109'
init_EngineCS_mode_response = '83f116c1e98fc3'

s.write(bytearray.fromhex('00'))
s.break_condition = True # https://forums.raspberrypi.com/viewtopic.php?t=239406
sleep(0.035)
s.break_condition = False
s.write(bytearray.fromhex('00'))
sleep(0.01)

#writehex(init_BCS_mode)
s.write(bytearray.fromhex(init_BCS_mode))
sleep(0.5)
readback = s.read_all().hex()
print('readback: '+ readback)
whatwesent = readback.find(init_BCS_mode)
response = readback[whatwesent+len(init_BCS_mode):]
print('thats '+readback[:whatwesent]+'and then whatwesent and then '+response)
if response == init_BCS_mode_response:
    print('correct response to BCS init')
if response == init_EngineCS_mode_response:
    print('correct response to EngineCS init')

exit()
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


#s.setRTS(False) # True is +5.15v, False is -5.15v
exit() # RTS will go to False upon exit
