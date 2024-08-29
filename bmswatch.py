#!/usr/bin/env python3

import serial
import time

config=open('bmswatch.conf','r').read().splitlines()
SERIAL=config[0] # first line of bmswatch.conf should be like /dev/ttyS2

serialPort = serial.Serial(port=SERIAL,baudrate=2400, bytesize=8, parity='N', stopbits=1, timeout=2000, xonxoff=0, rtscts=0)


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
        WIFINETWORK = os.popen('iwconfig 2>&1 | grep -m1 \'^w\'').read().split('"')[-2]
    except:
        WIFINETWORK = 'NO_WIFI_NETWORK'
statusfile = open('statusfile.txt','w') # we overwrite this with the latest
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
#sendPacket(BCS,[0x13]) # request DTCs
#dtc = parseReply()
chargeStopped = False  # did we brusastop yet?
while(failedParseReplies < 5):
    v = requestSignedInt(BCS,[0x21,1]) # request voltage
    a = requestSignedInt(BCS,[0x21,3]) # request amperage
    s = requestSignedInt(BCS,[0x21,4]) # request state of charge
    if (s > 990) and (chargeStopped == False):
        os.system("brusastop")
        os.system('timeout 5 curl -sG '+CGIURL+' --data-urlencode "charge is complete, stopping charger"' )
        chargeStopped = True
        time.sleep(5)
        os.system("ignition_off.sh") # turn off vehicle
    t = requestSignedInt(BCS,[0x21,6]) # request battery pack temperature
    if v and a and s and t:
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
        print("timed out querying for volts or amps, failedParseReplies = "+str(failedParseReplies))
    time.sleep(1)

#serialPort.setRTS(False) # True is +5.15v, False is -5.15v
exit() # RTS will go to False upon exit

