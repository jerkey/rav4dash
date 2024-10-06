#!/usr/bin/env python3

import serial
import time
import os

config=open('rav4dash.conf','r').read().splitlines()
SERIAL=config[0] # first line of rav4dash.conf should be like /dev/ttyS4
CGIURL=config[1] # second line of rav4dash.conf should be like https://website.com/cgi-bin/logcar.sh

# RTS will go True upon opening serial port, and False when program closes
serialPort = serial.Serial(port=SERIAL,baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=2000, xonxoff=0, rtscts=0)

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
        #print('.',end='')
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
        serialPort.read_all() # print("all: "+str(serialPort.read_all())) # throw away whatever is in the buffer
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

def requestSignedInt(target, requestBytes):
    sendPacket(target,requestBytes)
    reply = parseReply(printout=False)
    if reply:
        return int.from_bytes(reply[5:7], byteorder='big', signed=True)
    else:
        return False

IPADDRESS=''
WIFINETWORK=''
def getIPandWifi():
    global IPADDRESS, WIFINETWORK
    try:
        IPADDRESS = os.popen('timeout 4 ip -br -4 a | grep -m1 \'^w\'').read().split(' ')[-2].split('/')[0]
    except:
        IPADDRESS = 'NO_IP_ADDRESS'
    try:
        WIFINETWORK = os.popen('iwconfig 2>&1 | grep -m1 \'^w\'').read().split('"')[1]
    except:
        WIFINETWORK = 'NO_WIFI_NETWORK'
statusfile = open('rav4dash.status','w') # we overwrite this with the latest
print('rav4dash.py started at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
getIPandWifi()
initBCS()
print('initBCS() success at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
print('IP address is '+IPADDRESS+' on wifi network '+WIFINETWORK)
totalEnergy = 0.0 # watt seconds aka joules
timeStarted = time.time()
failedParseReplies = 0 # count how many failures to parse we've had
webUpdateTime = 0 # we'll use this to remember when we last sent a web update
loopTime = time.time()

#print('req dtcs:',end='	')
#sendPacket(BCS,[0x13]) # request DTCs
#time.sleep(1)
#print(parseReply())
#print('clear dtcs:',end='	')
#sendPacket(BCS,[0x14]) # CLEAR DTCs
#time.sleep(1)
#print(parseReply())
#print('req dtcs:',end='	')
#sendPacket(BCS,[0x13]) # request DTCs
#time.sleep(1)
#print(parseReply())

chargeStopped = False  # did we brusastop yet?
while(failedParseReplies < 5):
    v = requestSignedInt(BCS,[0x21,1]) # request voltage
    a = requestSignedInt(BCS,[0x21,3]) # request amperage
    s = requestSignedInt(BCS,[0x21,4]) # request state of charge
    t = requestSignedInt(BCS,[0x21,6]) # request battery pack temperature
    if (s > 990) and (chargeStopped == False): # in the "after-magne-charge but still plugged in" state, the above requests are answered once per initBCS()
        os.system("brusastop")
        os.system('timeout 5 curl -sG '+CGIURL+' --data-urlencode "charge is complete, stopping charger"' )
        chargeStopped = True
        time.sleep(5)
        os.system("ignition_off.sh") # turn off vehicle
    if v and s and t: # a is 0 in the "after-magne-charge but still plugged in" state
        failedParseReplies = 0; # reset fail counter
        volts = v/10.0
        amps = a/10.0
        soc = s/10.0
        tp = t/100.0
        watts = volts * amps
        if volts != 499.5 and amps != 400:
            totalEnergy += watts * ( time.time() - loopTime ) # add energy from each round
        loopTime = time.time() # update timer
        printString = "V:"+str(volts)+"	A:"+str(amps)+"	W:"+str(int(watts))+"	Wh:"+str(int(totalEnergy/3600))+"	SOC:"+str(soc)+"	T:"+str(tp)
        print(printString)
        statusfile.seek(0)
        statusfile.write(printString)
        statusfile.truncate()
        statusfile.flush()
        if (time.time() - webUpdateTime) > 60: # time in seconds between web updates
            getIPandWifi()
            os.system('timeout 3 curl -sG '+CGIURL+' --data-urlencode "' + printString + '	' + IPADDRESS + '	' + WIFINETWORK + '"' ) # timeout after 3 seconds
            webUpdateTime = time.time() # reset timer
        #gv = getModuleVoltages()
        #print(str(gv)+' '+str(sum(gv)))
    else:
        failedParseReplies += 1
        print('vRaw:'+str(v)) '	aRaw:'+str(a) '	sRaw:'+str(s) '	tRaw:'+str(t))
        print("timed out querying for volts or amps, failedParseReplies = "+str(failedParseReplies))
    time.sleep(1)

#serialPort.setRTS(False) # True is +5.15v, False is -5.15v
exit() # RTS will go to False upon exit
