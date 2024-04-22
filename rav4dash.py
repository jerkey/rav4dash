#!/usr/bin/env python3

import serial
import time
import os

# RTS will go True upon opening serial port, and False when program closes
serialPort = serial.Serial(port='/dev/ttyS4',baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=2000, xonxoff=0, rtscts=0)

BCS = 0xD5 # battery controller
ECS = 0x16 # engine controller

lastFreezeFrame = 0 # alternate between 0 and 1 ???

def sendPacket(destination, data):
    toSend = [0x80 + len(data), destination, 0xF1] + data
    checksum = 0
    for i in toSend:
        checksum += i;
    toSend.append(checksum % 256)
    serialPort.write(bytearray(toSend))
    readback = serialPort.read(len(toSend)) # serialPort.write() returns number of bytes sent
    if readback != bytearray(toSend):
        print("sent "+bytearray(toSend).hex()+" but echo was "+readback.hex())

def parseReply(printout=True):
    a = serialPort.read_all()
    startParseTime = time.time()
    while len(a) == 0 and (time.time() - startParseTime) < 5: # timeout in seconds
        print('.',end='')
        time.sleep(0.1)
        a = serialPort.read_all()
    if len(a) == 0:
        serialPort.read_all() # clear buffer
        return False
    if a[0] > 0x87 or a[0] < 0x81:
        print("first byte returned was "+hex(a[0])+" expected 0x81-0x87")
        return False
    if a[0] & 15 != len(a) - 4:
        print("strange, expected "+str((a[0] & 15) + 4)+" bytes but got "+str(len(a))+", reading for a while and printing all:",end='')
        time.sleep(1)
        a += serialPort.read_all()
        print(a.hex())
        return a
    checksum = 0
    for i in a[0:(3 + a[0] & 15)]:
        checksum += i;
    checksum %= 256
    if checksum != a[(a[0] & 15) + 3]:
        print("checksum is wrong, was "+str(a[(a[0] & 15) + 3])+" but expected "+str(checksum))
        return False
    if printout:
        if a[2] == ECS:
            print("ECS says: ",end='')
        if a[2] == BCS:
            print("BCS says: ",end='')
        print(a[3:(3 + a[0] & 15)].hex())
    return a

def initECS():
    serialPort.write(bytearray.fromhex('00'))
    serialPort.break_condition = True # https://forums.raspberrypi.com/viewtopic.php?t=239406
    time.sleep(0.035)
    serialPort.break_condition = False
    serialPort.write(bytearray.fromhex('00'))
    time.sleep(0.01)
    serialPort.read_all() # throw away whatever is in the buffer
    sendPacket(ECS,[0x81])
    parseReply()
    sendPacket(ECS,[0x12,0x1F,0])
    parseReply()
    sendPacket(ECS,[0x12,0x1F,1])
    parseReply()

def initBCS():
    initBCSStatus = False
    while initBCSStatus == False:
        serialPort.write(bytearray.fromhex('00'))
        serialPort.break_condition = True # https://forums.raspberrypi.com/viewtopic.php?t=239406
        time.sleep(0.035)
        serialPort.break_condition = False
        serialPort.write(bytearray.fromhex('00'))
        time.sleep(0.01)
        print("all: "+str(serialPort.read_all())) # throw away whatever is in the buffer
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
        serialPort.write(i)
        time.sleep(0.01)

def getModuleVoltages():
    global lastFreezeFrame
    sendPacket(BCS,[0x12,2,lastFreezeFrame]) # request freeze frame 0
    parseReply()#printout=False)
    moduleVoltages = []
    lastFreezeFrame ^= 1 # alternate lastFreezeFrame between 0 and 1
    for i in [10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,    33,34]: # 0x20 is something else, 25.2 ?
        sendPacket(BCS,[0x12, i, lastFreezeFrame]) # request module voltage from ff0
        mv = parseReply(printout=False)
        moduleVoltages.append(mv[6]/10.0)
    return moduleVoltages

print('rav4dash.py started at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
initBCS()
print('initBCS() success at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
totalEnergy = 0.0 # watt seconds aka joules
timeStarted = time.time()
failedParseReplies = 0 # count how many failures to parse we've had
webUpdateTime = 0 # we'll use this to remember when we last sent a web update
loopTime = time.time()
#sendPacket(BCS,[0x13]) # request DTCs
#dtc = parseReply()
while(failedParseReplies < 5):
    sendPacket(BCS,[0x21,1]) # request voltage
    v = parseReply(printout=False)
    sendPacket(BCS,[0x21,3]) # request amperage
    a = parseReply(printout=False)
    sendPacket(BCS,[0x21,4]) # request state of charge
    s = parseReply(printout=False)
    if v and a:
        volts = int.from_bytes(v[5:7], byteorder='big', signed=True)/10.0   # (v[5]*256+v[6])/10
        amps = int.from_bytes(a[5:7], byteorder='big', signed=True)/10.0   # ((a[5]*256+a[6])-65535)/10
        soc = int.from_bytes(s[5:7], byteorder='big', signed=True)/10.0   #
        watts = volts * amps
        if volts != 499.5 and amps != 400:
            totalEnergy += watts * ( time.time() - loopTime ) # add energy from each round
        loopTime = time.time() # update timer
        printString = "Volts: "+str(volts)+"	Amps: "+str(amps)+"	Watts: "+str(int(watts))+"	Wh: "+str(int(totalEnergy/3600)) + "	SOC: " + str(soc)
        print(printString)
        if (time.time() - webUpdateTime) > 60: # timeout in seconds
            os.system('curl -G https://website.org/cgi-bin/darbo --data-urlencode "' + printString + '"' )
            webUpdateTime = time.time() # reset timer
        #gv = getModuleVoltages()
        #print(str(gv)+' '+str(sum(gv)))
    else:
        failedParseReplies += 1
        print("timed out querying for volts or amps, failedParseReplies = "+str(failedParseReplies))
    time.sleep(1)

#serialPort.setRTS(False) # True is +5.15v, False is -5.15v
exit() # RTS will go to False upon exit
