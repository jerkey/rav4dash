#!/usr/bin/env python3

import serial
import time

# RTS will go True upon opening serial port, and False when program closes
s = serial.Serial(port='/dev/ttyS4',baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=2000, xonxoff=0, rtscts=0)

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
    if readback != bytearray(toSend):
        print("sent "+bytearray(toSend).hex()+" but echo was "+readback.hex())

def parseReply(printout=True):
    a = s.read_all()
    startParseTime = time.time()
    while len(a) == 0 and (time.time() - startParseTime) < 5: # timeout in seconds
        print('.',end='')
        time.sleep(0.1)
        a = s.read_all()
    if len(a) == 0:
        s.read_all() # clear buffer
        return False
    if a[0] > 0x87 or a[0] < 0x81:
        print("first byte returned was "+hex(a[0])+" expected 0x81-0x87")
        return False
    if a[0] & 15 != len(a) - 4:
        print("expected "+str((a[0] & 15) + 4)+" bytes but got "+str(len(a)))
        return False
    checksum = 0
    for i in a[0:(3 + a[0] & 15)]:
        checksum += i;
    checksum %= 256
    if checksum != a[len(a)-1]:
        print("checksum is wrong, was "+str(a[len(a)-1])+" but expected "+str(checksum))
        return False
    if printout:
        if a[2] == ECS:
            print("ECS says: ",end='')
        if a[2] == BCS:
            print("BCS says: ",end='')
        print(a[3:(3 + a[0] & 15)].hex())
    return a

def initECS():
    s.write(bytearray.fromhex('00'))
    s.break_condition = True # https://forums.raspberrypi.com/viewtopic.php?t=239406
    time.sleep(0.035)
    s.break_condition = False
    s.write(bytearray.fromhex('00'))
    time.sleep(0.01)
    s.read_all() # throw away whatever is in the buffer
    sendPacket(ECS,[0x81])
    parseReply()
    sendPacket(ECS,[0x12,0x1F,0])
    parseReply()
    sendPacket(ECS,[0x12,0x1F,1])
    parseReply()

def initBCS():
    initBCSStatus = False
    while initBCSStatus == False:
        s.write(bytearray.fromhex('00'))
        s.break_condition = True # https://forums.raspberrypi.com/viewtopic.php?t=239406
        time.sleep(0.035)
        s.break_condition = False
        s.write(bytearray.fromhex('00'))
        time.sleep(0.01)
        print("all: "+str(s.read_all())) # throw away whatever is in the buffer
        sendPacket(BCS,[0x81])
        initBCSStatus = parseReply()
    sendPacket(BCS,[0x12,0,0])
    parseReply()
    sendPacket(BCS,[0x12,0,1])
    parseReply()

def writehex(hexbytes):
    print('writing ',end='')
    for i in bytearray.fromhex(hexbytes):
        print(hex(i),end=' ')
        s.write(i)
        time.sleep(0.01)

print('rav4dash.py started at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
initBCS()
print('initBCS() success at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
totalEnergy = 0.0 # watt seconds aka joules
timeStarted = time.time()
failedParseReplies = 0 # count how many failures to parse we've had
loopTime = time.time()
while(failedParseReplies < 5):
    sendPacket(BCS,[0x21,1]) # request voltage
    v = parseReply(printout=False)
    sendPacket(BCS,[0x21,3]) # request amperage
    a = parseReply(printout=False)
    if v and a:
        volts = int.from_bytes(v[5:7], byteorder='big', signed=True)/10.0   # (v[5]*256+v[6])/10
        amps = int.from_bytes(a[5:7], byteorder='big', signed=True)/10.0   # ((a[5]*256+a[6])-65535)/10
        watts = volts * amps
        if volts != 499.5 and amps != 400:
            totalEnergy += watts * ( time.time() - loopTime ) # add energy from each round
        loopTime = time.time() # update timer
        print("Volts: "+str(volts)+"	Amps: "+str(amps)+"	Watts: "+str(int(watts))+"	Wh: "+str(int(totalEnergy/3600)))
    else:
        failedParseReplies += 1
        print("timed out querying for volts or amps, failedParseReplies = "+str(failedParseReplies))
    time.sleep(1)

#s.setRTS(False) # True is +5.15v, False is -5.15v
exit() # RTS will go to False upon exit