ff 3c 31 20 32 02 32 0b 32 29 32 39 32 54 32 6c 32 6c 32 5d 32 45 32 23 32 57 32 6a 2c 3f 32 2f 32 11 32 1a 32 20 32 2c 32 26 32 17 32 17 32 0e 32 14 32 fb 7d 6a 7f 1c 7e 0a 80 00 00 28 
ff 3c 31 23 32 05 32 05 32 29 32 39 32 57 32 69 32 69 32 5d 32 45 32 23 32 57 32 67 2c 3f 32 2c 32 11 32 1d 32 20 32 2c 32 26 32 17 32 1a 32 0e 32 14 32 fb 7d 6a 7f 22 7e 10 80 00 00 01 
ff 3c 31 23 32 02 32 0b 32 26 32 39 32 57 32 69 32 6c 32 5d 32 45 32 23 32 54 32 6a 2c 3f 32 2f 32 11 32 1a 32 20 32 2c 32 26 32 17 32 17 32 0e 32 14 32 fb 7d 6a 7f 1c 7e 10 80 00 00 3b 
ff 3c 31 20 32 05 32 11 32 26 32 39 32 54 32 6c 32 6c 32 5d 32 45 32 20 32 57 32 67 2c 3f 32 2c 32 11 32 1d 32 20 32 2c 32 26 32 17 32 1a 32 0e 32 14 32 fb 7d 64 7f 22 7e 10 80 00 00 17 
ff 3c 31 23 32 05 32 08 32 29 32 39 32 57 32 69 32 69 32 5d 32 45 32 20 32 5a 32 6a 2c 3f 32 2c 32 11 32 1a 32 20 32 2c 32 26 32 17 32 17 32 0e 32 14 32 fb 7d 6a 7f 22 7e 15 80 00 00 00 
ff 3c 31 20 32 02 32 0b 32 26 32 39 32 57 32 69 32 6c 32 5d 32 45 32 23 32 57 32 67 2c 3f 32 2f 32 11 32 1d 32 1d 32 2c 32 26 32 17 32 17 32 0e 32 14 32 fb 7d 64 7f 1c 7e 15 80 00 00 07 
ff 3c 31 20 32 02 32 0e 32 29 32 39 32 54 32 69 32 69 32 5d 32 45 32 20 32 57 32 67 2c 3f 32 2c 32 11 32 1a 32 1d 32 2c 32 26 32 17 32 17 32 0e 32 14 32 fb 7d 6a 7f 22 7e 10 80 00 00 39 
ff 3c 31 23 32 08 32 05 32 29 32 36 32 54 32 69 32 69 32 5d 32 45 32 20 32 5a 32 64 2c 3f 32 2f 32 11 32 1a 32 20 32 2c 32 26 32 17 32 17 32 0e 32 14 32 fb 7d 6a 7f 1c 7e 10 80 00 00 3a 
ff 3c 31 20 32 ff 31 05 32 26 32 39 32 54 32 69 32 6c 32 5a 32 45 32 23 32 54 32 67 2c 3f 32 2c 32 11 32 1a 32 1d 32 2c 32 26 32 17 32 17 32 0e 32 14 32 fb 7d 6a 7f 1c 7e 10 80 00 00 ff 
ff 3c 31 20 32 02 32 05 32 26 32 36 32 54 32 69 32 69 32 5d 32 45 32 20 32 57 32 67 2c 3c 32 2c 32 0e 32 1a 32 20 32 2c 32 26 32 14 32 17 32 0e 32 11 32 fb 7d 6a 7f 22 7e 0a 80 00 00 0f 
ff 3c 31 23 32 05 32 05 32 26 32 36 32 54 32 69 32 69 32 5d 32 42 32 20 32 57 32 64 2c 3f 32 2c 32 11 32 1a 32 1d 32 2c 32 26 32 14 32 17 32 0b 32 14 32 fb 7d 6a 7f 1c 7e 0a 80 00 00 10 
ff 3c 31 20 32 05 32 08 32 26 32 36 32 54 32 69 32 6c 32 5a 32 45 32 23 32 54 32 67 2c 3f 32 2c 32 0e 32 1a 32 20 32 2c 32 26 32 17 32 17 32 0e 32 11 32 fb 7d 6a 7f 1c 7e 0a 80 00 00 39 
ff 3c 31 20 32 02 32 05 32 26 32 36 32 54 32 69 32 69 32 5a 32 45 32 20 32 54 32 64 2c 3f 32 2c 32 0e 32 1a 32 1d 32 2c 32 26 32 14 32 17 32 0b 32 14 32 fb 7d 6a 7f 22 7e 0a 80 00 00 36 
ff 3c 31 26 32 02 32 05 32 26 32 36 32 54 32 69 32 69 32 5d 32 42 32 20 32 54 32 67 2c 3c 32 2c 32 0e 32 1a 32 1d 32 2c 32 26 32 14 32 17 32 0e 32 11 32 fb 7d 6a 7f 1c 7e 15 80 00 00 11 
ff 3c 31 20 32 ff 31 05 32 23 32 36 32 54 32 69 32 6c 32 5a 32 45 32 23 32 54 32 64 2c 3f 32 2c 32 0e 32 1a 32 1d 32 2c 32 26 32 14 32 17 32 0b 32 11 32 fb 7d 6a 7f 1c 7e 10 80 00 00 ea 
ff 3c 31 23 32 02 32 02 32 26 32 36 32 54 32 69 32 69 32 5d 32 45 32 20 32 54 32 67 2c 3c 32 2c 32 0e 32 1a 32 1d 32 2c 32 23 32 14 32 17 32 0e 32 11 32 fb 7d 6a 7f 22 7e 10 80 00 00 2a 
ff 3c 31 23 32 ff 31 02 32 26 32 36 32 54 32 66 32 69 32 5d 32 42 32 20 32 54 32 64 2c 3f 32 2c 32 0e 32 1a 32 1d 32 2c 32 26 32 14 32 17 32 0b 32 11 32 fb 7d 64 7f 22 7e 10 80 00 00 d2 
ff 3c 31 20 32 ff 31 05 32 23 32 36 32 51 32 69 32 6c 32 5a 32 42 32 20 32 54 32 67 2c 3c 32 2c 32 0e 32 1a 32 1d 32 2c 32 23 32 14 32 14 32 0b 32 11 32 fb 7d 6a 7f 1c 7e 0a 80 00 00 f7 
ff 3c 31 20 32 ff 31 02 32 26 32 36 32 54 32 69 32 69 32 5a 32 45 32 20 32 54 32 64 2c 3c 32 2c 32 0e 32 1a 32 1d 32 2c 32 26 32 14 32 17 32 0e 32 11 32 fb 7d 6a 7f 22 7e 0a 80 00 00 cc 
ff 3c 31 23 32 ff 31 02 32 23 32 36 32 54 32 66 32 69 32 5a 32 42 32 20 32 54 32 67 2c 3f 32 2c 32 0e 32 1a 32 1d 32 2c 32 23 32 14 32 17 32 0b 32 11 32 fb 7d 6a 7f 22 7e 0a 80 00 00 c2 
ff 3c 31 1d 32 ff 31 08 32 23 32 36 32 54 32 69 32 6c 32 5a 32 42 32 20 32 54 32 64 2c 3c 32 2c 32 0e 32 1a 32 1d 32 2c 32 26 32 14 32 14 32 0e 32 11 32 fb 7d 6a 7f 22 7e 0a 80 00 00 ff 
ff 3c 31 20 32 ff 31 02 32 26 32 32 32 54 32 69 32 69 32 5a 32 42 32 20 32 54 32 64 2c 3f 32 2c 32 0e 32 1a 32 1a 32 2c 32 23 32 14 32 17 32 0b 32 11 32 fb 7d 6a 7f 22 7e 0a 80 00 00 cb 
ff 3c 31 20 32 fc 31 02 32 23 32 36 32 54 32 66 32 69 32 5a 32 42 32 20 32 54 32 64 2c 3c 32 2c 32 0e 32 1a 32 1d 32 2c 32 26 32 14 32 14 32 0e 32 11 32 01 7e 6a 7f 22 7e 0a 80 00 00 38 
ff 3c 31 1d 32 ff 31 02 32 23 32 36 32 54 32 66 32 69 32 5a 32 42 32 20 32 54 32 64 2c 3f 32 2c 32 0e 32 1a 32 1d 32 2c 32 23 32 14 32 17 32 0b 32 11 32 fb 7d 6a 7f 22 7e 05 80 00 00 f0 
ff 3c 31 20 32 ff 31 02 32 26 32 36 32 54 32 69 32 69 32 5a 32 42 32 20 32 57 32 67 2c 3c 32 2c 32 0e 32 17 32 1d 32 29 32 23 32 14 32 14 32 0e 32 11 32 fb 7d 6a 7f 22 7e 00 80 00 00 cf 
ff 3c 31 1d 32 fc 31 02 32 23 32 36 32 54 32 66 32 69 32 5a 32 42 32 20 32 54 32 64 2c 3f 32 2c 32 0e 32 1a 32 1a 32 2c 32 23 32 14 32 14 32 0b 32 11 32 fb 7d 6a 7f 22 7e fa 7f 00 00 f7 
ff 3c 31 1d 32 ff 31 05 32 23 32 36 32 51 32 69 32 69 32 5a 32 42 32 20 32 54 32 67 2c 3c 32 2c 32 0e 32 17 32 1d 32 29 32 23 32 14 32 14 32 0e 32 11 32 fb 7d 6a 7f 22 7e f4 7f 00 00 fd 
ff 3c 31 20 32 ff 31 02 32 26 32 32 32 54 32 69 32 69 32 5a 32 42 32 1d 32 57 32 64 2c 3c 32 29 32 0e 32 1a 32 1d 32 2c 32 23 32 14 32 17 32 0b 32 11 32 fb 7d 6a 7f 22 7e f4 7f 00 00 f5 
ff 3c 31 1d 32 fc 31 02 32 23 32 36 32 54 32 66 32 69 32 5a 32 42 32 20 32 54 32 67 2c 3c 32 2c 32 0e 32 17 32 1d 32 29 32 23 32 14 32 14 32 0b 32 11 32 fb 7d 6a 7f 1c 7e f4 7f 00 00 c8 
ff 3c 31 1d 32 ff 31 05 32 23 32 36 32 51 32 69 32 69 32 5a 32 42 32 1d 32 54 32 64 2c 3c 32 2c 32 0e 32 1a 32 1a 32 29 32 23 32 14 32 14 32 0b 32 11 32 fb 7d 6a 7f 22 7e f4 7f 00 00 cc 
ff 3c 31 20 32 fc 31 02 32 23 32 32 32 54 32 69 32 69 32 5a 32 42 32 20 32 57 32 64 2c 3c 32 29 32 0e 32 17 32 1d 32 29 32 23 32 14 32 14 32 0b 32 11 32 fb 7d 6a 7f 22 7e f4 7f 00 00 c5 
ff 3c 31 1d 32 fc 31 02 32 23 32 36 32 51 32 66 32 69 32 57 32 42 32 20 32 54 32 64 2c 3c 32 2c 32 0b 32 1a 32 1d 32 29 32 23 32 14 32 14 32 0b 32 11 32 fb 7d 6a 7f 1c 7e f4 7f 00 00 cb 
ff 3c 31 1d 32 ff 31 02 32 23 32 32 32 51 32 69 32 66 32 57 32 42 32 1d 32 54 32 64 2c 3c 32 29 32 0e 32 17 32 1a 32 2c 32 23 32 14 32 14 32 0b 32 11 32 fb 7d 6a 7f 22 7e ef 7f 00 00 db 
ff 3c 31 20 32 ff 31 02 32 26 32 32 32 51 32 66 32 66 32 5a 32 42 32 20 32 54 32 61 2c 3c 32 2c 32 0b 32 1a 32 1d 32 29 32 23 32 11 32 14 32 0b 32 11 32 fb 7d 6a 7f 22 7e ef 7f 00 00 d3 
ff 3c 31 1d 32 fc 31 02 32 23 32 32 32 51 32 66 32 69 32 57 32 42 32 20 32 51 32 64 2c 3c 32 29 32 0e 32 17 32 1a 32 29 32 23 32 14 32 14 32 0b 32 11 32 fb 7d 6a 7f 1c 7e e9 7f 00 00 dd 
ff 3c 31 1d 32 ff 31 02 32 23 32 32 32 51 32 66 32 66 32 57 32 42 32 1d 32 54 32 61 2c 3c 32 29 32 0b 32 17 32 1d 32 29 32 23 32 11 32 14 32 0b 32 11 32 fb 7d 6a 7f 22 7e e9 7f 00 00 d5 
ff 3c 31 20 32 fc 31 02 32 23 32 32 32 51 32 66 32 66 32 5a 32 42 32 1d 32 54 32 61 2c 3c 32 29 32 0b 32 17 32 1a 32 2c 32 23 32 11 32 14 32 0b 32 11 32 fb 7d 6a 7f 22 7e e9 7f 00 00 e4 
ff 3c 31 1d 32 fc 31 02 32 1d 32 32 32 51 32 66 32 69 32 57 32 42 32 20 32 51 32 64 2c 3c 32 29 32 0b 32 17 32 1d 32 29 32 23 32 14 32 14 32 0b 32 0e 32 fb 7d 6a 7f 1c 7e e9 7f 00 00 fe 
ff 3c 31 1d 32 ff 31 ff 31 1d 32 32 32 51 32 66 32 66 32 5a 32 42 32 1d 32 51 32 61 2c 3c 32 29 32 0b 32 17 32 1a 32 29 32 23 32 11 32 14 32 08 32 11 32 fb 7d 6a 7f 22 7e e4 7f 00 00 14 
ff 3c 31 20 32 fc 31 02 32 23 32 32 32 51 32 66 32 66 32 5a 32 3f 32 1d 32 51 32 64 2c 39 32 29 32 0b 32 17 32 1a 32 29 32 23 32 14 32 14 32 0b 32 0e 32 fb 7d 6a 7f 22 7e e4 7f 00 00 8e 
ff 3c 31 1d 32 fc 31 02 32 1d 32 32 32 4e 32 66 32 69 32 57 32 42 32 1d 32 51 32 61 2c 3c 32 29 32 0b 32 1a 32 1a 32 29 32 23 32 11 32 14 32 08 32 11 32 fb 7d 6a 7f 22 7e de 7f 00 00 c3 
ff 3c 31 1d 32 fc 31 ff 31 1a 32 32 32 51 32 66 32 66 32 5a 32 42 32 1d 32 51 32 64 2c 39 32 29 32 0e 32 17 32 1a 32 29 32 23 32 11 32 11 32 08 32 11 32 fb 7d 6a 7f 22 7e de 7f 00 00 2a 
ff 3c 31 20 32 fc 31 ff 31 20 32 32 32 51 32 66 32 66 32 57 32 3f 32 1d 32 51 32 61 2c 3c 32 29 32 0b 32 17 32 1a 32 29 32 23 32 11 32 14 32 08 32 0e 32 fb 7d 6a 7f 22 7e de 7f 00 00 42 
ff 3c 31 1a 32 fc 31 ff 31 1d 32 32 32 51 32 66 32 69 32 57 32 42 32 1d 32 51 32 64 2c 3c 32 26 32 0b 32 17 32 1a 32 29 32 23 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 22 7e de 7f 00 00 38 
ff 3c 31 1d 32 fc 31 ff 31 20 32 2f 32 51 32 66 32 66 32 57 32 3f 32 1d 32 51 32 61 2c 39 32 29 32 0b 32 17 32 1a 32 29 32 23 32 11 32 14 32 0b 32 11 32 fb 7d 6a 7f 22 7e de 7f 00 00 7b 
ff 3c 31 1d 32 f8 31 ff 31 20 32 32 32 51 32 66 32 66 32 57 32 3f 32 1d 32 51 32 61 2c 39 32 29 32 0b 32 17 32 17 32 29 32 23 32 11 32 11 32 08 32 11 32 fb 7d 6a 7f 22 7e de 7f 00 00 69 
ff 3c 31 1a 32 fc 31 ff 31 1a 32 32 32 4e 32 66 32 66 32 57 32 3f 32 1d 32 51 32 61 2c 39 32 29 32 0b 32 17 32 1a 32 29 32 23 32 11 32 11 32 0b 32 0e 32 fb 7d 6a 7f 22 7e de 7f 00 00 5e 
ff 3c 31 1d 32 fc 31 ff 31 1a 32 2f 32 51 32 66 32 66 32 57 32 3f 32 1d 32 54 32 61 2c 3c 32 26 32 0b 32 17 32 17 32 29 32 20 32 11 32 14 32 08 32 11 32 fb 7d 6a 7f 22 7e e4 7f 00 00 79 
ff 3c 31 1a 32 f8 31 ff 31 20 32 32 32 51 32 63 32 66 32 57 32 3f 32 1d 32 51 32 61 2c 39 32 29 32 08 32 17 32 1a 32 26 32 23 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 22 7e e4 7f 00 00 4f 
ff 3c 31 1a 32 f8 31 ff 31 17 32 32 32 4e 32 66 32 66 32 57 32 42 32 1d 32 51 32 61 2c 39 32 26 32 0b 32 17 32 17 32 29 32 20 32 11 32 11 32 08 32 11 32 fb 7d 6a 7f 22 7e e4 7f 00 00 0d 
ff 3c 31 1d 32 f8 31 ff 31 1a 32 2f 32 51 32 66 32 66 32 57 32 3f 32 1d 32 54 32 61 2c 39 32 29 32 08 32 14 32 1a 32 26 32 23 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 22 7e e9 7f 00 00 61 
ff 3c 31 1a 32 f8 31 ff 31 1d 32 2f 32 51 32 63 32 66 32 57 32 3f 32 1d 32 51 32 5e 2c 39 32 26 32 08 32 17 32 17 32 29 32 20 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 1c 7e ef 7f 00 00 6b 
ff 3c 31 1a 32 f8 31 fc 31 14 32 32 32 4e 32 66 32 63 32 57 32 3f 32 1d 32 51 32 61 2c 39 32 29 32 0b 32 14 32 1a 32 26 32 20 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 22 7e e9 7f 00 00 69 
ff 3c 31 1a 32 f8 31 ff 31 17 32 2f 32 51 32 66 32 63 32 57 32 3f 32 1a 32 54 32 5e 2c 39 32 26 32 08 32 17 32 17 32 29 32 20 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 22 7e f4 7f 00 00 46 
ff 3c 31 1a 32 f8 31 ff 31 1d 32 32 32 4e 32 63 32 66 32 57 32 3f 32 1d 32 51 32 61 2c 39 32 26 32 0b 32 14 32 17 32 26 32 20 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 1c 7e f4 7f 00 00 42 
ff 3c 31 1a 32 f8 31 fc 31 14 32 2f 32 4e 32 63 32 63 32 57 32 3f 32 1a 32 51 32 5e 2c 39 32 26 32 08 32 17 32 17 32 26 32 23 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 22 7e f4 7f 00 00 55 
ff 3c 31 1a 32 f8 31 ff 31 1a 32 2c 32 4e 32 63 32 63 32 57 32 3f 32 1d 32 51 32 61 2c 39 32 26 32 08 32 14 32 17 32 29 32 20 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 22 7e fa 7f 00 00 62 
ff 3c 31 1a 32 f8 31 ff 31 14 32 2f 32 4e 32 63 32 66 32 57 32 3f 32 1d 32 4e 32 5e 2c 39 32 26 32 08 32 17 32 17 32 26 32 23 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 1c 7e fa 7f 00 00 7b 
ff 3c 31 1a 32 fc 31 fc 31 0b 32 2f 32 4e 32 63 32 63 32 57 32 42 32 1a 32 51 32 61 2c 39 32 26 32 0b 32 14 32 17 32 29 32 20 32 11 32 11 32 05 32 0e 32 fb 7d 6a 7f 22 7e fa 7f 00 00 03 
ff 3c 31 1a 32 f8 31 fc 31 17 32 2f 32 4e 32 63 32 63 32 57 32 3f 32 1a 32 51 32 5e 2c 39 32 26 32 08 32 14 32 17 32 26 32 23 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 22 7e 00 80 00 00 5e 
ff 3c 31 1a 32 f8 31 ff 31 11 32 2f 32 4e 32 63 32 66 32 57 32 3f 32 1d 32 4e 32 5e 2c 39 32 26 32 08 32 14 32 17 32 26 32 20 32 11 32 11 32 05 32 0e 32 fb 7d 6a 7f 22 7e fa 7f 00 00 4d 
ff 3c 31 1a 32 f8 31 fc 31 0b 32 2f 32 4e 32 63 32 63 32 57 32 3f 32 1a 32 51 32 5e 2c 36 32 26 32 08 32 14 32 17 32 26 32 20 32 11 32 11 32 08 32 0b 32 fb 7d 6a 7f 22 7e fa 7f 00 00 4e 
ff 3c 31 1d 32 f8 31 fc 31 17 32 29 32 4e 32 63 32 63 32 57 32 3f 32 1a 32 4e 32 5e 2c 39 32 26 32 08 32 14 32 17 32 26 32 20 32 11 32 11 32 05 32 0e 32 fb 7d 6a 7f 22 7e 00 80 00 00 4e 
ff 3c 31 1a 32 f8 31 fc 31 08 32 2c 32 4e 32 63 32 66 32 54 32 3f 32 1a 32 4e 32 61 2c 36 32 26 32 08 32 14 32 17 32 26 32 20 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 1c 7e 00 80 00 00 56 
ff 3c 31 1a 32 f8 31 f8 31 0b 32 2f 32 4e 32 63 32 63 32 57 32 3f 32 1a 32 4e 32 5e 2c 39 32 26 32 08 32 14 32 17 32 26 32 20 32 0e 32 11 32 05 32 0e 32 fb 7d 6a 7f 22 7e fa 7f 00 00 4d 
ff 3c 31 1d 32 f8 31 fc 31 0e 32 2c 32 4e 32 63 32 63 32 57 32 3c 32 1a 32 4e 32 61 2c 36 32 26 32 08 32 14 32 17 32 26 32 20 32 11 32 11 32 08 32 0e 32 fb 7d 6a 7f 22 7e 00 80 00 00 6c 
ff 3c 31 1a 32 f8 31 fc 31 08 32 2c 32 4e 32 63 32 66 32 54 32 3f 32 1a 32 4e 32 5e 2c 39 32 26 32 05 32 14 32 17 32 26 32 20 32 0e 32 11 32 05 32 0e 32 fb 7d 6a 7f 22 7e fa 7f 00 00 42 
ff 3c 31 1a 32 f8 31 f8 31 08 32 2f 32 4e 32 63 32 63 32 54 32 3f 32 1a 32 4e 32 61 2c 36 32 26 32 08 32 14 32 17 32 26 32 20 32 0e 32 0e 32 05 32 0e 32 fb 7d 6a 7f 22 7e fa 7f 00 00 62 
ff 3c 31 1d 32 f8 31 fc 31 0e 32 29 32 4e 32 63 32 63 32 54 32 3c 32 1a 32 4e 32 5e 2c 36 32 26 32 05 32 14 32 17 32 23 32 20 32 0e 32 11 32 05 32 0b 32 fb 7d 6a 7f 22 7e fa 7f 00 00 4f 
ff 3c 31 17 32 f8 31 f8 31 08 32 2c 32 4e 32 63 32 66 32 54 32 3c 32 1a 32 4e 32 61 2c 36 32 26 32 08 32 14 32 17 32 26 32 20 32 11 32 0e 32 05 32 0e 32 fb 7d 6a 7f 22 7e fa 7f 00 00 75 
ff 3c 31 1a 32 f8 31 f8 31 08 32 2c 32 4e 32 63 32 63 32 54 32 3c 32 1a 32 51 32 5e 2c 36 32 26 32 05 32 14 32 17 32 23 32 20 32 0e 32 0e 32 08 32 0b 32 fb 7d 6a 7f 22 7e f4 7f 00 00 4c 
ff 3c 31 1d 32 f8 31 fc 31 11 32 26 32 4e 32 63 32 63 32 54 32 3c 32 1a 32 4e 32 5e 2c 39 32 26 32 08 32 14 32 14 32 26 32 20 32 0e 32 11 32 05 32 0e 32 fb 7d 6a 7f 22 7e f4 7f 00 00 50 
ff 3c 31 17 32 f8 31 f8 31 08 32 2c 32 4e 32 63 32 66 32 54 32 3c 32 1a 32 4e 32 5e 2c 36 32 23 32 05 32 14 32 17 32 23 32 20 32 0e 32 0e 32 08 32 0b 32 fb 7d 6a 7f 22 7e ef 7f 00 00 45 
ff 3c 31 17 32 f8 31 f8 31 05 32 2c 32 4e 32 63 32 63 32 54 32 3c 32 1a 32 51 32 5e 2c 39 32 26 32 08 32 14 32 14 32 26 32 1d 32 0e 32 11 32 05 32 0e 32 fb 7d 6a 7f 22 7e e9 7f 00 00 7f 
ff 3c 31 1a 32 f5 31 fc 31 0e 32 2c 32 4e 32 60 32 63 32 54 32 3c 32 1a 32 4e 32 5e 2c 36 32 26 32 05 32 11 32 17 32 23 32 20 32 0e 32 0e 32 08 32 0b 32 fb 7d 6a 7f 22 7e e9 7f 00 00 47 
ff 3c 31 17 32 f8 31 f8 31 05 32 29 32 4e 32 63 32 63 32 54 32 3c 32 1a 32 4e 32 5e 2c 39 32 23 32 05 32 14 32 14 32 26 32 20 32 0e 32 0e 32 05 32 0e 32 fb 7d 6a 7f 22 7e e4 7f 00 00 42 
ff 3c 31 17 32 f5 31 f8 31 08 32 26 32 4e 32 63 32 63 32 54 32 3c 32 1a 32 51 32 5e 2c 36 32 23 32 05 32 11 32 17 32 23 32 20 32 0e 32 0e 32 05 32 0b 32 fb 7d 6a 7f 22 7e e4 7f 00 00 5b 
ff 3c 31 17 32 f5 31 f8 31 0e 32 26 32 4e 32 60 32 63 32 54 32 3c 32 1a 32 4e 32 5e 2c 36 32 23 32 05 32 14 32 14 32 26 32 20 32 0e 32 0e 32 05 32 0b 32 fb 7d 6a 7f 1c 7e e4 7f 00 00 7c 
ff 3c 31 17 32 f8 31 f8 31 05 32 29 32 4b 32 60 32 63 32 54 32 3c 32 1a 32 4e 32 5e 2c 36 32 23 32 05 32 11 32 17 32 23 32 1d 32 0e 32 0e 32 05 32 0b 32 fb 7d 6a 7f 22 7e de 7f 00 00 4a 
ff 3c 31 17 32 f5 31 f8 31 0e 32 26 32 4e 32 60 32 63 32 54 32 3c 32 1a 32 51 32 5e 2c 39 32 23 32 05 32 14 32 14 32 23 32 20 32 0e 32 0e 32 05 32 0b 32 fb 7d 6a 7f 22 7e de 7f 00 00 6d 
ff 3c 31 17 32 f5 31 fc 31 0b 32 23 32 4b 32 60 32 63 32 54 32 3c 32 1a 32 4e 32 5e 2c 36 32 23 32 05 32 11 32 14 32 23 32 1d 32 0e 32 0e 32 05 32 0b 32 fb 7d 6a 7f 22 7e de 7f 00 00 44 
ff 3c 31 17 32 f5 31 f8 31 02 32 23 32 4b 32 60 32 63 32 54 32 3c 32 1a 32 4e 32 5e 2c 36 32 23 32 05 32 14 32 14 32 23 32 20 32 0e 32 0e 32 05 32 0b 32 fb 7d 6a 7f 22 7e de 7f 00 00 71 
ff 3c 31 17 32 f5 31 f8 31 02 32 1d 32 4e 32 60 32 60 32 54 32 3c 
ff 3c 31 f8 30 f2 30 e6 30 f8 30 11 31 2f 31 66 31 4b 31 41 31 35 31 23 31 47 31 67 2a 51 31 2f 31 04 31 1a 31 23 31 35 31 1d 31 0d 31 01 31 04 31 0d 31 86 7e 15 80 e4 7e a7 7f 00 00 27 
ff 3c 31 f8 30 e6 30 e3 30 f5 30 07 31 2f 31 5a 31 41 31 41 31 29 31 23 31 44 31 48 2a 47 31 2f 31 f5 30 17 31 23 31 23 31 20 31 04 31 f8 30 04 31 fe 30 86 7e 10 80 d9 7e ac 7f 00 00 db 
ff 3c 31 d0 30 c4 30 c7 30 d0 30 ef 30 1a 31 3e 31 2f 31 26 31 0a 31 0a 31 1d 31 cb 29 35 31 14 31 da 30 fe 30 fb 30 17 31 01 31 e6 30 e0 30 e3 30 e3 30 86 7e 10 80 d9 7e ac 7f 00 00 f0 
ff 3c 31 c7 30 ca 30 c7 30 cd 30 f2 30 14 31 3e 31 35 31 23 31 14 31 0a 31 1a 31 e0 29 32 31 14 31 e0 30 f8 30 fe 30 17 31 fb 30 ec 30 da 30 e3 30 ec 30 86 7e 15 80 df 7e a1 7f 00 00 3e 
ff 3c 31 c1 30 ca 30 be 30 cd 30 ef 30 0a 31 41 31 2f 31 1d 31 14 31 04 31 20 31 ce 29 29 31 14 31 d7 30 f5 30 04 31 0a 31 01 31 e6 30 d4 30 e6 30 dd 30 80 7e 10 80 ea 7e 9c 7f 00 00 04 
ff 3c 31 d4 30 ca 30 be 30 d4 30 ec 30 14 31 47 31 29 31 26 31 11 31 01 31 29 31 d4 29 35 31 14 31 da 30 fe 30 fb 30 14 31 01 31 e6 30 dd 30 e3 30 e3 30 86 7e 10 80 e4 7e a7 7f 00 00 c6 
ff 3c 31 f2 30 e0 30 e0 30 ef 30 01 31 2c 31 54 31 3e 31 3e 31 23 31 20 31 3b 31 45 2a 47 31 29 31 f8 30 0d 31 17 31 2c 31 14 31 01 31 f8 30 f8 30 04 31 86 7e 15 80 d9 7e ac 7f 00 00 a6 
ff 3c 31 07 31 fe 30 04 31 07 31 23 31 47 31 66 31 60 31 54 31 3e 31 3b 31 4e 31 b9 2a 5d 31 47 31 14 31 2c 31 3b 31 3b 31 35 31 1d 31 17 31 1d 31 17 31 86 7e 10 80 d9 7e a7 7f 00 00 29 
ff 3c 31 07 31 0d 31 0a 31 0d 31 2f 31 4b 31 72 31 6c 31 57 31 47 31 3e 31 54 31 d1 2a 6c 31 4b 31 1a 31 38 31 3b 31 47 31 3e 31 20 31 23 31 20 31 23 31 86 7e 10 80 e4 7e 96 7f 00 00 96 
ff 3c 31 a9 30 ac 30 9d 30 af 30 d4 30 f2 30 2c 31 14 31 07 31 fb 30 e9 30 07 31 5d 29 17 31 f5 30 be 30 da 30 dd 30 fb 30 dd 30 c7 30 b5 30 c1 30 ca 30 86 7e 15 80 ea 7e 9c 7f 00 00 6d 
ff 3c 31 c1 30 b5 30 ac 30 c1 30 da 30 01 31 35 31 17 31 14 31 fe 30 f5 30 1a 31 8e 29 1d 31 04 31 c7 30 e6 30 f2 30 fb 30 ef 30 d7 30 be 30 d4 30 cd 30 86 7e 10 80 e4 7e a1 7f 00 00 fc 
ff 3c 31 51 33 2a 33 42 33 30 33 17 33 17 33 11 33 1a 33 1d 33 0e 33 0b 33 27 33 ea 32 17 33 02 33 08 33 05 33 20 33 ea 32 0e 33 05 33 61 33 0e 33 17 33 8b 7e 10 80 df 7e a7 7f 00 00 67 
ff 3c 31 8b 31 81 31 8b 31 88 31 9d 31 b5 31 d1 31 ce 31 c2 31 af 31 ac 31 be 31 40 2d d1 31 b2 31 94 31 a3 31 ac 31 b5 31 a6 31 9a 31 a6 31 91 31 a0 31 86 7e 15 80 d9 7e 96 7f 00 00 d5 
ff 3c 31 26 31 2c 31 26 31 2c 31 4b 31 60 31 8e 31 85 31 72 31 66 31 5a 31 75 31 4b 2b 7e 31 69 31 38 31 4e 31 63 31 5d 31 5a 31 44 31 3b 31 44 31 41 31 80 7e 15 80 e4 7e 90 7f 00 00 26 
ff 3c 31 9d 30 9a 30 87 30 a0 30 c1 30 e9 30 23 31 04 31 fe 30 ec 30 dd 30 fe 30 bb 28 0a 31 ec 30 a6 30 d4 30 cd 30 ec 30 d7 30 b5 30 a6 30 b8 30 b2 30 86 7e 0a 80 ea 7e 96 7f 00 00 c5 
ff 3c 31 7b 30 6f 30 63 30 7b 30 9a 30 ca 30 01 31 e0 30 e0 30 c7 30 be 30 dd 30 47 28 e9 30 c4 30 8a 30 a9 30 a9 30 cd 30 a9 30 96 30 7b 30 8d 30 93 30 86 7e 15 80 df 7e a1 7f 00 00 88 
ff 3c 31 a9 30 9d 30 9d 30 a9 30 ca 30 f8 30 20 31 0d 31 07 31 ec 30 ec 30 fb 30 2c 29 0d 31 f5 30 b5 30 d4 30 e0 30 ef 30 dd 30 c4 30 ac 30 c1 30 bb 30 80 7e 15 80 d9 7e a1 7f 00 00 90 
ff 3c 31 e9 30 e9 30 e9 30 ec 30 0d 31 2f 31 57 31 4e 31 3b 31 2c 31 26 31 35 31 3f 2a 4e 31 2f 31 f5 30 1a 31 1d 31 2c 31 23 31 01 31 01 31 04 31 01 31 86 7e 10 80 df 7e 90 7f 00 00 ad 
ff 3c 31 e9 30 ef 30 e6 30 f2 30 11 31 2c 31 5d 31 4e 31 3e 31 32 31 20 31 41 31 51 2a 51 31 2c 31 01 31 17 31 1d 31 35 31 1a 31 07 31 01 31 fe 30 0a 31 86 7e 15 80 ea 7e 90 7f 00 00 aa 
ff 3c 31 f5 30 ec 30 e3 30 f8 30 0d 31 2f 31 60 31 44 31 41 31 2f 31 20 31 47 31 57 2a 4b 31 32 31 fb 30 17 31 26 31 29 31 20 31 0a 31 f8 30 07 31 04 31 86 7e 10 80 ea 7e 9c 7f 00 00 18 
ff 3c 31 fb 30 e9 30 e6 30 f5 30 07 31 32 31 5a 31 47 31 44 31 2c 31 26 31 41 31 4b 2a 4e 31 32 31 f8 30 1d 31 1d 31 2c 31 23 31 04 31 01 31 04 31 01 31 86 7e 10 80 d9 7e a1 7f 00 00 e0 
ff 3c 31 11 31 07 31 0d 31 11 31 2c 31 4e 31 6f 31 66 31 5d 31 44 31 44 31 54 31 ce 2a 69 31 47 31 1d 31 32 31 38 31 4e 31 35 31 26 31 26 31 1d 31 29 31 86 7e 15 80 d9 7e 96 7f 00 00 e5 
ff 3c 31 20 31 23 31 20 31 23 31 41 31 5d 31 85 31 7b 31 69 31 5d 31 51 31 66 31 2a 2b 75 31 60 31 32 31 44 31 57 31 54 31 4e 31 3b 31 35 31 38 31 38 31 80 7e 15 80 e4 7e 8b 7f 00 00 f9 
ff 3c 31 fc 31 e9 31 e9 31 ec 31 f2 31 f8 31 23 32 1a 32 11 32 0b 32 e9 31 1a 32 06 2e 17 32 02 32 e3 31 f8 31 05 32 ec 31 02 32 e9 31 08 32 ec 31 ec 31 86 7e 10 80 ef 7e 90 7f 00 00 cc 
ff 3c 31 c2 31 a9 31 a9 31 b8 31 be 31 d7 31 ff 31 e9 31 e9 31 d7 31 cb 31 f2 31 1f 2e f2 31 d4 31 bb 31 c8 31 d1 31 da 31 cb 31 be 31 d1 31 b8 31 c8 31 86 7e 15 80 e4 7e 9c 7f 00 00 91 
ff 3c 31 47 31 32 31 35 31 3e 31 51 31 78 31 97 31 8b 31 88 31 6c 31 69 31 81 31 8f 2b 8b 31 75 31 47 31 5a 31 6f 31 6c 31 63 31 54 31 4b 31 51 31 51 31 86 7e 15 80 d9 7e 9c 7f 00 00 6a 
ff 3c 31 07 31 04 31 04 31 07 31 26 31 4b 31 6c 31 66 31 57 31 44 31 41 31 51 31 8b 2a 66 31 4b 31 14 31 35 31 38 31 44 31 3b 31 1d 31 1a 31 20 31 1d 31 86 7e 10 80 df 7e 90 7f 00 00 ae 
ff 3c 31 c5 32 bc 32 c8 32 b9 32 b9 32 b0 32 bf 32 c5 32 b9 32 b9 32 a6 32 c5 32 bb 31 b9 32 9a 32 a0 32 9a 32 b0 32 94 32 a0 32 97 32 da 32 9a 32 ad 32 8b 7e 10 80 ef 7e 8b 7f 00 00 4a 
ff 3c 31 0b 33 f6 32 ff 32 fc 32 ed 32 e3 32 f9 32 f3 32 f3 32 f0 32 da 32 08 33 fa 34 e7 32 d4 32 da 32 cb 32 f6 32 bf 32 d7 32 da 32 14 33 da 32 e3 32 86 7e 15 80 ef 7e 90 7f 00 00 83 
ff 3c 31 36 33 0b 33 1d 33 17 33 02 33 02 33 0b 33 08 33 0e 33 ff 32 f9 32 20 33 5f 37 02 33 ed 32 ed 32 ed 32 0b 33 d7 32 fc 32 f0 32 36 33 f6 32 fc 32 80 7e 10 80 e4 7e 9c 7f 00 00 5e 
ff 3c 31 33 33 0e 33 2a 33 17 33 08 33 0b 33 0b 33 14 33 17 33 05 33 08 33 1d 33 32 3a 0b 33 f0 32 fc 32 f3 32 05 33 ea 32 f6 32 f6 32 3f 33 f6 32 0b 33 86 7e 15 80 df 7e 96 7f 00 00 d0 
ff 3c 31 cb 32 b9 32 cb 32 bc 32 c2 32 bf 32 c8 32 d7 32 c8 32 c2 32 bc 32 d1 32 68 38 bf 32 a9 32 a9 32 9d 32 c5 32 9d 32 a9 32 a9 32 d7 32 a6 32 b3 32 86 7e 15 80 e4 7e 8b 7f 00 00 d4 
ff 3c 31 4b 32 45 32 45 32 45 32 51 32 51 32 76 32 73 32 63 32 60 32 4e 32 6c 32 64 33 5a 32 45 32 29 32 39 32 4e 32 32 32 45 32 32 32 4e 32 39 32 32 32 8b 7e 10 80 f5 7e 8b 7f 00 00 19 
ff 3c 31 c5 31 b2 31 ac 31 bb 31 c5 31 d7 31 02 32 ec 31 ec 31 e0 31 d1 31 f8 31 93 2e ff 31 da 31 bb 31 ce 31 ce 31 e0 31 d1 31 c2 31 da 31 be 31 cb 31 86 7e 15 80 e4 7e 96 7f 00 00 e7 
ff 3c 31 8e 31 72 31 78 31 85 31 8e 31 b2 31 d1 31 bb 31 be 31 a6 31 a3 31 c5 31 92 2c c8 31 ac 31 8b 31 94 31 ac 31 a6 31 9d 31 94 31 94 31 8b 31 97 31 8b 7e 15 80 df 7e a1 7f 00 00 44 
ff 3c 31 81 31 6f 31 75 31 72 31 88 31 af 31 c2 31 c5 31 bb 31 a0 31 a0 31 ac 31 4f 2c c2 31 ac 31 7b 31 97 31 9d 31 9a 31 a3 31 85 31 8b 31 8b 31 85 31 8b 7e 15 80 d9 7e 96 7f 00 00 89 
ff 3c 31 6f 31 6f 31 6f 31 72 31 8b 31 a6 31 be 31 c5 31 ac 31 a6 31 9a 31 af 31 2d 2c c2 31 a0 31 78 31 91 31 8b 31 a6 31 94 31 81 31 91 31 7e 31 8b 31 8b 7e 1b 80 e4 7e 85 7f 00 00 90 
ff 3c 31 72 31 72 31 66 31 75 31 8e 31 a0 31 ce 31 c2 31 af 31 a6 31 91 31 b8 31 46 2c bb 31 a3 31 7e 31 8b 31 a0 31 9d 31 91 31 88 31 88 31 81 31 8b 31 8b 7e 15 80 ef 7e 90 7f 00 00 12 
ff 3c 31 88 31 6f 31 6c 31 78 31 81 31 a3 31 c8 31 b5 31 b5 31 a3 31 94 31 b8 31 36 2c bb 31 a9 31 78 31 91 31 9a 31 97 31 a3 31 81 31 88 31 88 31 7e 31 8b 7e 15 80 ea 7e 9c 7f 00 00 0d 
ff 3c 31 81 31 66 31 6f 31 78 31 85 31 a9 31 be 31 b5 31 b5 31 9a 31 9d 31 b8 31 2a 2c c5 31 a0 31 78 31 94 31 8b 31 a3 31 94 31 7e 31 91 31 7e 31 88 31 8b 7e 15 80 d9 7e a1 7f 00 00 d2 
ff 3c 31 54 31 47 31 4e 31 4e 31 6c 31 91 31 a9 31 a6 31 94 31 81 31 81 31 8e 31 95 2b a3 31 88 31 63 31 6c 31 81 31 85 31 72 31 6c 31 66 31 63 31 69 31 86 7e 1b 80 df 7e 9c 7f 00 00 0a 
ff 3c 31 e9 30 f2 30 e9 30 ef 30 17 31 2f 31 63 31 5a 31 44 31 3b 31 2c 31 3e 31 79 29 51 31 38 31 f8 30 1d 31 26 31 2c 31 29 31 0d 31 fb 30 0d 31 01 31 8b 7e 15 80 ea 7e 90 7f 00 00 53 
ff 3c 31 c4 30 c7 30 b5 30 cd 30 ef 30 0d 31 47 31 29 31 23 31 14 31 01 31 26 31 c5 28 35 31 0d 31 d4 30 fb 30 f2 30 17 31 fb 30 e0 30 d7 30 da 30 e0 30 8b 7e 15 80 ea 7e 9c 7f 00 00 24 
ff 3c 31 75 31 5d 31 60 31 6c 31 75 31 9d 31 be 31 a9 31 a9 31 8e 31 88 31 ac 31 ed 2b af 31 97 31 72 31 7e 31 91 31 94 31 85 31 7b 31 78 31 75 31 7e 31 8b 7e 1b 80 e4 7e a7 7f 00 00 b2 
ff 3c 31 72 31 60 31 66 31 69 31 78 31 9d 31 b5 31 af 31 ac 31 91 31 91 31 a6 31 f0 2b af 31 9d 31 6c 31 85 31 94 31 8e 31 91 31 7b 31 78 31 7b 31 75 31 8b 7e 1b 80 d9 7e a1 7f 00 00 45 
ff 3c 31 5a 31 60 31 63 31 60 31 7e 31 9a 31 b5 31 b5 31 a0 31 8e 31 8e 31 a0 31 de 2b b2 31 94 31 6c 31 88 31 81 31 97 31 8b 31 72 31 7e 31 6f 31 78 31 86 7e 15 80 e4 7e 96 7f 00 00 4e 
ff 3c 31 60 31 63 31 5a 31 60 31 7e 31 8e 31 bb 31 b5 31 a0 31 97 31 81 31 a3 31 e7 2b af 31 94 31 72 31 7b 31 8e 31 94 31 81 31 78 31 78 31 72 31 7b 31 8b 7e 1b 80 f5 7e 96 7f 00 00 8e 
ff 3c 31 66 31 5d 31 54 31 66 31 72 31 8e 31 b8 31 9d 31 a0 31 94 31 81 31 a9 31 c3 2b a6 31 94 31 63 31 7b 31 8b 31 81 31 8b 31 72 31 6f 31 72 31 6c 31 86 7e 1b 80 ea 7e a1 7f 00 00 99 
ff 3c 31 69 31 51 31 57 31 63 31 6f 31 97 31 b5 31 a0 31 a3 31 88 31 88 31 a6 31 b3 2b b2 31 8e 31 63 31 81 31 7e 31 8e 31 88 31 6c 31 78 31 69 31 6f 31 8b 7e 15 80 df 7e ac 7f 00 00 e6 
ff 3c 31 66 31 54 31 5d 31 5d 31 6f 31 9a 31 af 31 af 31 a3 31 8b 31 88 31 97 31 cc 2b a9 31 91 31 6c 31 75 31 81 31 91 31 7b 31 72 31 75 31 6c 31 75 31 8b 7e 1b 80 df 7e a1 7f 00 00 6e 
ff 3c 31 54 31 5a 31 5a 31 5a 31 75 31 8e 31 ac 31 af 31 9a 31 8e 31 88 31 97 31 b9 2b a6 31 94 31 63 31 7b 31 85 31 81 31 8b 31 6c 31 6c 31 6f 31 69 31 8b 7e 1b 80 e4 7e 96 7f 00 00 ed 
ff 3c 31 5a 31 5d 31 51 31 60 31 78 31 8e 31 bb 31 ac 31 9a 31 91 31 7e 31 a3 31 b3 2b b2 31 91 31 66 31 81 31 78 31 91 31 85 31 6c 31 78 31 69 31 6f 31 8b 7e 15 80 ef 7e 9c 7f 00 00 0d 
ff 3c 31 75 31 5d 31 57 31 69 31 6f 31 94 31 bb 31 a3 31 a6 31 94 31 85 31 a6 31 d5 2b af 31 91 31 6c 31 78 31 85 31 94 31 7e 31 75 31 75 31 6c 31 78 31 8b 7e 1b 80 ea 7e a7 7f 00 00 55 
ff 3c 31 6f 31 57 31 60 31 69 31 72 31 9a 31 b2 31 a9 31 a6 31 8b 31 8e 31 a6 31 d2 2b a9 31 97 31 66 31 7e 31 8e 31 88 31 8e 31 72 31 72 31 75 31 6f 31 86 7e 1b 80 df 7e b2 7f 00 00 b9 
ff 3c 31 5d 31 57 31 5d 31 5d 31 78 31 9a 31 af 31 b2 31 a0 31 8b 31 8b 31 97 31 bf 2b b2 31 91 31 69 31 85 31 78 31 94 31 88 31 6c 31 7b 31 6f 31 72 31 8b 7e 15 80 df 7e a7 7f 00 00 d2 
ff 3c 31 60 31 63 31 5d 31 60 31 7b 31 8e 31 b5 31 b8 31 a0 31 97 31 88 31 9d 31 d8 2b af 31 91 31 6f 31 7b 31 85 31 97 31 7e 31 78 31 7b 31 6c 31 78 31 8b 7e 1b 80 f5 7e 96 7f 00 00 76 
ff 3c 31 60 31 5d 31 54 31 69 31 78 31 91 31 be 31 a3 31 a0 31 97 31 81 31 a9 31 c6 2b a9 31 97 31 66 31 7e 31 8e 31 85 31 8b 31 72 31 72 31 72 31 6c 31 8b 7e 1b 80 ef 7e ac 7f 00 00 ae 
ff 3c 31 69 31 51 31 51 31 5d 31 6c 31 91 31 b8 31 9d 31 a0 31 88 31 7b 31 a3 31 a1 2b af 31 8e 31 60 31 7e 31 78 31 8b 31 88 31 66 31 75 31 69 31 6c 31 8b 7e 1b 80 e4 7e b2 7f 00 00 c1 
ff 3c 31 5d 31 47 31 4e 31 51 31 63 31 8b 31 a3 31 a0 31 9a 31 7e 31 7e 31 97 31 85 2b a3 31 85 31 60 31 6c 31 75 31 88 31 72 31 66 31 66 31 5d 31 69 31 91 7e 20 80 df 7e ac 7f 00 00 dd 
ff 3c 31 54 31 54 31 5a 31 5a 31 75 31 94 31 af 31 ac 31 97 31 88 31 88 31 97 31 b3 2b a6 31 94 31 66 31 78 31 8b 31 81 31 88 31 6f 31 6c 31 6f 31 6c 31 8b 7e 1b 80 e4 7e ac 7f 00 00 cf 
ff 3c 31 5d 31 60 31 57 31 5d 31 7b 31 91 31 b8 31 b8 31 a0 31 94 31 81 31 a3 31 b9 2b b2 31 94 31 66 31 85 31 7b 31 91 31 8e 31 6f 31 7b 31 6f 31 72 31 8b 7e 1b 80 ea 7e a7 7f 00 00 ef 
ff 3c 31 6f 31 60 31 57 31 69 31 72 31 8e 31 bb 31 a3 31 a3 31 94 31 85 31 ac 31 cc 2b af 31 8e 31 6f 31 7b 31 78 31 94 31 7e 31 72 31 78 31 6c 31 78 31 91 7e 1b 80 ef 7e ac 7f 00 00 9f 
ff 3c 31 6f 31 57 31 5d 31 69 31 72 31 9d 31 b8 31 a6 31 a6 31 8b 31 8b 31 a9 31 cc 2b a9 31 97 31 69 31 7b 31 8b 31 85 31 8b 31 72 31 75 31 75 31 6f 31 8b 7e 1b 80 e4 7e c2 7f 00 00 d4 
ff 3c 31 69 31 57 31 60 31 5d 31 75 31 9d 31 af 31 b5 31 a6 31 8b 31 8b 31 97 31 b9 2b af 31 94 31 66 31 85 31 78 31 8e 31 8b 31 6f 31 7b 31 6c 31 6f 31 8b 7e 20 80 df 7e b2 7f 00 00 e5 
ff 3c 31 5d 31 63 31 60 31 60 31 7e 31 91 31 b2 31 b8 31 9d 31 94 31 8b 31 9d 31 d2 2b af 31 91 31 6f 31 7e 31 7e 31 97 31 7e 31 75 31 7b 31 6c 31 7b 31 91 7e 1b 80 ef 7e a1 7f 00 00 9b 
ff 3c 31 60 31 5d 31 57 31 63 31 7b 31 91 31 be 31 ac 31 9d 31 97 31 81 31 a6 31 c6 2b a9 31 94 31 6c 31 78 31 88 31 85 31 88 31 72 31 72 31 75 31 72 31 91 7e 1b 80 f5 7e b2 7f 00 00 94 
ff 3c 31 72 31 60 31 5a 31 66 31 6f 31 97 31 bb 31 a6 31 a6 31 91 31 81 31 ac 31 bc 2b af 31 94 31 66 31 85 31 7b 31 91 31 8b 31 6f 31 7b 31 6f 31 6f 31 8b 7e 1b 80 e4 7e bd 7f 00 00 e1 
ff 3c 31 66 31 4e 31 54 31 60 31 6c 31 91 31 a9 31 a3 31 a0 31 85 31 88 31 a3 31 9e 2b ac 31 88 31 66 31 78 31 75 31 91 31 75 31 6c 31 72 31 63 31 72 31 91 7e 20 80 e4 7e b7 7f 00 00 d5 
ff 3c 31 41 31 38 31 3e 31 41 31 5d 31 81 31 9d 31 97 31 8b 31 72 31 72 31 7b 31 45 2b 91 31 7b 31 4e 31 60 31 72 31 6f 31 6c 31 5a 31 4e 31 5a 31 57 31 8b 7e 1b 80 e4 7e b7 7f 00 00 e2 
ff 3c 31 af 30 b5 30 a9 30 b5 30 e0 30 fe 30 35 31 2c 31 11 31 07 31 f8 30 0a 31 d4 28 23 31 04 31 c1 30 e9 30 e9 30 04 31 f2 30 cd 30 c1 30 d4 30 c7 30 91 7e 1b 80 ef 7e ac 7f 00 00 1d 
ff 3c 31 1f 30 26 30 0a 30 2c 30 59 30 87 30 ca 30 a6 30 9a 30 8d 30 78 30 96 30 be 26 ac 30 84 30 41 30 69 30 60 30 9a 30 66 30 4d 30 29 30 41 30 47 30 96 7e 20 80 f5 7e b7 7f 00 00 04 
ff 3c 31 9f 2f 93 2f 81 2f a8 2f d3 2f 1c 30 63 30 35 30 32 30 13 30 0a 30 1f 30 1c 25 35 30 19 30 b5 2f ec 2f ec 2f 1f 30 f2 2f d3 2f 87 2f ca 2f b5 2f 8b 7e 20 80 ef 7e c8 7f 00 00 bf 
ff 3c 31 04 2f 07 2f f4 2e 16 2f 56 2f ab 2f ec 2f ca 2f be 2f 99 2f 96 2f 9f 2f 92 23 c7 2f 9c 2f 2b 2f 75 2f 5c 2f a8 2f 78 2f 44 2f f4 2e 44 2f 2b 2f 91 7e 1b 80 d9 7e c2 7f 00 00 bf 
ff 3c 31 8a 2e 9f 2e 80 2e a2 2e f7 2e 4a 2f 99 2f 75 2f 59 2f 3e 2f 3b 2f 3b 2f a7 22 68 2f 3b 2f ca 2e 0d 2f f4 2e 59 2f 04 2f e2 2e 80 2e d6 2e ca 2e 91 7e 20 80 ea 7e a7 7f 00 00 e7 
ff 3c 31 53 2e 6b 2e 43 2e 74 2e c4 2e 13 2f 71 2f 44 2f 28 2f 13 2f 04 2f 0d 2f 6a 22 34 2f 0d 2f 93 2e dc 2e d0 2e 1f 2f dc 2e b4 2e 3d 2e a8 2e 90 2e 8b 7e 20 80 ef 7e ac 7f 00 00 77 
ff 3c 31 5f 2e 6e 2e 49 2e 7a 2e c7 2e 1c 2f 78 2f 3e 2f 31 2f 16 2f 04 2f 1c 2f c5 22 3b 2f 16 2f 96 2e eb 2e cd 2e 1f 2f e8 2e b4 2e 46 2e ae 2e 96 2e 91 7e 1b 80 ea 7e bd 7f 00 00 e6 
ff 3c 31 13 2f 13 2f fa 2e 22 2f 59 2f a5 2f ef 2f c7 2f bb 2f 99 2f 93 2f a8 2f e8 24 c7 2f 9c 2f 38 2f 75 2f 5f 2f b2 2f 71 2f 4d 2f 01 2f 44 2f 3b 2f 91 7e 1b 80 ea 7e bd 7f 00 00 61 
ff 3c 31 84 2f 84 2f 78 2f 90 2f c7 2f 07 30 44 30 26 30 16 30 fe 2f f8 2f 01 30 56 26 1f 30 01 30 a8 2f d6 2f dc 2f 07 30 df 2f bb 2f 7e 2f b2 2f a8 2f 96 7e 20 80 e4 7e b7 7f 00 00 a8 
ff 3c 31 ab 2f bb 2f ab 2f be 2f f8 2f 2f 30 6c 30 53 30 3e 30 29 30 1c 30 2c 30 e2 26 4a 30 2f 30 d3 2f 0d 30 01 30 2f 30 0d 30 e5 2f b5 2f e2 2f d3 2f 96 7e 1b 80 e4 7e b2 7f 00 00 ee 
ff 3c 31 e9 2f f2 2f d9 2f f5 2f 26 30 4d 30 96 30 75 30 66 30 53 30 41 30 60 30 84 27 78 30 50 30 07 30 38 30 29 30 60 30 32 30 16 30 ef 2f 0d 30 10 30 91 7e 20 80 f5 7e ac 7f 00 00 b5 
ff 3c 31 29 30 1f 30 10 30 2f 30 4d 30 81 30 be 30 96 30 93 30 7b 30 72 30 8d 30 2f 28 9a 30 81 30 3b 30 5c 30 66 30 81 30 66 30 4a 30 22 30 44 30 3e 30 91 7e 20 80 ef 7e bd 7f 00 00 33 
ff 3c 31 93 30 84 30 87 30 90 30 af 30 e0 30 0a 31 f2 30 ef 30 d0 30 ca 30 e6 30 72 29 f5 30 dd 30 96 30 c1 30 c1 30 d7 30 c7 30 a6 30 9a 30 a6 30 a0 30 91 7e 20 80 df 7e c2 7f 00 00 04 
ff 3c 31 47 30 4a 30 44 30 4d 30 78 30 a9 30 d7 30 c7 30 b5 30 a0 30 9d 30 a9 30 9a 28 c4 30 a0 30 63 30 8a 30 84 30 ac 30 8a 30 72 30 59 30 66 30 6f 30 91 7e 20 80 e4 7e ac 7f 00 00 60 
ff 3c 31 3e 30 4a 30 3e 30 4d 30 78 30 9d 30 da 30 c7 30 af 30 a3 30 96 30 a9 30 9a 28 be 30 a3 30 60 30 84 30 8a 30 a3 30 87 30 72 30 50 30 6c 30 69 30 91 7e 20 80 f5 7e ac 7f 00 00 24 
ff 3c 31 4d 30 4d 30 3b 30 53 30 78 30 a0 30 e0 30 be 30 b5 30 a6 30 90 30 b5 30 91 28 c1 30 a9 30 5c 30 8a 30 8a 30 a3 30 90 30 6c 30 53 30 6f 30 63 30 91 7e 20 80 f5 7e b2 7f 00 00 61 
ff 3c 31 60 30 50 30 4a 30 60 30 7b 30 af 30 e3 30 c4 30 c1 30 a6 30 a0 30 be 30 b8 28 d0 30 a9 30 6f 30 93 30 8d 30 b5 30 90 30 78 30 63 30 72 30 75 30 96 7e 20 80 ea 7e bd 7f 00 00 12 
ff 3c 31 5c 30 53 30 50 30 60 30 84 30 b5 30 e3 30 d0 30 c4 30 a9 30 a9 30 b8 30 ce 28 ca 30 af 30 75 30 90 30 9d 30 b5 30 96 30 7e 30 60 30 7b 30 75 30 91 7e 20 80 e4 7e b7 7f 00 00 a9 
ff 3c 31 56 30 5c 30 53 30 60 30 87 30 b2 30 e6 30 d4 30 c1 30 af 30 a6 30 b5 30 c8 28 d0 30 b5 30 6f 30 9a 30 9a 30 af 30 a0 30 7e 30 69 30 7e 30 75 30 96 7e 20 80 ef 7e ac 7f 00 00 8d 
ff 3c 31 78 30 7e 30 6f 30 81 30 a6 30 c7 30 01 31 e9 30 da 30 cd 30 be 30 d7 30 32 29 ec 30 ca 30 90 30 b2 30 b2 30 d4 30 b5 30 9a 30 8a 30 93 30 9a 30 96 7e 20 80 f5 7e ac 7f 00 00 e6 
ff 3c 31 84 30 7e 30 72 30 87 30 a6 30 cd 30 07 31 e6 30 e3 30 cd 30 be 30 e3 30 45 29 e9 30 cd 30 93 30 b2 30 be 30 d0 30 b5 30 a0 30 87 30 9a 30 9d 30 96 7e 20 80 f5 7e b2 7f 00 00 56 
ff 3c 31 f8 2f ec 2f df 2f fb 2f 1f 30 5c 30 96 30 78 30 72 30 53 30 4d 30 69 30 6c 27 75 30 5c 30 07 30 3b 30 38 30 5c 30 41 30 1c 30 ef 2f 19 30 0a 30 91 7e 20 80 ea 7e b7 7f 00 00 32 
ff 3c 31 b5 2f b8 2f ab 2f c1 2f f5 2f 32 30 69 30 50 30 41 30 26 30 26 30 2f 30 d3 26 53 30 29 30 d6 2f 0d 30 fb 2f 38 30 0a 30 e5 2f bb 2f df 2f df 2f 9c 7e 20 80 ea 7e ac 7f 00 00 13 
ff 3c 31 fe 2f 0a 30 f8 2f 0d 30 3e 30 69 30 a6 30 90 30 7b 30 69 30 5c 30 6f 30 e3 27 87 30 6c 30 26 30 47 30 4d 30 6f 30 4d 30 35 30 07 30 2c 30 26 30 96 7e 26 80 f5 7e a1 7f 00 00 7e 
ff 3c 31 2f 30 32 30 1f 30 38 30 60 30 87 30 c7 30 a9 30 9d 30 8d 30 7e 30 9d 30 5a 28 ac 30 8d 30 44 30 72 30 72 30 8a 30 78 30 53 30 38 30 56 30 47 30 96 7e 20 80 fa 7e a7 7f 00 00 f6 
ff 3c 31 32 30 2c 30 22 30 3b 30 59 30 8d 30 c7 30 a3 30 a0 30 87 30 7e 30 a0 30 5d 28 af 30 87 30 47 30 72 30 69 30 93 30 72 30 53 30 3b 30 4d 30 50 30 96 7e 20 80 ef 7e b2 7f 00 00 f2 
ff 3c 31 4a 30 41 30 3b 30 4d 30 6f 30 a3 30 d4 30 bb 30 b2 30 96 30 93 30 a9 30 ac 28 bb 30 9d 30 60 30 7e 30 87 30 a3 30 84 30 6c 30 4d 30 66 30 66 30 91 7e 26 80 ea 7e ac 7f 00 00 ce 
ff 3c 31 53 30 56 30 50 30 5c 30 81 30 af 30 e0 30 cd 30 be 30 a9 30 a6 30 b5 30 dd 28 ca 30 b2 30 6c 30 93 30 96 30 ac 30 9d 30 7b 30 63 30 7b 30 6f 30 96 7e 20 80 ef 7e a7 7f 00 00 eb 
ff 3c 31 84 30 8d 30 84 30 90 30 b5 30 d4 30 0a 31 fb 30 e6 30 da 30 ca 30 e6 30 8b 29 fb 30 da 30 a0 30 c4 30 c1 30 dd 30 c4 30 a6 30 a0 30 a3 30 a9 30 9c 7e 26 80 f5 7e a1 7f 00 00 83 
ff 3c 31 8e 32 76 32 7f 32 7c 32 6f 32 63 32 85 32 7c 32 79 32 73 32 57 32 8e 32 b8 2f 76 32 5a 32 5d 32 51 32 79 32 4b 32 5a 32 5a 32 8e 32 57 32 63 32 9c 7e 26 80 fa 7e a1 7f 00 00 c3 
ff 3c 31 5a 31 41 31 44 31 4e 31 57 31 78 31 9d 31 8b 31 8b 31 72 31 6c 31 94 31 43 2c 91 31 7e 31 4e 31 66 31 78 31 72 31 72 31 57 31 60 31 5a 31 5a 31 9c 7e 20 80 ef 7e b2 7f 00 00 ec 
ff 3c 31 b2 30 a9 30 a9 30 b2 30 d0 30 fe 30 26 31 17 31 0d 31 f2 30 f5 30 01 31 c2 29 1d 31 f8 30 be 30 e3 30 e0 30 fe 30 e6 30 c7 30 c1 30 c4 30 ca 30 9c 7e 20 80 ea 7e a7 7f 00 00 85 
ff 3c 31 3e 30 44 30 3b 30 47 30 75 30 a0 30 d7 30 c4 30 b2 30 9d 30 9a 30 a3 30 47 28 bb 30 9d 30 60 30 7e 30 87 30 a6 30 84 30 6f 30 4d 30 63 30 69 30 96 7e 26 80 ef 7e 9c 7f 00 00 0d 
ff 3c 31 da 30 dd 30 d4 30 e0 30 fb 30 17 31 47 31 38 31 29 31 1d 31 0d 31 2c 31 67 2a 35 31 20 31 e6 30 04 31 0d 31 1a 31 11 31 f2 30 ec 30 f2 30 ec 30 9c 7e 20 80 fa 7e 9c 7f 00 00 10 
ff 3c 31 3c 33 1a 33 2d 33 24 33 0b 33 ff 32 0b 33 0b 33 0e 33 05 33 f9 32 27 33 49 34 08 33 f0 32 ff 32 f3 32 11 33 e3 32 fc 32 f6 32 4e 33 f9 32 0b 33 9c 7e 26 80 00 7f a1 7f 00 00 19 
ff 3c 31 3e 31 29 31 29 31 32 31 41 31 69 31 8b 31 7b 31 78 31 5d 31 5a 31 78 31 c6 2b 7e 31 60 31 3b 31 4b 31 5a 31 63 31 51 31 44 31 44 31 3b 31 4b 31 96 7e 2b 80 ea 7e a7 7f 00 00 7b 
ff 3c 31 1c 30 19 30 13 30 22 30 50 30 8a 30 b8 30 a6 30 9a 30 7e 30 7e 30 87 30 3e 27 9d 30 84 30 35 30 63 30 66 30 84 30 6c 30 4a 30 1c 30 47 30 3b 30 9c 7e 26 80 ea 7e 9c 7f 00 00 11 
ff 3c 31 16 30 22 30 13 30 26 30 56 30 81 30 be 30 a9 30 93 30 81 30 78 30 87 30 8d 27 a6 30 81 30 38 30 6c 30 5c 30 8a 30 69 30 47 30 29 30 44 30 41 30 9c 7e 26 80 f5 7e 96 7f 00 00 3a 
ff 3c 31 04 30 0d 30 f5 2f 10 30 3e 30 69 30 ac 30 8d 30 81 30 6f 30 5c 30 7b 30 6c 27 8a 30 6c 30 26 30 4a 30 4a 30 78 30 4d 30 35 30 0a 30 2c 30 2c 30 9c 7e 2b 80 fa 7e 96 7f 00 00 d4 
ff 3c 31 0a 30 01 30 f2 2f 0d 30 32 30 69 30 a6 30 81 30 7e 30 66 30 5c 30 78 30 6c 27 84 30 6c 30 16 30 47 30 47 30 69 30 50 30 2c 30 01 30 2c 30 19 30 96 7e 26 80 f5 7e a1 7f 00 00 19 
ff 3c 31 a9 30 9a 30 9a 30 a3 30 be 30 ef 30 17 31 04 31 fe 30 e3 30 e0 30 f5 30 9a 29 0a 31 e9 30 af 30 d4 30 cd 30 ef 30 d7 30 b8 30 b2 30 b5 30 b8 30 9c 7e 20 80 ea 7e a1 7f 00 00 ad 
ff 3c 31 f3 32 dd 32 f6 32 dd 32 d4 32 cb 32 d1 32 e0 32 d7 32 cb 32 c8 32 dd 32 dd 31 d1 32 bc 32 c8 32 b6 32 dd 32 a9 32 bf 32 bf 32 08 33 bf 32 d4 32 a2 7e 2b 80 f5 7e 96 7f 00 00 e1 
ff 3c 31 fc 32 f0 32 fc 32 ed 32 e7 32 d4 32 e0 32 ed 32 e0 32 e0 32 d1 32 f0 32 e0 32 da 32 cb 32 ce 32 c2 32 f0 32 b0 32 d7 32 cb 32 11 33 d1 32 d7 32 a7 7e 20 80 00 7f 90 7f 00 00 51 
ff 3c 31 ed 32 d1 32 dd 32 da 32 cb 32 c2 32 d7 32 d1 32 d4 32 ce 32 bc 32 ea 32 fc 33 ce 32 b3 32 b6 32 b3 32 cb 32 a9 32 bf 32 b0 32 fc 32 b6 32 c2 32 9c 7e 26 80 06 7f 96 7f 00 00 c1 
ff 3c 31 fc 32 d4 32 e7 32 e0 32 ce 32 d1 32 da 32 d7 32 e0 32 ce 32 c5 32 f0 32 95 35 d4 32 b6 32 c2 32 b6 32 d7 32 b0 32 bc 32 bf 32 ff 32 bc 32 ce 32 9c 7e 2b 80 fa 7e a7 7f 00 00 53 
ff 3c 31 0e 33 ea 32 05 33 f0 32 e7 32 ea 32 ea 32 f6 32 f3 32 e0 32 e3 32 f9 32 31 38 e3 32 d4 32 d4 32 cb 32 f6 32 b9 32 dd 32 d4 32 11 33 da 32 e0 32 96 7e 26 80 ef 7e 9c 7f 00 00 47 
ff 3c 31 7c 32 73 32 82 32 73 32 7c 32 7c 32 8b 32 97 32 88 32 82 32 79 32 8e 32 21 35 88 32 69 32 5a 32 66 32 73 32 60 32 6c 32 57 32 91 32 5d 32 66 32 9c 7e 20 80 fa 7e 90 7f 00 00 42 
ff 3c 31 f8 31 ef 31 e9 31 ef 31 ff 31 08 32 48 32 42 32 32 32 26 32 fc 31 3f 32 81 31 29 32 08 32 f8 31 fc 31 11 32 08 32 ff 31 ff 31 11 32 f2 31 05 32 a2 7e 2b 80 06 7f 90 7f 00 00 8c 
ff 3c 31 bb 31 a6 31 a3 31 af 31 b2 31 cb 31 f2 31 da 31 e0 31 ce 31 c2 31 ec 31 e5 2e e6 31 d7 31 af 31 bb 31 da 31 c2 31 cb 31 b8 31 c5 31 bb 31 bb 31 96 7e 26 80 f5 7e 9c 7f 00 00 1a 
ff 3c 31 88 31 6f 31 75 31 7e 31 88 31 a9 31 c5 31 b8 31 b8 31 9d 31 a0 31 be 31 37 2d c8 31 a9 31 7e 31 9a 31 9d 31 a3 31 a0 31 85 31 97 31 88 31 8b 31 a2 7e 26 80 ef 7e a1 7f 00 00 92 
ff 3c 31 60 31 4e 31 57 31 54 31 69 31 91 31 a6 31 a9 31 9d 31 81 31 85 31 94 31 3d 2c a9 31 88 31 66 31 75 31 75 31 91 31 75 31 6c 31 72 31 63 31 72 31 a2 7e 2b 80 ef 7e 96 7f 00 00 59 
ff 3c 31 4e 31 54 31 51 31 51 31 6c 31 81 31 a3 31 a9 31 91 31 88 31 7e 31 94 31 12 2c 9a 31 88 31 5d 31 6c 31 7b 31 7e 31 7b 31 66 31 63 31 66 31 66 31 a2 7e 2b 80 f5 7e 90 7f 00 00 47 
ff 3c 31 4b 31 4e 31 44 31 54 31 6c 31 7e 31 ac 31 9d 31 8e 31 85 31 72 31 97 31 ea 2b 9d 31 85 31 54 31 72 31 6c 31 7b 31 7b 31 5a 31 69 31 60 31 60 31 9c 7e 26 80 00 7f 96 7f 00 00 96 
ff 3c 31 63 31 4b 31 44 31 54 31 5d 31 85 31 a9 31 94 31 94 31 7e 31 72 31 9a 31 f0 2b 9d 31 7e 31 60 31 69 31 6c 31 85 31 6c 31 63 31 66 31 57 31 66 31 a2 7e 2b 80 f5 7e a7 7f 00 00 47 
ff 3c 31 41 31 2c 31 35 31 3b 31 4b 31 72 31 8b 31 85 31 81 31 66 31 69 31 81 31 73 2b 85 31 72 31 41 31 54 31 69 31 63 31 63 31 4b 31 47 31 4e 31 47 31 a2 7e 2b 80 ea 7e a7 7f 00 00 8a 
ff 3c 31 29 31 29 31 2f 31 2f 31 4e 31 6f 31 8b 31 8b 31 75 31 63 31 63 31 72 31 4f 2b 88 31 6f 31 38 31 5d 31 5a 31 66 31 63 31 41 31 4b 31 44 31 44 31 9c 7e 26 80 f5 7e 9c 7f 00 00 85 
ff 3c 31 38 31 38 31 35 31 38 31 54 31 69 31 97 31 91 31 7b 31 75 31 60 31 7e 31 7f 2b 91 31 6c 31 47 31 5a 31 5d 31 75 31 5a 31 51 31 51 31 47 31 54 31 a2 7e 31 80 fa 7e 96 7f 00 00 cf 
ff 3c 31 44 31 3e 31 35 31 47 31 57 31 6f 31 9d 31 8b 31 85 31 75 31 66 31 8e 31 9b 2b 8b 31 75 31 4b 31 5a 31 6c 31 6c 31 66 31 54 31 4e 31 51 31 51 31 9c 7e 31 80 fa 7e a1 7f 00 00 28 
ff 3c 31 4b 31 32 31 32 31 41 31 4b 31 75 31 9a 31 85 31 81 31 69 31 63 31 88 31 79 2b 8e 31 72 31 3e 31 60 31 60 31 6c 31 69 31 4b 31 54 31 4e 31 4b 31 9c 7e 2b 80 f5 7e ac 7f 00 00 8a 
ff 3c 31 41 31 2c 31 32 31 32 31 47 31 72 31 88 31 85 31 7e 31 63 31 66 31 75 31 64 2b 8b 31 66 31 41 31 54 31 54 31 6f 31 57 31 47 31 4e 31 41 31 4e 31 a2 7e 2b 80 ea 7e a7 7f 00 00 81 
ff 3c 31 b8 30 bb 30 b8 30 be 30 e9 30 0a 31 32 31 2f 31 17 31 0a 31 04 31 11 31 45 29 23 31 0a 31 d0 30 e9 30 fb 30 07 31 f2 30 e0 30 c4 30 dd 30 d7 30 9c 7e 31 80 f5 7e 96 7f 00 00 a3 
ff 3c 31 10 30 19 30 01 30 1c 30 50 30 78 30 c1 30 a3 30 8d 30 81 30 6f 30 87 30 90 26 9d 30 7e 30 29 30 63 30 59 30 81 30 69 30 3e 30 19 30 41 30 32 30 a7 7e 26 80 06 7f 96 7f 00 00 92 
ff 3c 31 9f 2f 99 2f 7e 2f a5 2f d3 2f 16 30 60 30 32 30 2c 30 16 30 07 30 22 30 25 25 3e 30 10 30 bb 2f ef 2f dc 2f 29 30 e9 2f c7 2f 93 2f c1 2f be 2f a2 7e 31 80 fa 7e a1 7f 00 00 0d 
ff 3c 31 04 2f fe 2e eb 2e 13 2f 4d 2f 9c 2f e9 2f c1 2f b5 2f 90 2f 90 2f 9f 2f 9b 23 b8 2f 96 2f 2b 2f 62 2f 5f 2f a2 2f 68 2f 47 2f eb 2e 3e 2f 2b 2f 9c 7e 31 80 ef 7e a7 7f 00 00 1b 
ff 3c 31 87 2e 93 2e 77 2e 9c 2e eb 2e 41 2f 8a 2f 65 2f 53 2f 31 2f 31 2f 2b 2f 95 22 5c 2f 34 2f b7 2e 07 2f ee 2e 41 2f 07 2f d3 2e 71 2e d3 2e b7 2e a2 7e 2b 80 ef 7e 9c 7f 00 00 e5 
ff 3c 31 1f 2e 3a 2e 19 2e 40 2e 99 2e f1 2e 4a 2f 1f 2f 01 2f e5 2e df 2e e2 2e fc 21 13 2f e2 2e 65 2e b4 2e 96 2e fe 2e ae 2e 83 2e 16 2e 74 2e 68 2e a2 7e 31 80 fa 7e 9c 7f 00 00 03 
ff 3c 31 2e 2f 3b 2f 19 2f 41 2f 78 2f b5 2f 01 30 dc 2f c7 2f b2 2f 9c 2f b2 2f 49 25 d3 2f b2 2f 4a 2f 81 2f 78 2f b5 2f 81 2f 5f 2f 13 2f 56 2f 4a 2f 9c 7e 31 80 00 7f 9c 7f 00 00 2e 
ff 3c 31 14 32 e9 31 f2 31 f5 31 e9 31 fc 31 26 32 1a 32 1d 32 08 32 ec 31 23 32 31 2e 1a 32 02 32 ec 31 f5 31 0e 32 ec 31 02 32 f2 31 1a 32 f2 31 f2 31 a2 7e 2b 80 00 7f ac 7f 00 00 fb 
ff 3c 31 5a 32 39 32 4e 32 45 32 3f 32 51 32 5d 32 5a 32 5a 32 42 32 29 32 5d 32 b5 2f 54 32 2f 32 2c 32 2c 32 3f 32 32 32 32 32 29 32 5d 32 23 32 36 32 a7 7e 31 80 f5 7e ac 7f 00 00 dd 
ff 3c 31 26 32 ff 31 26 32 1a 32 11 32 26 32 48 32 4e 32 3f 32 2c 32 11 32 3f 32 a5 2f 32 32 1d 32 0b 32 0b 32 32 32 11 32 1a 32 14 32 32 32 0e 32 14 32 9c 7e 31 80 00 7f 9c 7f 00 00 ba 
ff 3c 31 20 32 05 32 1d 32 0b 32 14 32 14 32 4b 32 4b 32 39 32 32 32 08 32 42 32 c7 2f 36 32 1a 32 ff 31 11 32 26 32 0e 32 20 32 08 32 32 32 0b 32 0b 32 a7 7e 2b 80 0b 7f 9c 7f 00 00 b3 
ff 3c 31 26 32 ff 31 02 32 0e 32 05 32 0e 32 48 32 3c 32 3c 32 2f 32 05 32 4b 32 04 30 36 32 14 32 05 32 0b 32 1a 32 14 32 11 32 08 32 2c 32 02 32 14 32 ad 7e 31 80 0b 7f a7 7f 00 00 30 
ff 3c 31 5d 31 44 31 4b 31 54 31 60 31 85 31 a6 31 94 31 94 31 78 31 75 31 9a 31 49 2c 97 31 81 31 5a 31 66 31 7e 31 7e 31 72 31 63 31 63 31 60 31 66 31 a7 7e 36 80 fa 7e ac 7f 00 00 ed 
ff 3c 31 96 30 8a 30 87 30 93 30 b5 30 e9 30 11 31 01 31 f8 30 da 30 dd 30 e9 30 9d 28 01 31 e6 30 9d 30 ca 30 ca 30 e0 30 d0 30 af 30 9a 30 af 30 a6 30 a7 7e 2b 80 f5 7e a7 7f 00 00 8c 
ff 3c 31 a2 2f b2 2f a2 2f b5 2f f2 2f 2c 30 69 30 53 30 3b 30 29 30 22 30 29 30 5c 25 53 30 26 30 d0 2f 07 30 f5 2f 38 30 04 30 df 2f b2 2f d9 2f d9 2f a7 7e 31 80 fa 7e 9c 7f 00 00 a8 
ff 3c 31 19 2f 2b 2f 0a 2f 31 2f 75 2f b2 2f 04 30 df 2f ca 2f b8 2f a5 2f bb 2f 0c 24 d6 2f b2 2f 4d 2f 84 2f 7b 2f be 2f 84 2f 65 2f 10 2f 59 2f 50 2f a7 7e 31 80 06 7f 9c 7f 00 00 0e 
ff 3c 31 e2 2f df 2f ca 2f ec 2f 13 30 4a 30 8d 30 63 30 60 30 47 30 3b 30 59 30 e2 26 69 30 4d 30 f5 2f 2c 30 26 30 4a 30 32 30 07 30 d9 2f 0a 30 f5 2f ad 7e 31 80 00 7f ac 7f 00 00 43 
ff 3c 31 3b 30 2f 30 29 30 3e 30 60 30 96 30 c7 30 ac 30 a6 30 87 30 87 30 a0 30 26 28 b2 30 8d 30 4d 30 75 30 6c 30 9a 30 75 30 56 30 41 30 50 30 53 30 a7 7e 31 80 f5 7e ac 7f 00 00 0b 
ff 3c 31 29 32 02 32 20 32 17 32 0b 32 20 32 42 32 48 32 3c 32 26 32 0e 32 3c 32 e8 2e 2f 32 1a 32 0b 32 08 32 2f 32 0e 32 14 32 14 32 32 32 0b 32 14 32 a7 7e 36 80 00 7f a7 7f 00 00 1e 
ff 3c 31 08 32 ef 31 f2 31 ec 31 f8 31 ff 31 32 32 3c 32 29 32 20 32 fc 31 29 32 fa 2e 26 32 0b 32 ef 31 ff 31 14 32 fc 31 0b 32 f8 31 1a 32 f8 31 fc 31 a7 7e 2b 80 06 7f 9c 7f 00 00 17 
ff 3c 31 d1 31 c8 31 c8 31 ce 31 d4 31 dd 31 05 32 ff 31 ef 31 e6 31 d7 31 ff 31 87 2e 08 32 e6 31 d1 31 dd 31 e6 31 e6 31 e3 31 d1 31 f5 31 ce 31 e0 31 a7 7e 31 80 0b 7f a1 7f 00 00 91 
ff 3c 31 c2 31 a6 31 a9 31 b2 31 b2 31 ce 31 ec 31 da 31 dd 31 cb 31 c2 31 e9 31 19 2e e9 31 d1 31 b8 31 be 31 d7 31 ce 31 c5 31 bb 31 ce 31 b5 31 c5 31 a7 7e 36 80 00 7f ac 7f 00 00 27 
ff 3c 31 81 31 6c 31 75 31 78 31 81 31 a0 31 b8 31 b5 31 b2 31 97 31 9a 31 b2 31 03 2d bb 31 a6 31 78 31 91 31 a0 31 97 31 9d 31 85 31 91 31 88 31 81 31 ad 7e 36 80 f5 7e ac 7f 00 00 ad 
ff 3c 31 c4 30 c4 30 c4 30 c7 30 ef 30 14 31 3b 31 32 31 23 31 0d 31 0d 31 1a 31 bf 29 35 31 11 31 d7 30 fe 30 f2 30 17 31 fe 30 e3 30 dd 30 dd 30 e3 30 ad 7e 36 80 fa 7e a1 7f 00 00 4a 
ff 3c 31 be 2f cd 2f b5 2f d0 2f 07 30 38 30 81 30 66 30 50 30 41 30 32 30 44 30 ca 25 5c 30 3b 30 e9 2f 13 30 13 30 4a 30 16 30 fe 2f c4 2f f2 2f ef 2f ad 7e 3c 80 0b 7f 9c 7f 00 00 69 
ff 3c 31 81 2f 81 2f 65 2f 8d 2f be 2f fe 2f 4a 30 1c 30 13 30 fe 2f ec 2f 0a 30 34 25 1c 30 fe 2f 99 2f d3 2f cd 2f 01 30 dc 2f af 2f 6e 2f af 2f 99 2f ad 7e 36 80 06 7f a7 7f 00 00 4d 
ff 3c 31 2c 30 1f 30 16 30 2f 30 50 30 87 30 be 30 9d 30 9a 30 7e 30 7b 30 96 30 c4 27 a9 30 81 30 3e 30 6c 30 60 30 8d 30 6c 30 4a 30 2f 30 44 30 44 30 ad 7e 36 80 fa 7e b2 7f 00 00 9b 
ff 3c 31 5c 30 56 30 50 30 5c 30 84 30 b5 30 e3 30 cd 30 c7 30 ac 30 a9 30 b5 30 a0 28 cd 30 af 30 72 30 90 30 96 30 b5 30 96 30 81 30 63 30 78 30 78 30 a7 7e 3c 80 fa 7e ac 7f 00 00 3e 
ff 3c 31 c8 31 be 31 cb 31 c2 31 ce 31 d7 31 f2 31 f8 31 e3 31 da 31 d1 31 e9 31 ab 2d f8 31 e3 31 c5 31 d4 31 e9 31 d1 31 e0 31 cb 31 e9 31 d1 31 ce 31 ad 7e 36 80 00 7f a1 7f 00 00 fc 
ff 3c 31 e6 31 e0 31 e0 31 e3 31 ec 31 ef 31 1a 32 2c 32 11 32 05 32 e9 31 11 32 9c 2e 1d 32 f8 31 e3 31 f2 31 fc 31 f8 31 f8 31 e9 31 11 32 e6 31 f5 31 ad 7e 36 80 0b 7f a1 7f 00 00 7d 
ff 3c 31 20 32 f5 31 f8 31 ff 31 f5 31 08 32 45 32 2f 32 39 32 29 32 ff 31 42 32 47 2f 2c 32 0b 32 02 32 fc 31 1d 32 08 32 05 32 05 32 20 32 fc 31 0b 32 b2 7e 3c 80 11 7f b2 7f 00 00 74 
ff 3c 31 9d 31 7e 31 8b 31 91 31 97 31 b5 31 cb 31 c2 31 c5 31 a9 31 ac 31 cb 31 6e 2d cb 31 b8 31 8e 31 a3 31 b8 31 a6 31 b5 31 9a 31 a6 31 9d 31 97 31 ad 7e 36 80 fa 7e b7 7f 00 00 4c 
ff 3c 31 3e 31 38 31 3e 31 3b 31 57 31 78 31 94 31 94 31 85 31 6c 31 6c 31 7b 31 e1 2b 94 31 72 31 47 31 63 31 5d 31 75 31 66 31 4e 31 5d 31 4b 31 54 31 ad 7e 36 80 00 7f ac 7f 00 00 6d 
ff 3c 31 04 30 10 30 fe 2f 10 30 44 30 72 30 b5 30 9d 30 87 30 78 30 6c 30 7e 30 c4 26 96 30 75 30 2c 30 50 30 53 30 7e 30 53 30 3e 30 0d 30 32 30 35 30 b2 7e 3c 80 0b 7f a1 7f 00 00 c6 
ff 3c 31 df 2f e2 2f ca 2f ec 2f 1c 30 4d 30 93 30 72 30 63 30 50 30 3e 30 5c 30 71 26 6f 30 53 30 f8 2f 2c 30 2c 30 50 30 35 30 0d 30 dc 2f 0d 30 fb 2f b2 7e 36 80 11 7f ac 7f 00 00 ce 
ff 3c 31 be 30 af 30 a6 30 bb 30 d0 30 fb 30 2f 31 11 31 11 31 f5 30 ec 30 11 31 a6 29 1d 31 fb 30 c1 30 e6 30 e3 30 fe 30 e9 30 ca 30 c4 30 c7 30 ca 30 ad 7e 36 80 06 7f b7 7f 00 00 51 
ff 3c 31 b8 31 9d 31 a9 31 a6 31 ac 31 cb 31 dd 31 da 31 d7 31 be 31 be 31 d7 31 89 2d e3 31 c8 31 b2 31 b5 31 c8 31 c8 31 be 31 b5 31 cb 31 ac 31 be 31 b2 7e 3c 80 fa 7e b7 7f 00 00 10 
ff 3c 31 0b 32 e6 31 f5 31 e9 31 f5 31 05 32 2c 32 39 32 29 32 11 32 ff 31 26 32 fa 2e 1d 32 0b 32 ef 31 f8 31 17 32 f2 31 08 32 fc 31 11 32 f8 31 fc 31 ad 7e 3c 80 06 7f ac 7f 00 00 dd 
ff 3c 31 a0 31 a0 31 9d 31 9d 31 b2 31 b8 31 e6 31 e0 31 ce 31 c8 31 b5 31 d4 31 b1 2d e6 31 c8 31 a6 31 be 31 c2 31 c2 31 c2 31 a9 31 c8 31 ac 31 b2 31 ad 7e 36 80 11 7f a1 7f 00 00 95 
ff 3c 31 85 31 78 31 75 31 85 31 8b 31 a0 31 cb 31 b2 31 b2 31 a9 31 97 31 c5 31 0c 2d c2 31 a3 31 8b 31 91 31 9d 31 a9 31 94 31 8b 31 9a 31 81 31 97 31 b2 7e 41 80 0b 7f b2 7f 00 00 63 
ff 3c 31 5a 31 3e 31 41 31 4e 31 5a 31 81 31 a3 31 8e 31 8e 31 72 31 72 31 94 31 03 2c 91 31 7e 31 51 31 66 31 75 31 72 31 75 31 5d 31 5d 31 5d 31 5a 31 b2 7e 3c 80 00 7f bd 7f 00 00 f4 
ff 3c 31 51 31 3b 31 41 31 41 31 57 31 7e 31 94 31 94 11 8b 31 6f 31 72 31 7e 31 e1 2b 9a 31 78 31 4e 31 69 31 60 31 78 31 72 31 51 31 63 31 54 31 57 31 b2 7e 3c 80 00 7f b2 7f 00 00 01 
ff 3c 31 32 31 35 31 38 31 38 31 54 31 6c 31 8b 31 8e 31 78 31 6c 31 66 31 78 31 b3 2b 88 31 6c 31 4b 31 54 31 57 31 6f 31 5a 31 4e 31 4e 31 44 31 51 31 ad 7e 41 80 06 7f a7 7f 00 00 ab 
ff 3c 31 3b 31 3b 31 32 31 3e 31 57 31 6c 31 9d 31 91 31 7b 31 72 31 5d 31 85 31 b6 2b 85 31 75 31 44 31 57 31 66 31 63 31 66 31 4e 31 4e 31 51 31 4b 31 b2 7e 3c 80 11 7f ac 7f 00 00 1c 
ff 3c 31 51 31 3b 31 32 31 41 31 4b 31 72 31 9a 31 81 31 85 31 72 31 63 31 88 31 ad 2b 91 31 72 31 44 31 63 31 5a 31 72 31 69 31 4b 31 57 31 4e 31 4e 31 b2 7e 3c 80 0b 7f b7 7f 00 00 c8 
ff 3c 31 44 31 2c 31 35 31 3e 31 47 31 72 31 8b 31 81 31 7e 31 63 31 66 31 85 31 a1 2b 88 31 69 31 47 31 54 31 57 31 72 31 54 31 4b 31 4e 31 41 31 51 31 b2 7e 41 80 00 7f c2 7f 00 00 4d 
ff 3c 31 f8 30 ef 30 f5 30 f5 30 17 31 3e 31 5d 31 5d 31 47 31 32 31 32 31 3b 31 97 2a 51 31 3e 31 07 31 1d 31 32 31 32 31 29 31 14 31 04 31 14 31 0d 31 b2 7e 41 80 06 7f b7 7f 00 00 2a 
ff 3c 31 66 30 6f 30 60 30 6f 30 9d 30 be 30 fb 30 e9 30 d4 30 ca 30 bb 30 cd 30 44 28 e9 30 c4 30 81 30 af 30 a3 30 c7 30 af 30 8a 30 7b 30 8d 30 8a 30 b2 7e 3c 80 0b 7f ac 7f 00 00 e7 
ff 3c 31 16 30 19 30 01 30 22 30 4d 30 7b 30 be 30 9a 30 8d 30 7e 30 6c 30 8d 30 38 27 a0 30 78 30 35 30 5c 30 53 30 8a 30 56 30 41 30 1c 30 38 30 3e 30 b8 7e 41 80 11 7f b7 7f 00 00 ca 
ff 3c 31 6c 30 5c 30 50 30 69 30 84 30 b8 30 f2 30 d0 30 ca 30 af 30 a9 30 c7 30 6c 28 d0 30 b8 30 75 30 9a 30 a3 30 b2 30 a0 30 84 30 66 30 81 30 78 30 ad 7e 41 80 06 7f bd 7f 00 00 e1 
ff 3c 31 2c 31 1a 31 20 31 26 31 35 31 5d 31 78 31 72 31 6c 31 51 31 51 31 66 31 3c 2b 75 31 5a 31 29 31 47 31 4b 31 54 31 51 31 2f 31 3b 31 32 31 32 31 b2 7e 3c 80 fa 7e b7 7f 00 00 54 
ff 3c 31 54 31 4e 31 57 31 54 31 6c 31 88 31 a0 31 a3 31 91 31 81 31 7b 31 8e 31 24 2c a3 31 81 31 63 31 72 31 78 31 88 31 75 31 66 31 75 31 60 31 6f 31 b8 7e 41 80 06 7f b2 7f 00 00 36 
ff 3c 31 94 31 94 31 91 31 91 31 a6 31 ac 31 da 31 d4 31 c2 31 bb 31 a9 31 c8 31 31 2d d1 31 be 31 9a 31 a6 31 c2 31 af 31 b5 31 a6 31 af 31 a3 31 a3 31 b2 7e 41 80 11 7f ac 7f 00 00 0e 
ff 3c 31 78 31 69 31 60 31 6f 31 78 31 91 31 bb 31 a6 31 a6 31 97 31 85 31 b2 31 80 2c b2 31 9a 31 6c 31 8b 31 8e 31 8e 31 94 31 75 31 85 31 7b 31 78 31 b8 7e 3c 80 11 7f b7 7f 00 00 08 
ff 3c 31 4e 31 32 31 35 31 44 31 4e 31 78 31 97 31 7e 31 85 31 69 31 66 31 88 31 cc 2b 94 31 6f 31 4e 31 5d 31 5a 31 75 31 60 31 54 31 5d 31 47 31 57 31 b2 7e 47 80 06 7f c8 7f 00 00 70 
ff 3c 31 44 31 32 31 38 31 35 31 4e 31 75 31 8b 31 8e 31 81 31 66 31 66 31 72 31 b3 2b 85 31 72 31 47 31 54 31 66 31 63 31 63 31 4e 31 4b 31 4e 31 4e 31 b2 7e 47 80 00 7f bd 7f 00 00 23 
ff 3c 31 2c 31 32 31 2f 31 2f 31 4e 31 66 31 88 31 8b 31 72 31 69 31 60 31 72 31 85 2b 88 31 6c 31 38 31 5a 31 54 31 63 31 63 31 41 31 4b 31 44 31 41 31 b2 7e 3c 80 0b 7f b2 7f 00 00 ba 
ff 3c 31 35 31 35 31 29 31 38 31 51 31 69 31 94 31 8b 31 75 31 6c 31 5a 31 7e 31 95 2b 88 31 66 31 44 31 54 31 51 31 6c 31 54 31 4b 31 4e 31 41 31 4e 31 b2 7e 47 80 16 7f bd 7f 00 00 b4 
ff 3c 31 35 31 23 31 1a 31 2c 31 38 31 5d 31 8b 31 6f 31 72 31 5d 31 4e 31 75 31 5b 2b 78 31 60 31 32 31 41 31 57 31 5a 31 4e 31 3e 31 35 31 38 31 3b 31 b2 7e 47 80 11 7f c2 7f 00 00 01 
ff 3c 31 17 31 01 31 07 31 14 31 23 31 4e 31 6f 31 60 31 5d 31 41 31 41 31 60 31 db 2a 66 31 4b 31 11 31 35 31 35 31 44 31 3e 31 1d 31 20 31 20 31 1d 31 b2 7e 41 80 00 7f c8 7f 00 00 14 
ff 3c 31 20 31 14 31 1a 31 17 31 35 31 5d 31 78 31 75 31 66 31 4e 31 4e 31 5d 31 24 2b 78 31 54 31 2c 31 41 31 3e 31 5a 31 41 31 2f 31 35 31 29 31 38 31 b8 7e 41 80 06 7f c2 7f 00 00 f8 
ff 3c 31 26 31 2c 31 23 31 29 31 47 31 57 31 88 31 88 31 6c 31 66 31 57 31 6c 31 6a 2b 7b 31 63 31 38 31 44 31 5d 31 5a 31 51 31 44 31 3b 31 3e 31 41 31 b2 7e 47 80 11 7f b7 7f 00 00 c3 
ff 3c 31 35 31 32 31 26 31 3b 31 4e 31 66 31 94 31 7e 31 75 31 6c 31 5a 31 85 31 7c 2b 85 31 6c 31 38 31 5a 31 57 31 60 31 63 31 41 31 4b 31 47 31 41 31 b2 7e 41 80 16 7f c2 7f 00 00 7f 
ff 3c 31 47 31 2c 31 29 31 38 31 41 31 72 31 94 31 7b 31 7b 31 63 31 5a 31 7e 31 89 2b 88 31 63 31 44 31 54 31 4e 31 72 31 57 31 47 31 4e 31 3e 31 4e 31 b2 7e 47 80 0b 7f d3 7f 00 00 3e 
ff 3c 31 41 31 2c 31 35 31 38 31 47 31 72 31 88 31 88 31 7e 31 63 31 66 31 78 31 95 2b 81 31 6f 31 44 31 4e 31 63 31 66 31 5d 31 4e 31 47 31 4b 31 4b 31 b2 7e 47 80 00 7f ce 7f 00 00 a4 
ff 3c 31 23 31 23 31 26 31 29 31 44 31 63 31 85 31 81 31 6c 31 5d 31 5a 31 6c 31 58 2b 7e 31 63 31 2f 31 51 31 51 31 5a 31 5a 31 3b 31 41 31 3e 31 38 31 b2 7e 47 80 0b 7f c2 7f 00 00 e8 
ff 3c 31 11 31 14 31 07 31 14 31 32 31 47 31 7b 31 72 31 5a 31 51 31 3e 31 5d 31 fc 2a 6f 31 4b 31 23 31 3b 31 35 31 54 31 3b 31 26 31 2c 31 23 31 2f 31 b8 7e 47 80 11 7f c8 7f 00 00 50 
ff 3c 31 e6 30 da 30 cd 30 e3 30 f8 30 1a 31 51 31 32 31 32 31 20 31 11 31 35 31 1a 2a 3b 31 1d 31 ec 30 fe 30 14 31 1d 31 07 31 f8 30 e6 30 ef 30 f5 30 b8 7e 47 80 11 7f ce 7f 00 00 48 
ff 3c 31 ca 30 b5 30 b2 30 ca 30 dd 30 0d 31 38 31 1d 31 1d 31 fe 30 fe 30 20 31 a6 29 23 31 0d 31 c7 30 ef 30 f5 30 fe 30 fb 30 da 30 ca 30 dd 30 d0 30 b8 7e 41 80 06 7f d9 7f 00 00 4f 
ff 3c 31 c1 30 b5 30 b5 30 bb 30 dd 30 0a 31 2f 31 26 31 17 31 fb 30 fe 30 07 31 a0 29 26 31 fe 30 ca 30 ec 30 e6 30 0a 31 ef 30 d4 30 cd 30 cd 30 d4 30 b8 7e 47 80 00 7f d3 7f 00 00 2b 
ff 3c 31 32 31 38 31 38 31 38 31 54 31 69 31 8e 31 91 31 78 31 6f 31 63 31 78 31 98 2b 81 31 6f 31 47 31 51 31 63 31 69 31 5a 31 4e 31 4b 31 47 31 51 31 b8 7e 47 80 0b 7f c8 7f 00 00 d2 
ff 3c 31 3e 31 41 31 38 31 47 31 5a 31 72 31 9d 31 94 31 7e 31 75 31 63 31 8e 31 b0 2b 88 31 78 31 44 31 60 31 63 31 6c 31 6c 31 4e 31 57 31 54 31 4e 31 b2 7e 41 80 16 7f d3 7f 00 00 1c 
ff 3c 31 54 31 3e 31 3b 31 47 31 51 31 75 31 9d 31 8b 31 8b 31 72 31 66 31 8e 31 bf 2b 91 31 72 31 4e 31 63 31 5d 31 7b 31 66 31 51 31 5d 31 4e 31 5a 31 b8 7e 47 80 0b 7f de 7f 00 00 df 
ff 3c 31 35 31 23 31 29 31 32 31 3e 31 66 31 85 31 78 31 75 31 5a 31 5d 31 78 31 70 2b 7b 31 63 31 38 31 44 31 5d 31 60 31 4e 31 41 31 3e 31 3b 31 41 31 b2 7e 47 80 00 7f de 7f 00 00 02 
ff 3c 31 c7 30 c4 30 c4 30 ca 30 ef 30 1a 31 3b 31 32 31 23 31 0a 31 0a 31 17 31 da 29 2f 31 17 31 d4 30 fb 30 01 31 0d 31 04 31 e6 30 d7 30 e9 30 dd 30 b8 7e 41 80 06 7f d9 7f 00 00 c9 
ff 3c 31 69 30 72 30 66 30 72 30 a0 30 be 30 fe 30 ef 30 d7 30 c7 30 bb 30 d0 30 8b 28 ec 30 c4 30 87 30 ac 30 a3 30 d0 30 ac 30 8d 30 81 30 8a 30 90 30 b8 7e 47 80 11 7f ce 7f 00 00 f1 
ff 3c 31 b8 30 b5 30 a3 30 bb 30 da 30 f8 30 32 31 11 31 0d 31 01 31 ec 30 14 31 9d 29 1a 31 fb 30 c7 30 dd 30 ec 30 fe 30 e3 30 d4 30 bb 30 ca 30 d0 30 b2 7e 47 80 16 7f d9 7f 00 00 d2 
ff 3c 31 63 31 4b 31 4b 31 57 31 60 31 85 31 a9 31 91 31 94 31 78 31 72 31 9a 31 f3 2b 9a 31 88 31 54 31 72 31 7e 31 75 31 7e 31 60 31 69 31 66 31 60 31 b8 7e 41 80 0b 7f e9 7f 00 00 a2 
ff 3c 31 60 31 4e 31 57 31 54 31 66 31 88 31 a3 31 a0 31 97 31 7e 31 7e 31 94 31 0c 2c a6 31 81 31 5d 31 75 31 75 31 88 31 78 31 63 31 75 31 60 31 69 31 b8 7e 47 80 00 7f de 7f 00 00 95 
ff 3c 31 4b 31 4b 31 51 31 51 31 69 31 81 31 a3 31 a0 31 8e 31 7e 31 7b 31 8e 31 12 2c 9d 31 81 31 60 31 69 31 85 31 85 31 72 31 66 31 69 31 60 31 69 31 b8 7e 4c 80 0b 7f d9 7f 00 00 55 
ff 3c 31 72 31 6f 31 69 31 72 31 88 31 97 31 c2 31 bb 31 a6 31 a0 31 8b 31 af 31 92 2c b5 31 a3 31 75 31 8e 31 9d 31 91 31 9a 31 7e 31 8b 31 85 31 7e 31 b8 7e 41 80 16 7f d3 7f 00 00 77 
ff 3c 31 81 31 6c 31 66 31 75 31 7e 31 94 31 c2 31 a9 31 ac 31 9d 31 8e 31 b5 31 8f 2c bb 31 9a 31 78 31 8e 31 8e 31 9d 31 91 31 78 31 91 31 7b 31 85 31 b8 7e 41 80 11 7f de 7f 00 00 60 
ff 3c 31 63 31 47 31 4e 31 5a 31 63 31 8b 31 a9 31 97 31 97 31 7b 31 7b 31 9d 31 1e 2c a0 31 85 31 63 31 6c 31 78 31 88 31 72 31 66 31 6c 31 60 31 6c 31 bd 7e 47 80 06 7f e4 7f 00 00 aa 
ff 3c 31 54 31 41 31 47 31 44 31 5d 31 85 31 9a 31 9d 31 91 31 75 31 75 31 85 31 e4 2b 91 31 7e 31 4e 31 66 31 72 31 72 31 75 31 5a 31 5d 31 5d 31 57 31 b2 7e 47 80 06 7f de 7f 00 00 42 
ff 3c 31 3e 31 3e 31 3e 31 3e 31 5d 31 72 31 97 31 97 31 7e 31 78 31 6c 31 7e 31 b6 2b 97 31 75 31 4b 31 66 31 5a 31 78 31 6c 31 4e 31 60 31 4e 31 57 31 b8 7e 41 80 0b 7f ce 7f 00 00 ee 
ff 3c 31 3b 31 3b 31 2f 31 41 31 57 31 6f 31 9a 31 8e 31 7b 31 72 31 60 31 8b 31 ad 2b 88 31 6f 31 4e 31 54 31 60 31 72 31 5d 31 51 31 51 31 4b 31 57 31 b8 7e 47 80 16 7f d3 7f 00 00 70 
ff 3c 31 51 31 38 31 2f 31 41 31 47 31 75 31 9a 31 85 31 81 31 6c 31 60 31 85 31 98 2b 85 31 75 31 41 31 5a 31 63 31 66 31 69 31 4b 31 4e 31 51 31 47 31 b2 7e 41 80 11 7f e4 7f 00 00 c1 
ff 3c 31 47 31 32 31 38 31 3e 31 4e 31 75 31 8e 31 88 31 81 31 66 31 69 31 85 31 95 2b 91 31 6f 31 44 31 60 31 54 31 72 31 63 31 4b 31 57 31 4b 31 51 31 b8 7e 47 80 00 7f de 7f 00 00 81 
ff 3c 31 35 31 2f 31 35 31 35 31 51 31 78 31 8e 31 94 31 7b 31 66 31 66 31 75 31 9b 2b 85 31 6f 31 4b 31 54 31 5d 31 72 31 5a 31 4e 31 4e 31 47 31 51 31 b2 7e 47 80 0b 7f de 7f 00 00 e3 
ff 3c 31 35 31 38 31 35 31 35 31 54 31 69 31 94 31 91 31 78 31 6f 31 60 31 78 31 8f 2b 85 31 72 31 3e 31 57 31 60 31 66 31 66 31 4b 31 4b 31 4e 31 47 31 b2 7e 47 80 11 7f d3 7f 00 00 9c 
ff 3c 31 3e 31 38 31 2c 31 41 31 51 31 6c 31 97 31 81 31 7b 31 6f 31 5d 31 88 31 82 2b 8e 31 6c 31 44 31 5d 31 54 31 75 31 63 31 44 31 54 31 44 31 4e 31 b8 7e 47 80 16 7f de 7f 00 00 7e 
ff 3c 31 47 31 2f 31 2f 31 3e 31 47 31 75 31 9a 31 81 31 7e 31 63 31 60 31 85 31 8f 2b 88 31 69 31 47 31 51 31 5a 31 72 31 54 31 4b 31 4e 31 44 31 51 31 b8 7e 47 80 0b 7f e9 7f 00 00 48 
ff 3c 31 41 31 2c 31 35 31 32 31 47 31 75 31 8b 31 8e 31 81 31 63 31 66 31 75 31 7f 2b 81 31 72 31 3b 31 54 31 60 31 63 31 63 31 47 31 47 31 4e 31 41 31 b2 7e 47 80 00 7f e4 7f 00 00 d8 
ff 3c 31 2c 31 32 31 32 31 35 31 54 31 6c 31 8b 31 91 31 75 31 69 31 63 31 75 31 79 2b 8e 31 6c 31 41 31 5d 31 51 31 72 31 60 31 44 31 54 31 44 31 4b 31 b2 7e 41 80 0b 7f d9 7f 00 00 22 
ff 3c 31 3b 31 3b 31 32 31 3b 31 57 31 6c 31 9d 31 91 31 7b 31 72 31 5d 31 81 31 a4 2b 8e 31 6c 31 4b 31 57 31 63 31 75 31 5d 31 51 31 51 31 47 31 54 31 b8 7e 47 80 16 7f d9 7f 00 00 30 
ff 3c 31 4e 31 3b 31 32 31 44 31 4e 31 72 31 9d 31 85 31 85 31 72 31 63 31 8b 31 9b 2b 88 31 75 31 41 31 5a 31 6c 31 69 31 69 31 4e 31 4e 31 51 31 4b 31 b2 7e 47 80 11 7f e4 7f 00 00 da 
ff 3c 31 4b 31 32 31 35 31 44 31 51 31 78 31 97 31 85 31 85 31 69 31 69 31 8b 31 95 2b 94 31 72 31 44 31 63 31 5d 31 75 31 69 31 4b 31 5a 31 4e 31 4e 31 b2 7e 47 80 06 7f ef 7f 00 00 cc 
ff 3c 31 44 31 35 31 3b 31 3b 31 54 31 78 31 91 31 91 31 85 31 69 31 6c 31 78 31 a7 2b 91 31 6f 31 4e 31 5a 31 60 31 75 31 5d 31 51 31 54 31 47 31 57 31 b8 7e 47 80 06 7f e9 7f 00 00 4c 
ff 3c 31 3b 31 3b 31 3b 31 3b 31 5a 31 6f 31 94 31 94 31 7e 31 78 31 6c 31 7e 31 a4 2b 8b 31 78 31 44 31 5d 31 6f 31 69 31 6f 31 51 31 51 31 54 31 4b 31 b8 7e 47 80 0b 7f d9 7f 00 00 dd 
ff 3c 31 3b 31 3e 31 32 31 47 31 5d 31 6f 31 a0 31 8b 31 7e 31 78 31 63 31 8e 31 9e 2b 97 31 78 31 44 31 66 31 5d 31 72 31 6c 31 4e 31 5d 31 51 31 51 31 b8 7e 47 80 16 7f e4 7f 00 00 65 
ff 3c 31 5a 31 38 31 35 31 47 31 51 31 78 31 9d 31 85 31 88 31 6f 31 66 31 8e 31 b0 2b 94 31 72 31 51 31 5d 31 60 31 7e 31 60 31 57 31 57 31 4e 31 5a 31 b8 7e 47 80 11 7f ef 7f 00 00 f6 
ff 3c 31 4e 31 35 31 41 31 47 31 54 31 7b 31 94 31 8e 31 8b 31 6f 31 75 31 8b 31 b3 2b 8e 31 78 31 4b 31 5d 31 72 31 6c 31 6f 31 54 31 54 31 57 31 51 31 b8 7e 47 80 00 7f ef 7f 00 00 8f 
ff 3c 31 3e 31 3b 31 41 31 41 31 5d 31 7e 31 97 31 94 31 81 31 6f 31 6f 31 7e 31 aa 2b 9d 31 78 31 4b 31 69 31 60 31 78 31 72 31 51 31 63 31 54 31 54 31 b8 7e 47 80 0b 7f e9 7f 00 00 1b 
ff 3c 31 44 31 41 31 38 31 41 31 5d 31 72 31 a0 31 9a 31 85 31 7b 31 69 31 85 31 bc 2b 94 31 75 31 51 31 5d 31 69 31 7b 31 63 31 57 31 5d 31 51 31 5d 31 b8 7e 47 80 11 7f de 7f 00 00 84 
ff 3c 31 4b 31 44 31 3b 31 4e 31 5d 31 75 31 a6 31 8e 31 88 31 7b 31 69 31 94 31 bc 2b 91 31 7b 31 4e 31 60 31 78 31 6f 31 6f 31 57 31 57 31 5a 31 57 31 b8 7e 47 80 11 7f e9 7f 00 00 97 
ff 3c 31 57 31 3b 31 3b 31 4e 31 57 31 81 31 a6 31 91 31 8e 31 72 31 6c 31 91 31 b0 2b 9a 31 7b 31 4b 31 69 31 66 31 78 31 72 31 54 31 63 31 57 31 54 31 b8 7e 47 80 0b 7f fa 7f 00 00 35 
ff 3c 31 57 31 3e 31 44 31 44 31 57 31 81 31 94 31 94 31 8e 31 72 31 75 31 85 31 c6 2b 9a 31 78 31 57 31 63 31 66 31 7e 31 66 31 5a 31 60 31 51 31 60 31 b8 7e 47 80 00 7f f4 7f 00 00 34 
ff 3c 31 3e 31 44 31 44 31 44 31 63 31 78 31 9a 31 9a 31 85 31 7b 31 72 31 85 31 c3 2b 91 31 7e 31 51 31 63 31 75 31 6f 31 6f 31 5d 31 5a 31 5d 31 57 31 b8 7e 47 80 0b 7f e9 7f 00 00 fa 
ff 3c 31 47 31 47 31 3b 31 4b 31 63 31 75 31 a9 31 9a 31 88 31 7e 31 69 31 8e 31 b9 2b 9d 31 7b 31 4e 31 6c 31 69 31 75 31 78 31 54 31 63 31 57 31 57 31 b8 7e 47 80 16 7f e9 7f 00 00 83 
ff 3c 31 5d 31 47 31 3e 31 51 31 5a 31 7b 31 a9 31 8e 31 8e 31 7e 31 6c 31 94 31 cf 2b 9d 31 78 31 57 31 66 31 69 31 85 31 69 31 5d 31 63 31 54 31 63 31 b8 7e 4c 80 11 7f f4 7f 00 00 14 
ff 3c 31 57 31 3e 31 44 31 51 31 5d 31 81 31 a0 31 91 31 8e 31 72 31 75 31 94 31 cc 2b 97 31 7e 31 51 31 63 31 7b 31 72 31 75 31 5d 31 5d 31 5d 31 5a 31 b8 7e 47 80 06 7f 00 80 00 00 0f 
ff 3c 31 4e 31 3e 31 47 31 44 31 5d 31 85 31 9d 31 9a 31 8e 31 75 31 75 31 81 31 bc 2b 9d 31 7b 31 4e 31 6c 31 6c 31 78 31 75 31 54 31 63 31 5a 31 57 31 b8 7e 47 80 06 7f f4 7f 00 00 64 
ff 3c 31 47 31 4b 31 47 31 47 31 66 31 78 31 9d 31 a0 31 88 31 81 31 72 31 88 31 cf 2b 9d 31 78 31 57 31 69 31 66 31 81 31 69 31 5d 31 66 31 54 31 63 31 b8 7e 47 80 0b 7f e9 7f 00 00 be 
ff 3c 31 47 31 47 31 3e 31 51 31 63 31 78 31 a9 31 97 31 88 31 7e 31 6c 31 97 31 cf 2b 97 31 7e 31 54 31 63 31 78 31 75 31 6f 31 5d 31 5d 31 5d 31 5d 31 b8 7e 47 80 16 7f f4 7f 00 00 c0 
ff 3c 31 60 31 44 31 41 31 51 31 5a 31 81 31 ac 31 91 31 91 31 78 31 6f 31 97 31 c3 2b 9d 31 7e 31 4e 31 6f 31 6f 31 78 31 78 31 57 31 63 31 5d 31 5a 31 b8 7e 47 80 0b 7f 00 80 00 00 7c 
ff 3c 31 5a 31 41 31 4b 31 4e 31 5d 31 85 31 9d 31 94 31 94 31 78 31 7b 31 91 31 d2 2b a3 31 7b 31 5a 31 69 31 66 31 81 31 6c 31 5d 31 69 31 57 31 66 31 b8 7e 47 80 00 7f 00 80 00 00 97 
ff 3c 31 47 31 44 31 4b 31 4b 31 69 31 85 31 a0 31 a0 31 8b 31 78 31 78 31 88 31 db 2b 97 31 81 31 57 31 63 31 7e 31 78 31 6f 31 60 31 60 31 60 31 60 31 b8 7e 47 80 0b 7f f4 7f 00 00 95 
ff 3c 31 4e 31 4e 31 44 31 4b 31 69 31 78 31 a6 31 a0 31 8b 31 85 31 6f 31 8e 31 cf 2b a0 31 81 31 51 31 72 31 72 31 75 31 7b 31 5d 31 66 31 60 31 5a 31 b8 7e 47 80 11 7f f4 7f 00 00 b4 
ff 3c 31 57 31 4e 31 44 31 57 31 63 31 7e 31 ac 31 91 31 8e 31 81 31 72 31 9a 31 d8 2b a0 31 7b 31 5a 31 69 31 6c 31 85 31 6c 31 60 31 69 31 57 31 66 31 b8 7e 4c 80 11 7f 00 80 00 00 b3 
ff 3c 31 5d 31 41 31 47 31 54 31 60 31 88 31 a9 31 94 31 94 31 78 31 75 31 97 31 de 2b 97 31 85 31 57 31 66 31 7e 31 7b 31 72 31 66 31 60 31 60 31 60 31 b8 7e 4c 80 0b 7f 0a 80 00 00 bb 
ff 3c 31 5a 31 44 31 4b 31 4b 31 60 31 88 31 a0 31 9a 31 94 31 7b 31 7b 31 8e 31 cf 2b 9d 31 85 31 54 31 72 31 72 31 78 31 7e 31 5d 31 66 31 63 31 5d 31 b8 7e 47 80 06 7f 05 80 00 00 bc 
ff 3c 31 44 31 4b 31 4e 31 4e 31 69 31 7e 31 9d 31 a0 31 8b 31 81 31 78 31 8b 31 d2 2b a3 31 7b 31 5a 31 6c 31 66 31 85 31 6f 31 60 31 69 31 57 31 66 31 b8 7e 47 80 0b 7f f4 7f 00 00 bd 
ff 3c 31 4b 31 4e 31 41 31 51 31 69 31 7b 31 ac 31 9d 31 8e 31 85 31 6f 31 91 31 de 2b 9a 31 81 31 5a 31 66 31 7e 31 7b 31 6f 31 63 31 60 31 60 31 63 31 b8 7e 4c 80 16 7f fa 7f 00 00 a1 
ff 3c 31 63 31 4b 31 44 31 57 31 5d 31 81 31 ac 31 94 31 94 31 81 31 72 31 9a 31 cc 2b 9d 31 85 31 51 31 72 31 75 31 78 31 7e 31 5d 31 69 31 63 31 5a 31 b8 7e 47 80 11 7f 0a 80 00 00 59 
ff 3c 31 5a 31 41 31 4b 31 54 31 60 31 88 31 a3 31 94 31 94 31 78 31 7b 31 97 31 cc 2b a3 31 7b 31 5a 31 6f 31 69 31 85 31 6f 31 60 31 69 31 5a 31 66 31 b8 7e 47 80 00 7f 0a 80 00 00 af 
ff 3c 31 4e 31 44 31 4b 31 4b 31 66 31 88 31 a0 31 9d 31 91 31 7b 31 78 31 88 31 d8 2b 9a 31 85 31 5a 31 66 31 7e 31 7e 31 72 31 63 31 60 31 60 31 63 31 b8 7e 4c 80 06 7f 05 80 00 00 ab 
ff 3c 31 4b 31 4b 31 4b 31 4b 31 66 31 78 31 a3 31 a0 31 8b 31 85 31 75 31 8e 31 c6 2b 9d 31 85 31 51 31 72 31 72 31 78 31 7b 31 5d 31 66 31 60 31 5a 31 b8 7e 47 80 11 7f fa 7f 00 00 98 
ff 3c 31 4b 31 4b 31 41 31 54 31 69 31 7b 31 ac 31 94 31 8b 31 81 31 72 31 97 31 c6 2b a0 31 7b 31 57 31 6f 31 69 31 88 31 72 31 5d 31 69 31 57 31 63 31 bd 7e 47 80 16 7f 05 80 00 00 99 
ff 3c 31 4b 31 35 31 2c 31 41 31 4b 31 72 31 9d 31 81 31 85 31 6c 31 60 31 88 31 7f 2b 88 31 72 31 44 31 54 31 66 31 6f 31 5d 31 51 31 4b 31 4b 31 4e 31 b8 7e 4c 80 11 7f 10 80 00 00 0a 
ff 3c 31 8a 30 78 30 75 30 87 30 a6 30 da 30 01 31 f2 30 ec 30 cd 30 d0 30 e0 30 6c 28 ef 30 d7 30 8a 30 b5 30 b8 30 cd 30 be 30 a3 30 84 30 a3 30 90 30 b8 7e 41 80 00 7f 10 80 00 00 d6 
ff 3c 31 ab 2f b8 2f ab 2f be 2f fe 2f 38 30 6f 30 5c 30 44 30 2f 30 2f 30 2f 30 b7 25 59 30 29 30 d3 2f 0d 30 f5 2f 41 30 07 30 e5 2f b5 2f dc 2f d6 2f bd 7e 47 80 0b 7f 00 80 00 00 9f 
ff 3c 31 eb 2e fe 2e dc 2e 04 2f 50 2f 8a 2f e9 2f c1 2f a5 2f 93 2f 84 2f 93 2f c3 23 b8 2f 90 2f 28 2f 5f 2f 59 2f a5 2f 62 2f 44 2f e5 2e 34 2f 28 2f b8 7e 47 80 11 7f fa 7f 00 00 4a 
ff 3c 31 7a 2e 87 2e 5c 2e 90 2e d9 2e 2b 2f 8a 2f 50 2f 44 2f 28 2f 19 2f 2e 2f 95 22 4a 2f 25 2f a5 2e f4 2e e2 2e 31 2f f7 2e c4 2e 5c 2e c0 2e a2 2e b8 7e 47 80 11 7f 05 80 00 00 dc 
ff 3c 31 6b 2e 71 2e 50 2e 80 2e c7 2e 1f 2f 78 2f 44 2f 38 2f 13 2f 13 2f 1f 2f db 22 41 2f 13 2f 9c 2e eb 2e ca 2e 2e 2f e2 2e b4 2e 53 2e ab 2e 9f 2e bd 7e 4c 80 06 7f 05 80 00 00 d0 
ff 3c 31 74 2e 80 2e 65 2e 8a 2e d6 2e 2e 2f 7b 2f 50 2f 41 2f 1f 2f 1c 2f 1f 2f 58 23 47 2f 22 2f ab 2e ee 2e e2 2e 34 2f ee 2e c7 2e 5f 2e bd 2e ae 2e b8 7e 47 80 06 7f 00 80 00 00 a6 
ff 3c 31 3d 2e 50 2e 31 2e 59 2e ab 2e 01 2f 59 2f 2e 2f 13 2f f4 2e ee 2e f4 2e f3 22 1c 2f f7 2e 74 2e c7 2e b1 2e 07 2f c7 2e 96 2e 28 2e 93 2e 77 2e bd 7e 47 80 0b 7f fa 7f 00 00 51 
ff 3c 31 13 2f 22 2f 01 2f 28 2f 65 2f 9f 2f f5 2f cd 2f bb 2f a5 2f 93 2f a8 2f 71 25 ca 2f a2 2f 3b 2f 7e 2f 68 2f b5 2f 7b 2f 4d 2f 10 2f 47 2f 41 2f b8 7e 47 80 11 7f fa 7f 00 00 b3 
ff 3c 31 b5 2f b2 2f 9c 2f be 2f e5 2f 22 30 66 30 3b 30 38 30 1f 30 10 30 32 30 2c 27 41 30 1f 30 d0 2f f8 2f fb 2f 29 30 fe 2f df 2f ab 2f d3 2f d9 2f bd 7e 4c 80 11 7f 00 80 00 00 56 
ff 3c 31 4d 30 3b 30 38 30 47 30 69 30 9d 30 ca 30 b5 30 af 30 8d 30 8d 30 a6 30 d4 28 b5 30 9d 30 53 30 7e 30 84 30 96 30 87 30 63 30 4a 30 66 30 56 30 b8 7e 47 80 06 7f 05 80 00 00 3e 
ff 3c 31 b3 32 9d 32 b6 32 a3 32 9d 32 9a 32 a3 32 b0 32 a3 32 97 32 94 32 a9 32 04 31 a0 32 85 32 8b 32 88 32 9a 32 7f 32 8b 32 82 32 cb 32 82 32 8e 32 bd 7e 47 80 0b 7f f4 7f 00 00 da 
ff 3c 31 91 32 88 32 91 32 85 32 85 32 7f 32 97 32 9a 32 8b 32 8b 32 79 32 97 32 7e 31 85 32 6c 32 6c 32 63 32 8b 32 63 32 6c 32 6f 32 a0 32 69 32 76 32 b8 7e 4c 80 1c 7f e9 7f 00 00 29 
ff 3c 31 6f 32 5a 32 60 32 63 32 5d 32 60 32 7c 32 73 32 6f 32 66 32 54 32 82 32 47 31 63 32 51 32 3c 32 48 32 60 32 3c 32 54 32 42 32 73 32 45 32 48 32 b8 7e 47 80 1c 7f ef 7f 00 00 12 
ff 3c 31 4e 32 2f 32 39 32 3c 32 36 32 45 32 5d 32 51 32 57 32 3f 32 20 32 60 32 e3 30 4b 32 2f 32 1d 32 23 32 36 32 29 32 2c 32 1d 32 4b 32 1a 32 29 32 bd 7e 47 80 16 7f fa 7f 00 00 3b 
ff 3c 31 1d 32 e6 31 f5 31 ef 31 f2 31 0b 32 3c 32 39 32 36 32 11 32 05 32 36 32 44 30 26 32 05 32 f8 31 f8 31 1a 32 02 32 02 32 ff 31 17 32 f5 31 08 32 bd 7e 4c 80 0b 7f f4 7f 00 00 9e 
ff 3c 31 ce 31 c5 31 d1 31 c8 31 da 31 e9 31 ff 31 08 32 fc 31 e3 31 e3 31 f5 31 6b 2f 02 32 ef 31 ce 31 da 31 f5 31 dd 31 ec 31 d7 31 ef 31 da 31 da 31 bd 7e 47 80 0b 7f e4 7f 00 00 49 
ff 3c 31 e3 31 dd 31 dd 31 dd 31 ec 31 ef 31 1d 32 2f 32 14 32 ff 31 e6 31 0e 32 d6 2f 1d 32 f8 31 e3 31 f5 31 fc 31 f8 31 f8 31 e6 31 0b 32 e3 31 f2 31 bd 7e 47 80 1c 7f de 7f 00 00 fc 
ff 3c 31 c8 31 b2 31 b2 31 be 31 be 31 d4 31 f8 31 e3 31 e6 31 d7 31 c8 31 f8 31 0a 2f f2 31 d7 31 c2 31 c5 31 e3 31 d7 31 cb 31 c8 31 da 31 c2 31 ce 31 bd 7e 52 80 16 7f ef 7f 00 00 34 
ff 3c 31 5a 31 41 31 47 31 54 31 5d 31 85 31 a6 31 94 31 94 31 75 31 78 31 9a 31 46 2c 97 31 85 31 51 31 6c 31 7b 31 75 31 7b 31 5d 31 60 31 63 31 60 31 bd 7e 4c 80 0b 7f f4 7f 00 00 23 
ff 3c 31 44 31 38 31 3e 31 3b 31 57 31 7b 31 97 31 94 31 88 31 6c 31 6f 31 7e 31 de 2b 97 31 75 31 47 31 63 31 60 31 75 31 69 31 4e 31 5d 31 4e 31 57 31 bd 7e 4c 80 0b 7f e9 7f 00 00 37 
ff 3c 31 26 31 2c 31 29 31 2c 31 47 31 60 31 88 31 85 31 6f 31 66 31 5d 31 72 31 7c 2b 7e 31 63 31 3b 31 4b 31 57 31 69 31 4e 31 41 31 41 31 3b 31 47 31 c3 7e 52 80 11 7f de 7f 00 00 a9 
ff 3c 31 f2 30 f5 30 ec 30 fb 30 1a 31 32 31 69 31 51 31 44 31 38 31 29 31 4e 31 60 2a 51 31 3b 31 01 31 20 31 2f 31 2f 31 2c 31 11 31 04 31 11 31 0a 31 b8 7e 4c 80 1c 7f e4 7f 00 00 f6 
ff 3c 31 01 31 ef 30 e6 30 f8 30 0a 31 32 31 63 31 44 31 47 31 2f 31 23 31 4b 31 4b 2a 54 31 32 31 fb 30 1d 31 1d 31 35 31 26 31 04 31 07 31 04 31 04 31 c3 7e 47 80 16 7f ef 7f 00 00 bc 
ff 3c 31 07 31 f2 30 f8 30 04 31 14 31 3e 31 5d 31 51 31 51 31 32 31 35 31 51 31 97 2a 5a 31 38 31 0d 31 20 31 29 31 3b 31 23 31 17 31 11 31 0d 31 1a 31 c3 7e 52 80 0b 7f fa 7f 00 00 58 
ff 3c 31 ac 30 ac 30 ac 30 b2 30 da 30 04 31 2c 31 20 31 11 31 f8 30 fb 30 04 31 5a 29 1a 31 01 31 c1 30 e3 30 ef 30 f8 30 ef 30 d4 30 bb 30 d0 30 ca 30 bd 7e 4c 80 11 7f ef 7f 00 00 d0 
ff 3c 31 9c 2f a8 2f 93 2f af 2f ec 2f 1f 30 69 30 4d 30 35 30 26 30 16 30 29 30 53 25 4a 30 1f 30 c4 2f 01 30 e9 2f 32 30 01 30 d6 2f a5 2f d3 2f ca 2f bd 7e 47 80 1c 7f e4 7f 00 00 7b 
ff 3c 31 38 2f 3e 2f 1c 2f 47 2f 84 2f c4 2f 16 30 e9 2f dc 2f c7 2f b5 2f d0 2f 65 24 e9 2f c1 2f 5f 2f 93 2f 87 2f d6 2f 90 2f 75 2f 2b 2f 68 2f 65 2f c3 7e 52 80 1c 7f ef 7f 00 00 0a 
ff 3c 31 47 2f 44 2f 2e 2f 53 2f 87 2f cd 2f 19 30 ec 2f e5 2f c4 2f c1 2f d6 2f f7 24 ec 2f cd 2f 62 2f 9f 2f 96 2f d0 2f a5 2f 7e 2f 34 2f 78 2f 62 2f bd 7e 4c 80 16 7f fa 7f 00 00 95 
ff 3c 31 ab 2f ab 2f 9c 2f b5 2f e5 2f 29 30 60 30 44 30 38 30 19 30 19 30 22 30 81 26 44 30 1f 30 c7 2f fe 2f f2 2f 29 30 01 30 d9 2f ab 2f d6 2f ca 2f c8 7e 4c 80 0b 7f f4 7f 00 00 12 
ff 3c 31 14 32 f2 31 0b 32 fc 31 fc 31 02 32 26 32 39 32 2c 32 11 32 ff 31 26 32 7a 2e 26 32 05 32 ff 31 ff 31 17 32 05 32 02 32 ff 31 23 32 f5 31 08 32 c3 7e 52 80 16 7f e9 7f 00 00 fd 
ff 3c 31 26 31 29 31 20 31 29 31 44 31 57 31 88 31 7b 31 69 31 5d 31 4e 31 6f 31 98 2b 6f 31 60 31 2f 31 44 31 54 31 54 31 51 31 3b 31 38 31 3b 31 38 31 bd 7e 52 80 21 7f e9 7f 00 00 90 
ff 3c 31 1a 32 f2 31 f2 31 f8 31 f5 31 05 32 42 32 2f 32 32 32 23 32 fc 31 3f 32 fa 2e 29 32 0b 32 f2 31 05 32 11 32 05 32 0b 32 f8 31 23 32 fc 31 02 32 bd 7e 4c 80 1c 7f f4 7f 00 00 4e 
ff 3c 31 ef 31 c8 31 d7 31 d7 31 d7 31 f2 31 0e 32 02 32 11 32 e6 31 e9 31 1a 32 c7 2e 0e 32 ec 31 e0 31 e0 31 f2 31 ef 31 e6 31 e3 31 ff 31 d7 31 ec 31 c3 7e 57 80 11 7f 00 80 00 00 66 
ff 3c 31 0e 32 e0 31 f2 31 e6 31 ef 31 05 32 2c 32 3c 32 2c 32 02 32 ff 31 29 32 53 2f 1a 32 08 32 ec 31 f2 31 17 32 f5 31 05 32 f8 31 0e 32 f5 31 f8 31 bd 7e 52 80 16 7f f4 7f 00 00 5b 
ff 3c 31 85 31 88 31 88 31 85 31 9a 31 a9 31 ce 31 cb 31 b8 31 b2 31 a6 31 be 31 68 2d d1 31 af 31 8b 31 a6 31 a9 31 af 31 ac 31 91 31 a9 31 94 31 97 31 c8 7e 4c 80 1c 7f e4 7f 00 00 1d 
ff 3c 31 47 31 41 31 3b 31 4b 31 5d 31 75 31 a3 31 94 31 88 31 78 31 69 31 94 31 0f 2c 94 31 75 31 51 31 60 31 6c 31 7b 31 66 31 57 31 5d 31 51 31 60 31 c8 7e 57 80 21 7f ef 7f 00 00 4e 
ff 3c 31 d4 30 c1 30 bb 30 cd 30 e6 30 11 31 41 31 26 31 26 31 0d 31 04 31 26 31 b6 29 29 31 14 31 d4 30 f2 30 04 31 0a 31 fe 30 e6 30 d0 30 e3 30 dd 30 c3 7e 57 80 16 7f fa 7f 00 00 3c 
ff 3c 31 a3 30 93 30 90 30 a0 30 bb 30 ec 30 17 31 04 31 01 31 e3 30 e3 30 f8 30 fe 28 0a 31 e9 30 a6 30 d0 30 d0 30 e9 30 d7 30 b5 30 a6 30 b5 30 af 30 c3 7e 4c 80 11 7f fa 7f 00 00 be 
ff 3c 31 84 30 84 30 81 30 87 30 b2 30 e0 30 0a 31 fe 30 ec 30 d7 30 d4 30 dd 30 e0 28 fb 30 d7 30 a0 30 be 30 bb 30 e3 30 be 30 a9 30 96 30 a0 30 a9 30 c8 7e 57 80 11 7f ef 7f 00 00 1b 
ff 3c 31 7e 30 87 30 78 30 87 30 b2 30 cd 30 0d 31 fe 30 e6 30 da 30 c7 30 e3 30 ec 28 ef 30 da 30 96 30 b5 30 c7 30 d4 30 be 30 a9 30 8a 30 a3 30 a0 30 c3 7e 57 80 21 7f e4 7f 00 00 5e 
ff 3c 31 a6 31 9a 31 94 31 a0 31 a6 31 b5 31 e0 31 c8 31 c8 31 be 31 ac 31 da 31 40 2d dd 31 be 31 97 31 b5 31 bb 31 b5 31 be 31 a0 31 be 31 a6 31 a9 31 c8 7e 4c 80 21 7f ef 7f 00 00 36 
ff 3c 31 3b 31 20 31 26 31 32 31 3e 31 69 31 8b 31 75 31 75 31 5a 31 57 31 78 31 8c 2b 81 31 60 31 3b 31 4b 31 51 31 69 31 4e 31 41 31 47 31 38 31 47 31 c8 7e 57 80 16 7f 00 80 00 00 2b 
ff 3c 31 75 31 63 31 6c 31 66 31 7b 31 97 31 b2 31 b2 31 a6 31 8e 31 8e 31 a0 31 83 2c ac 31 9a 31 75 31 81 31 9d 31 8e 31 8b 31 7b 31 81 31 7b 31 81 31 c3 7e 57 80 0b 7f f4 7f 00 00 aa 
ff 3c 31 85 31 81 31 88 31 85 31 9a 31 ac 31 cb 31 cb 31 b8 31 ac 31 a6 31 be 31 1e 2d d1 31 b2 31 8b 31 a3 31 ac 31 ac 31 ac 31 91 31 a9 31 94 31 9a 31 c8 7e 52 80 1c 7f ef 7f 00 00 7a 
ff 3c 31 7b 31 78 31 72 31 7b 31 8e 31 9d 31 cb 31 be 31 af 31 a6 31 94 31 b8 31 f1 2c c2 31 a3 31 85 31 94 31 9a 31 a9 31 97 31 88 31 9a 31 81 31 94 31 ce 7e 57 80 21 7f ef 7f 00 00 d2 
ff 3c 31 78 31 63 31 5d 31 6c 31 75 31 91 31 bb 31 a6 31 a6 31 94 31 85 31 af 31 95 2c ac 31 97 31 6f 31 7b 31 94 31 8e 31 88 31 78 31 7b 31 78 31 7b 31 c8 7e 57 80 1c 7f fa 7f 00 00 74 
ff 3c 31 72 31 5a 31 63 31 69 31 72 31 97 31 b2 31 a3 31 a6 31 8b 31 8b 31 ac 31 80 2c af 31 97 31 66 31 85 31 8e 31 8b 31 8e 31 72 31 7e 31 78 31 72 31 c8 7e 52 80 16 7f 00 80 00 00 97 
ff 3c 31 5d 31 54 31 60 31 5a 31 72 31 94 31 ac 31 ac 31 9d 31 85 31 88 31 97 31 67 2c af 31 8b 31 6c 31 7b 31 7e 31 94 31 7e 31 6f 31 7e 31 69 31 7b 31 ce 7e 5d 80 11 7f f4 7f 00 00 89 
ff 3c 31 63 31 66 31 63 31 63 31 7e 31 8b 31 b5 31 b2 31 a0 31 97 31 8b 31 a3 31 8f 2c ac 31 97 31 6f 31 7b 31 97 31 8e 31 85 31 7b 31 7b 31 78 31 78 31 c8 7e 5d 80 21 7f e4 7f 00 00 6a 
ff 3c 31 78 31 75 31 6f 31 7e 31 8b 31 9d 31 c8 31 b2 31 af 31 a3 31 94 31 c2 31 d8 2c be 31 a9 31 78 31 94 31 9d 31 9a 31 a0 31 81 31 97 31 88 31 88 31 c8 7e 52 80 21 7f f4 7f 00 00 19 
ff 3c 31 88 31 6c 31 6c 31 7b 31 81 31 a0 31 c8 31 b2 31 b2 31 9a 31 94 31 bb 31 d2 2c c2 31 9d 31 7e 31 91 31 91 31 a6 31 91 31 81 31 97 31 7e 31 8e 31 ce 7e 57 80 1c 7f 00 80 00 00 19 
ff 3c 31 5a 31 44 31 4e 31 4e 31 60 31 85 31 a0 31 97 31 94 31 78 31 7b 31 9a 31 12 2c 97 31 7e 31 57 31 63 31 7e 31 7b 31 75 31 63 31 60 31 5d 31 63 31 c8 7e 5d 80 11 7f fa 7f 00 00 d3 
ff 3c 31 3b 31 38 31 3e 31 3e 31 5a 31 7b 31 94 31 97 31 81 31 6f 31 6f 31 7e 31 c6 2b 91 31 78 31 44 31 63 31 69 31 6f 31 6c 31 4e 31 57 31 54 31 51 31 c8 7e 57 80 16 7f ef 7f 00 00 2f 
ff 3c 31 2f 31 32 31 29 31 2f 31 4e 31 60 31 91 31 8e 31 75 31 6c 31 5d 31 75 31 7c 2b 8b 31 66 31 3e 31 54 31 51 31 6c 31 57 31 44 31 4b 31 3e 31 4b 31 c8 7e 5d 80 21 7f ef 7f 00 00 42 
ff 3c 31 3b 31 32 31 26 31 38 31 44 31 63 31 94 31 78 31 78 31 6c 31 5a 31 85 31 85 2b 81 31 69 31 3e 31 4b 31 63 31 63 31 57 31 4b 31 41 31 44 31 47 31 c8 7e 62 80 21 7f f4 7f 00 00 c7 
ff 3c 31 47 31 2c 31 2f 31 3e 31 47 31 72 31 94 31 7e 31 81 31 63 31 63 31 85 31 92 2b 85 31 72 31 3b 31 5d 31 63 31 63 31 66 31 47 31 4e 31 4e 31 44 31 c8 7e 57 80 16 7f 05 80 00 00 5d 
ff 3c 31 44 31 2f 31 38 31 35 31 4e 31 72 31 8e 31 8e 31 85 31 66 31 69 31 75 31 9b 2b 91 31 6c 31 44 31 5a 31 57 31 75 31 5d 31 4b 31 54 31 44 31 51 31 c8 7e 5d 80 11 7f 00 80 00 00 3a 
ff 3c 31 32 31 35 31 35 31 38 31 54 31 6c 31 8e 31 91 31 78 31 6f 31 66 31 78 31 a1 2b 85 31 6f 31 47 31 51 31 66 31 6f 31 5a 31 4e 31 4b 31 4b 31 51 31 c8 7e 5d 80 1c 7f ef 7f 00 00 ba 
ff 3c 31 38 31 35 31 2c 31 38 31 54 31 69 31 9a 31 8e 31 78 31 6f 31 5d 31 81 31 8c 2b 88 31 6f 31 3b 31 5a 31 5d 31 66 31 66 31 47 31 4e 31 4b 31 47 31 c8 7e 57 80 27 7f fa 7f 00 00 02 
ff 3c 31 44 31 2f 31 26 31 38 31 41 31 66 31 94 31 78 31 7b 31 69 31 5a 31 7e 31 73 2b 8b 31 63 31 3b 31 54 31 4e 31 6c 31 57 31 41 31 4b 31 3b 31 47 31 c8 7e 5d 80 21 7f 00 80 00 00 dd 
ff 3c 31 32 31 1d 31 23 31 2c 31 38 31 66 31 81 31 75 31 72 31 57 31 5a 31 75 31 4b 2b 78 31 5d 31 35 31 41 31 54 31 5d 31 47 31 3b 31 35 31 38 31 3e 31 c8 7e 5d 80 16 7f 0a 80 00 00 43 
ff 3c 31 29 31 1d 31 23 31 20 31 3e 31 66 31 7e 31 7b 31 6c 31 54 31 57 31 63 31 3f 2b 78 31 63 31 29 31 4b 31 51 31 51 31 57 31 38 31 38 31 3b 31 32 31 c8 7e 57 80 16 7f 00 80 00 00 e1 
ff 3c 31 23 31 29 31 23 31 26 31 47 31 5a 31 8b 31 85 31 6c 31 66 31 54 31 6c 31 4b 2b 85 31 5d 31 32 31 4e 31 4b 31 66 31 54 31 38 31 47 31 35 31 3e 31 ce 7e 5d 80 27 7f f4 7f 00 00 65 
ff 3c 31 2f 31 2f 31 26 31 38 31 4b 31 63 31 94 31 7b 31 75 31 69 31 57 31 81 31 79 2b 7e 31 69 31 41 31 4b 31 63 31 63 31 54 31 47 31 41 31 41 31 4b 31 c8 7e 62 80 27 7f 00 80 00 00 b4 
ff 3c 31 44 31 29 31 26 31 35 31 44 31 6c 31 94 31 78 31 7b 31 60 31 5a 31 7e 31 73 2b 81 31 6c 31 32 31 51 31 5d 31 5a 31 63 31 41 31 47 31 47 31 3e 31 c8 7e 57 80 1c 7f 10 80 00 00 e6 
ff 3c 31 2f 31 1a 31 20 31 26 31 38 31 60 31 7e 31 75 31 72 31 54 31 57 31 6c 31 33 2b 7e 31 5a 31 2c 31 4b 31 41 31 60 31 4b 31 35 31 3b 31 32 31 38 31 c8 7e 5d 80 11 7f 0a 80 00 00 fb 
ff 3c 31 20 31 1d 31 23 31 23 31 41 31 63 31 81 31 7b 31 66 31 57 31 57 31 66 31 48 2b 78 31 5d 31 32 31 3e 31 54 31 5d 31 47 31 3b 31 38 31 35 31 3e 31 c8 7e 5d 80 1c 7f 00 80 00 00 5d 
ff 3c 31 26 31 29 31 20 31 29 31 44 31 5a 31 8e 31 85 31 6c 31 63 31 51 31 72 31 4f 2b 7b 31 66 31 2c 31 4b 31 57 31 57 31 5a 31 3e 31 3b 31 3e 31 38 31 c8 7e 57 80 27 7f 00 80 00 00 fd 
ff 3c 31 2f 31 29 31 1d 31 2f 31 3e 31 5d 31 8e 31 6f 31 72 31 63 31 51 31 7b 31 45 2b 81 31 60 31 2f 31 4e 31 4e 31 66 31 51 31 38 31 41 31 38 31 3e 31 c8 7e 5d 80 21 7f 05 80 00 00 e9 
ff 3c 31 3e 31 23 31 29 31 38 31 41 31 6c 31 8e 31 78 31 7b 31 5d 31 5d 31 81 31 76 2b 81 31 66 31 41 31 4b 31 5d 31 69 31 51 31 47 31 44 31 41 31 4b 31 ce 7e 62 80 16 7f 15 80 00 00 63 
ff 3c 31 3b 31 29 31 32 31 2f 31 4b 31 6f 31 8b 31 88 31 7b 31 63 31 63 31 6f 31 79 2b 81 31 6f 31 38 31 54 31 63 31 5d 31 66 31 44 31 47 31 4b 31 41 31 c8 7e 57 80 11 7f 0a 80 00 00 04 
ff 3c 31 26 31 2c 31 2c 31 2c 31 4b 31 60 31 88 31 88 31 72 31 66 31 60 31 72 31 64 2b 8b 31 63 31 38 31 57 31 4e 31 69 31 57 31 3e 31 4e 31 3e 31 47 31 c8 7e 5d 80 21 7f 00 80 00 00 1f 
ff 3c 31 38 31 3b 31 32 31 41 31 57 31 6f 31 9d 31 94 31 7b 31 72 31 60 31 8b 31 aa 2b 8b 31 6f 31 4b 31 54 31 66 31 75 31 5a 31 51 31 51 31 47 31 54 31 c8 7e 62 80 27 7f 05 80 00 00 36 
ff 3c 31 51 31 4b 31 4b 31 51 31 66 31 88 31 a6 31 a3 31 91 31 7b 31 75 31 94 31 de 2b 91 31 7e 31 57 31 69 31 66 31 7e 31 6f 31 5a 31 60 31 5a 31 63 31 c8 7e 5d 80 1c 7f 0a 80 00 00 0e 
ff 3c 31 54 31 4b 31 4e 31 51 31 66 31 8b 31 a6 31 a3 31 94 31 7e 31 75 31 97 31 e7 2b 94 31 7e 31 57 31 69 31 66 31 81 31 72 31 5d 31 63 31 5d 31 63 31 c8 7e 5d 80 21 7f 0a 80 00 00 ee 
ff 3c 31 54 31 4e 31 4e 31 54 31 66 31 8b 31 a6 31 a6 31 94 31 7e 31 78 31 97 31 ea 2b 94 31 7e 31 57 31 69 31 66 31 81 31 72 31 5d 31 63 31 5d 31 66 31 c8 7e 5d 80 21 7f 0a 80 00 00 ee 
ff 3c 31 54 31 4e 31 4e 31 54 31 69 31 8b 31 a9 31 a6 31 94 31 7e 31 78 31 97 31 ed 2b 94 31 81 31 5a 31 69 31 69 31 81 31 72 31 5d 31 63 31 5d 31 66 31 c8 7e 5d 80 1c 7f 0a 80 00 00 29 
ff 3c 31 57 31 4e 31 4e 31 54 31 66 31 8b 31 a9 31 a6 31 97 31 7e 31 78 31 9a 31 ed 2b 97 31 81 31 5a 31 6c 31 69 31 81 31 75 31 5d 31 63 31 5d 31 66 31 c8 7e 5d 80 21 7f 0a 80 00 00 17 
ff 3c 31 57 31 4e 31 4e 31 54 31 69 31 8e 31 a9 31 a6 31 97 31 7e 31 78 31 9a 31 f0 2b 97 31 81 31 5a 31 6c 31 69 31 81 31 75 31 60 31 66 31 60 31 66 31 ce 7e 5d 80 1c 7f 10 80 00 00 24 
ff 3c 31 57 31 4e 31 4e 31 54 31 69 31 8b 31 a9 31 a9 31 97 31 81 31 78 31 9a 31 f0 2b 97 31 81 31 5a 31 6c 31 69 31 85 31 75 31 60 31 66 31 60 31 66 31 c8 7e 5d 80 1c 7f 10 80 00 00 d3 
ff 3c 31 57 31 4e 31 51 31 54 31 69 31 8e 31 ac 31 a9 31 97 31 81 31 78 31 9a 31 f0 2b 97 31 81 31 5a 31 6c 31 69 31 85 31 75 31 60 31 66 31 60 31 66 31 ce 7e 5d 80 21 7f 10 80 00 00 f7 
ff 3c 31 57 31 4e 31 51 31 54 31 69 31 8e 31 a9 31 a9 31 97 31 81 31 7b 31 9a 31 f3 2b 97 31 81 31 5a 31 6c 31 6c 31 85 31 75 31 60 31 66 31 60 31 69 31 ce 7e 5d 80 1c 7f 15 80 00 00 c0 
ff 3c 31 57 31 51 31 51 31 54 31 6c 31 8e 31 ac 31 a9 31 97 31 81 31 7b 31 9a 31 f3 2b 97 31 85 31 5d 31 6c 31 69 31 85 31 75 31 60 31 66 31 60 31 69 31 ce 7e 5d 80 1c 7f 15 80 00 00 d9 
ff 3c 31 60 31 5a 31 5a 31 60 31 72 31 97 31 b2 31 b2 31 a0 31 8b 31 81 31 a3 31 15 2c 9d 31 8b 31 66 31 75 31 72 31 8b 31 7e 31 69 31 6f 31 69 31 72 31 ce 7e 5d 80 21 7f 15 80 00 00 d0 
ff 3c 31 60 31 5a 31 5a 31 60 31 75 31 97 31 b2 31 b2 31 a0 31 8b 31 81 31 a3 31 1b 2c a0 31 8b 31 66 31 75 31 72 31 8e 31 7e 31 69 31 72 31 69 31 72 31 ce 7e 5d 80 21 7f 15 80 00 00 fc 
ff 3c 31 63 31 5a 31 5d 31 60 31 75 31 9a 31 b5 31 b2 31 a0 31 8b 31 81 31 a3 31 1b 2c a0 31 8e 31 66 31 75 31 72 31 8e 31 7e 31 6c 31 72 31 69 31 72 31 ce 7e 5d 80 1c 7f 1b 80 00 00 c1 
ff 3c 31 63 31 5a 31 5d 31 60 31 75 31 9a 31 b5 31 b2 31 a0 31 8b 31 85 31 a3 31 1e 2c a0 31 8e 31 66 31 78 31 72 31 8e 31 7e 31 6c 31 72 31 6c 31 72 31 ce 7e 5d 80 21 7f 1b 80 00 00 f5 
ff 3c 31 63 31 5a 31 5d 31 60 31 75 31 9a 31 b5 31 b2 31 a3 31 8b 31 85 31 a3 31 21 2c a0 31 8e 31 66 31 78 31 75 31 8e 31 81 31 6c 31 72 31 6c 31 75 31 ce 7e 5d 80 21 7f 1b 80 00 00 36 
ff 3c 31 63 31 5d 31 5d 31 60 31 78 31 9a 31 b5 31 b5 31 a3 31 8e 31 85 31 a6 31 21 2c a0 31 91 31 66 31 78 31 75 31 8e 31 81 31 6c 31 72 31 6c 31 75 31 ce 7e 5d 80 21 7f 1b 80 00 00 24 
ff 3c 31 63 31 5d 31 5d 31 63 31 78 31 9a 31 b5 31 b5 31 a3 31 8e 31 85 31 a6 31 21 2c a0 31 91 31 69 31 7b 31 75 31 91 31 81 31 6c 31 75 31 6c 31 75 31 ce 7e 5d 80 21 7f 1b 80 00 00 33 
ff 3c 31 63 31 5d 31 60 31 63 31 78 31 9a 31 b5 31 b5 31 a3 31 8e 31 88 31 a6 31 24 2c a3 31 91 31 69 31 7b 31 75 31 91 31 81 31 6f 31 75 31 6c 31 75 31 ce 7e 5d 80 21 7f 1b 80 00 00 06 
ff 3c 31 66 31 5d 31 60 31 63 31 78 31 9d 31 b8 31 b5 31 a3 31 8e 31 88 31 a6 31 27 2c a3 31 91 31 69 31 7b 31 75 31 91 31 81 31 6f 31 75 31 6c 31 75 31 ce 7e 5d 80 21 7f 20 80 00 00 31 
ff 3c 31 66 31 5d 31 60 31 63 31 78 31 9d 31 b8 31 b5 31 a3 31 8e 31 88 31 a6 31 27 2c a3 31 91 31 69 31 7b 31 75 31 91 31 81 31 6f 31 75 31 6f 31 75 31 ce 7e 5d 80 21 7f 20 80 00 00 32 
ff 3c 31 66 31 60 31 60 31 66 31 7b 31 9d 31 b8 31 b8 31 a6 31 91 31 88 31 a9 31 2d 2c a3 31 91 31 69 31 7b 31 78 31 91 31 85 31 6f 31 78 31 6f 31 78 31 ce 7e 5d 80 21 7f 20 80 00 00 12 
ff 3c 31 66 31 60 31 60 31 66 31 7b 31 9d 31 b8 31 b8 31 a6 31 91 31 88 31 a9 31 2d 2c a3 31 91 31 6c 31 7b 31 78 31 91 31 85 31 6f 31 78 31 6f 31 78 31 ce 7e 5d 80 21 7f 20 80 00 00 17 
ff 3c 31 69 31 60 31 63 31 66 31 7b 31 9d 31 b8 31 b8 31 a6 31 91 31 88 31 a9 31 2d 2c a6 31 91 31 6c 31 7b 31 78 31 91 31 85 31 6f 31 78 31 6f 31 78 31 ce 7e 5d 80 21 7f 20 80 00 00 1e 
ff 3c 31 69 31 60 31 63 31 66 31 7b 31 9d 31 bb 31 b8 31 a6 31 91 31 8b 31 a9 31 2d 2c a6 31 94 31 6c 31 7e 31 78 31 94 31 85 31 72 31 78 31 72 31 78 31 ce 7e 5d 80 21 7f 20 80 00 00 1b 
ff 3c 31 69 31 60 31 63 31 66 31 7b 31 a0 31 bb 31 b8 31 a6 31 91 31 8b 31 a9 31 30 2c a6 31 94 31 6c 31 7e 31 78 31 94 31 85 31 72 31 78 31 72 31 78 31 ce 7e 5d 80 21 7f 20 80 00 00 3b 
ff 3c 31 69 31 60 31 63 31 66 31 7b 31 a0 31 bb 31 b8 31 a6 31 91 31 8b 31 a9 31 30 2c a6 31 94 31 6c 31 7e 31 7b 31 94 31 88 31 72 31 78 31 72 31 7b 31 ce 7e 5d 80 21 7f 26 80 00 00 30 
ff 3c 31 5d 31 57 31 57 31 5d 31 72 31 94 31 b2 31 af 31 9d 31 88 31 7e 31 a0 31 fc 2b 9a 31 88 31 63 31 72 31 6f 31 8b 31 7b 31 66 31 6c 31 66 31 6f 31 ce 7e 5d 80 21 7f 26 80 00 00 d1 
ff 3c 31 60 31 5a 31 5a 31 60 31 75 31 9a 31 b5 31 b2 31 a0 31 8b 31 85 31 a3 31 09 2c a0 31 8e 31 66 31 78 31 72 31 8e 31 7e 31 69 31 72 31 69 31 72 31 ce 7e 5d 80 21 7f 26 80 00 00 db 
ff 3c 31 60 31 5a 31 5a 31 60 31 75 31 9a 31 b5 31 b2 31 a0 31 8b 31 85 31 a3 31 06 2c a0 31 8b 31 66 31 75 31 72 31 8e 31 7e 31 69 31 6f 31 69 31 72 31 ce 7e 5d 80 21 7f 26 80 00 00 c1 
ff 3c 31 60 31 57 31 5a 31 5d 31 72 31 97 31 b2 31 b2 31 a0 31 8b 31 81 31 a3 31 fc 2b 9d 31 8b 31 63 31 75 31 72 31 8b 31 7e 31 69 31 6f 31 69 31 6f 31 ce 7e 5d 80 21 7f 26 80 00 00 25 
ff 3c 31 41 31 41 31 47 31 44 31 63 31 88 31 9d 31 a0 31 8b 31 c5 75 31 85 31 bc 2b 91 31 7e 31 54 31 63 31 75 31 78 31 6c 31 5d 31 57 31 5d 31 5d 31 ce 7e 62 80 1c 7f 20 80 00 00 5f 
ff 3c 31 3e 31 41 31 38 31 3e 31 60 31 6f 31 a3 31 9a 31 85 31 7b 31 69 31 85 31 8f 2b 97 31 7b 31 44 31 69 31 66 31 72 31 6f 31 51 31 5a 31 54 31 51 31 ce 7e 5d 80 27 7f 20 80 00 00 e4 
ff 3c 31 51 31 47 31 3b 31 4e 31 5d 31 7b 31 a6 31 91 31 8b 31 7e 31 6c 31 97 31 aa 2b 9a 31 75 31 54 31 66 31 5d 31 81 31 66 31 57 31 60 31 51 31 60 31 ce 7e 5d 80 27 7f 2b 80 00 00 3e 
ff 3c 31 4b 31 32 31 35 31 44 31 51 31 7b 31 a0 31 88 31 88 31 69 31 69 31 8e 31 85 2b 8b 31 75 31 47 31 57 31 6c 31 6f 31 66 31 54 31 4e 31 54 31 54 31 ce 7e 62 80 1c 7f 36 80 00 00 88 
ff 3c 31 51 31 3b 31 41 31 41 31 5a 31 81 31 9d 31 94 31 91 31 72 31 72 31 81 31 9b 2b 97 31 7b 31 47 31 69 31 69 31 72 31 75 31 54 31 60 31 5a 31 54 31 ce 7e 5d 80 16 7f 2b 80 00 00 1d 
ff 3c 31 2f 31 32 31 32 31 35 31 54 31 69 31 91 31 8e 31 78 31 6f 31 66 31 78 31 61 2b 8e 31 69 31 44 31 5a 31 54 31 72 31 57 31 47 31 51 31 41 31 51 31 d4 7e 5d 80 21 7f 20 80 00 00 40 
ff 3c 31 35 31 2c 31 29 31 2f 31 47 31 69 31 91 31 91 31 7b 31 63 31 5a 31 75 31 2a 2b 75 31 63 31 35 31 51 31 4b 31 66 31 54 31 3b 31 3b 31 3e 31 47 31 ce 7e 5d 80 21 7f 2b 80 00 00 d1 
ff 3c 31 57 31 44 31 3b 31 4b 31 54 31 75 31 a6 31 8b 31 8e 31 7b 31 6c 31 97 31 98 2b 94 31 7b 31 47 31 66 31 6c 31 6f 31 72 31 54 31 5a 31 5a 31 54 31 ce 7e 5d 80 21 7f 2b 80 00 00 c9 
ff 3c 31 4e 31 35 31 3b 31 47 31 54 31 7e 31 a0 31 8b 31 8b 31 6f 31 6f 31 91 31 8f 2b 9a 31 75 31 4e 31 63 31 5d 31 7e 31 63 31 51 31 5d 31 4e 31 57 31 ce 7e 5d 80 16 7f 36 80 00 00 a1 
ff 3c 31 51 31 41 31 47 31 44 31 63 31 88 31 a0 31 9a 31 91 31 75 31 78 31 85 31 c3 2b 97 31 7e 31 57 31 63 31 7b 31 7b 31 69 31 60 31 5d 31 5a 31 63 31 ce 7e 62 80 16 7f 31 80 00 00 35 
ff 3c 31 47 31 4b 31 47 31 4b 31 66 31 78 31 a0 31 a3 31 8b 31 85 31 75 31 8b 31 b9 2b 9a 31 81 31 4e 31 6c 31 6f 31 75 31 78 31 5a 31 63 31 60 31 5a 31 ce 7e 5d 80 21 7f 20 80 00 00 88 
ff 3c 31 41 31 44 31 38 31 4e 31 63 31 75 31 a9 31 97 31 85 31 7e 31 69 31 94 31 a1 2b 9a 31 75 31 51 31 69 31 60 31 81 31 69 31 57 31 63 31 51 31 5d 31 ce 7e 5d 80 27 7f 2b 80 00 00 12 
ff 3c 31 66 31 47 31 47 31 57 31 60 31 88 31 af 31 97 31 97 31 7e 31 75 31 9a 31 d8 2b 9a 31 7e 31 5d 31 66 31 78 31 81 31 6c 31 63 31 60 31 60 31 69 31 ce 7e 5d 80 21 7f 36 80 00 00 ed 
ff 3c 31 63 31 4b 31 54 31 57 31 66 31 8e 31 a3 31 9d 31 9a 31 7e 31 81 31 9a 31 de 2b a0 31 8b 31 54 31 75 31 78 31 78 31 81 31 63 31 6c 31 69 31 63 31 ce 7e 5d 80 16 7f 31 80 00 00 f0 
ff 3c 31 66 31 60 31 60 31 66 31 7b 31 9d 31 b8 31 b8 31 a6 31 91 31 88 31 a9 31 15 2c a3 31 91 31 69 31 7b 31 78 31 91 31 85 31 6f 31 78 31 6f 31 78 31 d4 7e 5d 80 21 7f 2b 80 00 00 3b 
ff 3c 31 66 31 60 31 60 31 66 31 78 31 9d 31 b8 31 b8 31 a6 31 91 31 88 31 a9 31 12 2c a3 31 91 31 69 31 7b 31 78 31 91 31 85 31 6f 31 75 31 6f 31 78 31 d4 7e 5d 80 21 7f 2b 80 00 00 32 
ff 3c 31 69 31 63 31 66 31 69 31 7e 31 a0 31 bb 31 b8 31 a9 31 91 31 8b 31 ac 31 24 2c a6 31 94 31 6f 31 7e 31 7b 31 94 31 88 31 72 31 7b 31 72 31 7b 31 d4 7e 5d 80 21 7f 2b 80 00 00 35 
ff 3c 31 6c 31 63 31 66 31 69 31 7e 31 a0 31 bb 31 bb 31 a9 31 94 31 8b 31 ac 31 27 2c a6 31 94 31 6f 31 7e 31 7b 31 97 31 88 31 75 31 7b 31 72 31 7e 31 d4 7e 5d 80 21 7f 2b 80 00 00 34 
ff 3c 31 6c 31 63 31 66 31 69 31 7e 31 a3 31 bb 31 bb 31 a9 31 94 31 8e 31 ac 31 2a 2c a6 31 94 31 6f 31 7e 31 7b 31 97 31 88 31 75 31 7b 31 75 31 7e 31 d4 7e 5d 80 21 7f 2b 80 00 00 38 
ff 3c 31 6c 31 63 31 66 31 6c 31 7e 31 a3 31 be 31 bb 31 a9 31 94 31 8e 31 ac 31 2d 2c a9 31 97 31 6f 31 f1 
ff 3c 31 26 32 02 32 14 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 48 32 23 32 5d 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 1a 32 4e 7e b7 7f d4 7e 86 7e 00 00 89 
ff 3c 31 26 32 02 32 14 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 45 32 23 32 5d 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 17 32 59 7e bd 7f d9 7e 8b 7e 00 00 94 
ff 3c 31 26 32 02 32 14 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 48 32 23 32 5d 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 1a 32 59 7e c8 7f df 7e 96 7e 00 00 fa 
ff 3c 31 26 32 02 32 0e 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 48 32 23 32 5a 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 17 32 5f 7e c8 7f e4 7e 9c 7e 00 00 dd 
ff 3c 31 26 32 02 32 14 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 45 32 23 32 5d 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 1a 32 64 7e ce 7f e4 7e a2 7e 00 00 c3 
ff 3c 31 26 32 02 32 11 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 45 32 23 32 5a 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 1a 32 64 7e ce 7f ea 7e a7 7e 00 00 ca 
ff 3c 31 26 32 05 32 17 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 45 32 23 32 5d 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 1a 32 6a 7e d3 7f ea 7e b2 7e 00 00 ca 
ff 3c 31 26 32 05 32 17 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 48 32 23 32 5d 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 17 32 6a 7e d3 7f ef 7e b2 7e 00 00 cf 
ff 3c 31 26 32 05 32 17 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 45 32 23 32 5d 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 32 32 26 32 17 32 1d 32 11 32 1a 32 70 7e d9 7f ef 7e b8 7e 00 00 c8 
ff 3c 31 26 32 05 32 14 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 45 32 23 32 5d 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 1a 32 70 7e d9 7f ef 7e bd 7e 00 00 d3 
ff 3c 31 26 32 02 32 14 32 29 32 3c 32 57 32 6f 32 6f 32 60 32 45 32 23 32 5d 32 1b 2d 3c 32 2c 32 11 32 1a 32 1d 32 2f 32 26 32 17 32 1d 32 11 32 1a 32 70 7e de 7f f5 7e c3 7e 00 f8 
ff 3c 31 45 32 3f 32 42 32 45 32 54 32 6f 32 88 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 48 32 29 32 32 32 36 32 4b 32 42 32 2f 32 39 32 2f 32 32 32 ca 7d 16 7f 5f 7e c4 7d 00 00 23 
ff 3c 31 45 32 3f 32 42 32 45 32 54 32 6f 32 85 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 48 32 29 32 32 32 39 32 4b 32 42 32 2f 32 39 32 2f 32 32 32 d5 7d 21 7f 6a 7e ca 7d 00 00 32 
ff 3c 31 45 32 3f 32 42 32 45 32 54 32 6f 32 88 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 48 32 29 32 32 32 39 32 4b 32 42 32 32 32 39 32 2f 32 32 32 da 7d 27 7f 6a 7e d5 7d 00 00 34 
ff 3c 31 45 32 3f 32 42 32 45 32 54 32 6f 32 85 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 45 32 29 32 32 32 39 32 4b 32 42 32 2f 32 39 32 2f 32 32 32 da 7d 2c 7f 70 7e da 7d 00 00 37 
ff 3c 31 45 32 3c 32 42 32 45 32 54 32 6f 32 85 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 48 32 29 32 32 32 39 32 4b 32 42 32 2f 32 39 32 2f 32 32 32 e0 7d 2c 7f 75 7e e0 7d 00 00 3c 
ff 3c 31 45 32 3f 32 42 32 45 32 54 32 6f 32 85 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 48 32 29 32 32 32 36 32 4b 32 42 32 32 32 39 32 2f 32 32 32 e0 7d 32 7f 75 7e e5 7d 00 00 36 
ff 3c 31 45 32 3f 32 42 32 45 32 54 32 6f 32 85 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 48 32 29 32 32 32 36 32 4b 32 42 32 2f 32 39 32 2f 32 32 32 e5 7d 32 7f 7b 7e eb 7d 00 00 2e 
ff 3c 31 45 32 3f 32 42 32 45 32 54 32 6f 32 85 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 45 32 29 32 32 32 39 32 4b 32 42 32 32 32 39 32 2f 32 32 32 eb 7d 38 7f 7b 7e f0 7d 00 00 2e 
ff 3c 31 45 32 3f 32 42 32 45 32 54 32 6f 32 85 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 48 32 29 32 32 32 39 32 4b 32 42 32 2f 32 39 32 2f 32 32 32 eb 7d 38 7f 80 7e f6 7d 00 00 c3 
ff 3c 31 45 32 3f 32 42 32 45 32 54 32 6f 32 88 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 45 32 29 32 32 32 39 32 4b 32 42 32 2f 32 39 32 2f 32 32 32 eb 7d 38 7f 80 7e fb 7d 00 00 ce 
ff 3c 31 45 32 3c 32 42 32 45 32 54 32 6f 32 85 32 88 32 79 32 63 32 5a 32 73 32 31 2d 54 32 45 32 29 32 32 32 39 32 4b 32 42 32 2f 32 39 32 2f 32 32 32 eb 7d 3d 7f 80 7e 01 7e 00 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 63 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 46 7d 9c 7e f6 7d e8 7c 00 00 6a 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 4b 7d a7 7e 01 7e f3 7c 00 00 b0 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 73 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 51 7d ad 7e 01 7e f9 7c 00 00 b6 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 51 7d ad 7e 06 7e 04 7d 00 00 51 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 56 7d b2 7e 0c 7e 09 7d 00 00 4e 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 5c 7d b8 7e 0c 7e 14 7d 00 00 53 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 5c 7d bd 7e 11 7e 1a 7d 00 00 45 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 5c 7d bd 7e 11 7e 1f 7d 00 00 40 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 61 7d bd 7e 17 7e 25 7d 00 00 41 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 61 7d bd 7e 17 7e 25 7d 00 00 41 
ff 3c 31 51 32 4b 32 4e 32 51 32 60 32 7c 32 91 32 94 32 85 32 6f 32 66 32 7f 32 3d 2d 60 32 51 32 39 32 45 32 42 32 57 32 4e 32 3f 32 45 32 3c 32 3f 32 67 7d c3 7e 17 ff 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 88 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 48 32 4e 32 42 32 48 32 5f 7c b9 7d 3b 7d 71 7b 00 00 3b 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 88 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 48 32 4e 32 42 32 48 32 6a 7c bf 7d 40 7d 76 7b 00 00 74 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 88 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 48 32 4e 32 42 32 48 32 6f 7c c4 7d 46 7d 82 7b 00 00 f8 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 88 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 48 32 4e 32 42 32 48 32 75 7c ca 7d 4b 7d 87 7b 00 00 e4 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 88 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 5d 32 54 32 48 32 4e 32 42 32 48 32 75 7c ca 7d 51 7d 8d 7b 00 00 c9 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 88 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 48 32 4e 32 42 32 48 32 75 7c cf 7d 51 7d 92 7b 00 00 ee 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 88 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 45 32 4e 32 42 32 48 32 7a 7c cf 7d 56 7d 98 7b 00 00 e1 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 88 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 48 32 4e 32 42 32 48 32 80 7c d5 7d 56 7d 9d 7b 00 00 09 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 85 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 48 32 4e 32 42 32 48 32 80 7c d5 7d 56 7d a3 7b 00 00 3a 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 85 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 48 32 4e 32 42 32 48 32 80 7c d5 7d 5c 7d a3 7b 00 00 30 
ff 3c 31 5a 32 54 32 57 32 5a 32 69 32 82 32 97 32 9a 32 8e 32 79 32 6f 32 88 32 43 2d 69 32 5a 32 3f 32 4b 32 4b 32 60 32 54 32 48 32 4e fa 
ff 3c 31 5d 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 91 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 44 7b c2 7c 3e 7c a9 7a 00 00 e4 
ff 3c 31 5d 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 91 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 4a 7b c7 7c 43 7c b4 7a 00 00 8f 
ff 3c 31 5d 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 91 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 50 7b cd 7c 49 7c bf 7a 00 00 9e 
ff 3c 31 5d 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 94 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 55 7b cd 7c 4e 7c c5 7a 00 00 e3 
ff 3c 31 5d 32 57 32 5d 32 5d 32 6c 32 88 32 9d 32 a0 32 91 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 55 7b d2 7c 54 7c d0 7a 00 00 cb 
ff 3c 31 5d 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 91 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 5b 7b d8 7c 54 7c d5 7a 00 00 f7 
ff 3c 31 5d 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 94 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 5b 7b d8 7c 54 7c db 7a 00 00 fc 
ff 3c 31 5d 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 91 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 60 7b d8 7c 59 7c e0 7a 00 00 f4 
ff 3c 31 5d 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 91 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 60 7b dd 7c 59 7c e6 7a 00 00 f7 
ff 3c 31 5d 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 91 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 32 54 32 4b 32 4e 32 60 7b dd 7c 59 7c ec 7a 00 00 fd 
ff 3c 31 60 32 57 32 5d 32 60 32 6c 32 88 32 9d 32 a0 32 91 32 7f 32 73 32 8b 32 49 2d 6c 32 5d 32 45 32 51 32 51 32 63 32 5a 32 4b 
