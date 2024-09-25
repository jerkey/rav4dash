#!/usr/bin/env python3

import serial
import time

config=open('bmswatch.conf','r').read().splitlines()
SERIAL=config[0] # first line of bmswatch.conf should be like /dev/ttyS2
logfile=open('bmslog_'+time.strftime('%Y%m%d%H%M%S')+'.log','w')
serialPort = serial.Serial(port=SERIAL,baudrate=2400, bytesize=8, parity='N', stopbits=1, timeout=5000, xonxoff=0, rtscts=0, dsrdtr=0, write_timeout=0.1)

outboundBMSpacket = [1,2,3]

def parseBMSpacket(printout=True):
    a = []
    a.append(0)
    while a[0] != 255:
        r = serialPort.read(1)
        if len(r) == 1:
            a[0] = r[0]
    a += serialPort.read(1)     # read the length byte
    a += serialPort.read(a[1])  # read that number more bytes
    if len(a) != 62:
        print("expected 62 bytes but got "+str(len(a)))
    if a[0] == 0xff and a[1] == 0x3c and a[2] == 0x31:
        xorsum = 0
        for i in a[1:a[1]]:
            xorsum = xorsum ^ i
        if xorsum != a[(a[1]+1)]:
            print("xorsum is "+str(a[(a[1]+1)])+" but expected "+str(xorsum)+" diff is "+str(abs(xorsum - a[(a[1]+1)])))
        else: # XORsum is valid
            outboundBMSpacket = a # update what we will send out
        serialPort.write(bytearray(outboundBMSpacket)) # send packet out the serial port to the waiting BECM (even if it's stale)
        batteryVoltages = []
        batteryTotal = 0
        for i in range(24):
            volts = (a[i*2+3] + a[i*2+4]*256) / 1000
            batteryVoltages.append(volts)
            batteryTotal += volts
        tempSensors = []
        for i in range(24,28):
            temp = (a[i*2+3] + a[i*2+4]*256) / 1000
            tempSensors.append(temp)
        if printout:
            #print(batteryVoltages, end='\t'+f"{batteryTotal:.5g}"+'\n')
            print(tempSensors,end='\ttot:'+f"{batteryTotal:.5g}"+'\t')
            print('max:'+f"{max(batteryVoltages):.4g}"+'\tmin:'+f"{min(batteryVoltages):.4g}"+'\tavg:'+f"{batteryTotal/24:.4g}")
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

def getElconStats():
    try:
        stats = open('/tmp/elconv','r').readlines()[0].rstrip().split('\t')
    except:
        return ',,'
    return str(stats[0])+','+str(stats[1])+','

statusfile = open('bmsvoltages.txt','w') # we overwrite this with the latest
print('bmswatch.py started at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
timeStarted = time.time()
failedParseReplies = 0 # count how many failures to parse we've had
while(failedParseReplies < 5):
    time.sleep(0.1) # can't use control-C to interrupt without this pause
    try:
        batteryVoltages, tempSensors = parseBMSpacket()#printout=False)
        printString = ''
        for i in batteryVoltages:
            printString += str(i)+','
        printString += getElconStats()
        #print(printString)
        logfile.write(printString+'\n')
        logfile.flush()
        statusfile.seek(0)
        statusfile.write(printString)
        statusfile.truncate()
        statusfile.flush()
    except:
        print('.',end='')
        #failedParseReplies += 1

