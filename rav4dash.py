#!/usr/bin/env python3

import serial
from time import sleep

# RTS will go True upon opening serial port, and False when program closes
s = serial.Serial(port='/dev/ttyS4',baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=200, xonxoff=0, rtscts=0)

BCS = 0xD5 # battery controller
ECS = 0x16 # engine controller

def sendPacket(destination, data):
    toSend = [0x80 + len(data), destination, 0xF1] + data
    checksum = 0
    for i in toSend:
        checksum += i;
    toSend.append(checksum % 256)
    s.write(bytearray(toSend))
    readback = s.read(len(toSend)) # s.write() returns number of bytes sent
    if readback == bytearray(toSend):
        print("sent "+bytearray(toSend).hex())
    else:
        print("sent "+bytearray(toSend).hex()+" but echo was "+readback.hex())

def parseReply():
    a = s.read_all()
    while len(a) == 0:
        print('.',end='')
        a = s.read_all()

    if a[0] > 0x87 or a[0] < 0x81:
        print("first byte returned was "+hex(a[0])+" expected 0x81-0x87")
    print("returned "+a.hex())

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
    s.read_all() # throw away whatever is in the buffer
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

initBCS()

#s.setRTS(False) # True is +5.15v, False is -5.15v
exit() # RTS will go to False upon exit
