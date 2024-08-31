#!/usr/bin/env python3

import serial
import time

config=open('bmswatch.conf','r').read().splitlines()
SERIAL=config[0] # first line of bmswatch.conf should be like /dev/ttyS2

serialPort = serial.Serial(port=SERIAL,baudrate=2400, bytesize=8, parity='N', stopbits=1, timeout=2000, xonxoff=0, rtscts=0)


def parseBMSpacket(printout=True):
    a = serialPort.read_all()
    startParseTime = time.time()
    while len(a) == 0 and (time.time() - startParseTime) < 5: # timeout in seconds
        #print('.',end='')
        time.sleep(0.1)
        a = serialPort.read_all()
    if len(a) == 0:
        return False
    print() # NEWLINE
    if len(a) != 62:
        print("expected 62 bytes but got "+str(len(a))+", reading for a while and printing all:",end='')
        time.sleep(1)
        a += serialPort.read_all()
        print(a.hex())
        return a
    if a[0] == 0xff and a[1] == 0x3c and a[2] == 0x31:
        checksum = 0
        for i in a[0:(1 + a[1])]:
            checksum = (i + checksum) % 256
        print("checksum is "+str(a[(a[1]+1)])+" but expected "+str(checksum))
        batteryVoltages = []
        for i in range(24):
            volts = (a[i+2] + a[i+3]*256) / 1000
            batteryVoltages.append(volts)
        tempSensors = []
        for i in range(24,28):
            temp = (a[i+2] + a[i+3]*256) / 1000
            tempSensors.append(temp)
        if printout:
            print(batteryVoltages)
            print(tempSensors)
        return batteryVoltages, tempSensors
    else:
        print("first 3 bytes returned were "+hex(a[0:3])+" expected ff 3c 31")
        return False

def requestSignedInt(target, requestBytes):
    sendPacket(target,requestBytes)
    reply = parseReply(printout=False)
    if reply:
        return int.from_bytes(reply[5:7], byteorder='big', signed=True)
    else:
        return False

tatusfile = open('bmsvoltages.txt','w') # we overwrite this with the latest
print('bmswatch.py started at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
timeStarted = time.time()
failedParseReplies = 0 # count how many failures to parse we've had
while(failedParseReplies < 5):
    try:
        batteryVoltages, tempSensors = parseBMSpacket()
    except:
        print('.')
        #failedParseReplies += 1

