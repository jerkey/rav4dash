#!/usr/bin/env python3
# vim: sw=2 ts=2 et
import socket
import struct
import time
import requests

last1Hz = 0.0
canformat = '<IB3x8s' # from https://python-can.readthedocs.io/en/1.5.2/_modules/can/interfaces/socketcan_native.html
targetVoltage = 0.0
targetCurrent = 0.0
status = 255
status_text = "unknown"
seenVoltage = 0
seenCurrent = 0
lastSeen1806E5F4 = 0
lastIgnitionFalse = 0

#From https://github.com/torvalds/linux/blob/master/include/uapi/linux/can.h
CAN_EFF_FLAG = 0x80000000 #EFF/SFF is set in the MSB
CAN_ERR_MASK = 0x1FFFFFFF # /* omit EFF, RTR, ERR flags */

class CanBus():
  def __init__(self, can_device):
    self.canSocket = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    can_id = 0
    can_mask = 0
    can_filter = struct.pack('LL',can_id,can_mask)

    self.canSocket.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FILTER, can_filter)
    ret_val = self.canSocket.getsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FILTER)
    print("Socket Option for CAN_RAW_FILTER is set to {}".format(ret_val))

    can_error_filter = struct.pack('L',CAN_ERR_MASK) # Set the system to receive every possible error

    self.canSocket.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_ERR_FILTER, can_error_filter)
    ret_val = self.canSocket.getsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_ERR_FILTER)
    print("Socket Option for CAN_RAW_ERR_FILTER is set to {}".format(ret_val))

    self.can_device = can_device
    try:
      self.canSocket.bind((can_device,))
    except OSError:
      print("Could not bind to can_device: "+can_device)
    # https://stackoverflow.com/questions/34371096/how-to-use-python-socket-settimeout-properly
    self.canSocket.settimeout(1)

  def receiveMessages(self):
    global status, status_text, seenVoltage, seenCurrent, lastSeen1806E5F4
    try:
      raw_bytes = self.canSocket.recv(16)
      if raw_bytes != None: # if a CAN message was waiting
        print('v',end='')
        rawID,DLC,candata = struct.unpack(canformat,raw_bytes)
        canID = rawID & 0x1FFFFFFF
        if canID == 0x18FF50E5:
          lastSeen1806E5F4 = time.time()
          seenVoltage = (candata[1] + (candata[0] * 256)) / 10.0
          seenCurrent = (candata[3] + (candata[2] * 256)) / 10.0
          status  = candata[4] & 0x1F
          status_text = "Hardware failure" if (status & 1) else ""
          status_text = status_text + ", too hot"            if (status & 2) else status_text
          status_text = status_text + ", Wrong input voltage at AC plug" if (status & 4) else status_text
          status_text = status_text + ", No battery detected"      if (status & 8) else status_text
          status_text = status_text + ", CAN error?"      if (status & 16) else status_text
          if status > 0:
            push_url = 'http://192.168.123.1/charger_push'
            params = {'voltage' : seenVoltage, 'current' : seenCurrent, 'status' : status_text }
            push_response = requests.get(push_url, params=params)
    except:
      print("e",end="")

  def sendMessages(self):
    rawID = 0x1806E5F4 | CAN_EFF_FLAG # B cansend can1 1806E5F4#0DC8003200000000
    candatalist = [0,0,0,0,0,0,0,0] # init list
    candatalist[0] = int((targetVoltage * 10) / 256)
    candatalist[1] = int((targetVoltage * 10 % 256))
    candatalist[2] = int((targetCurrent * 10) / 256)
    candatalist[3] = int((targetCurrent * 10 % 256))
    #print("tv {}	TC {}".format(targetVoltage,targetCurrent),end='	')

    candata = bytes(candatalist) # turn into bytes to be sent
    self.canSocket.send(struct.pack(canformat, rawID, 8, candata))

  def run(self):
    global lastIgnitionFalse, targetVoltage, targetCurrent, last1Hz
    charge_desired = {'ignition' : False } # reinitialize
    while True:
      self.receiveMessages()

      if time.time() - last1Hz > 1.0: # one time per second
        last1Hz  = time.time()

        if time.time() - lastSeen1806E5F4 < 1.0:
          push_url = 'http://192.168.123.1/charger_push'
          params = {'voltage' : seenVoltage, 'current' : seenCurrent, 'status' : status_text }
          push_response = requests.get(push_url, params=params)

        charge_desired = {'ignition' : False } # reinitialize
        get_url = 'http://192.168.123.1/charger_get'
        get_data = requests.get(get_url)
        if get_data.status_code == 200:
          try:
            charge_desired.update(get_data.json())
            print(charge_desired)
          except:
            print('text response: '+get_data.text)
        else:
          print("get_data failed with status code: {}".format(get_data.status_code))

      if charge_desired['ignition']:
        try:
          targetVoltage = charge_desired['targetVoltage']
          targetCurrent = charge_desired['targetCurrent']
          if (time.time() - lastSeen1806E5F4 < 5):
            print("k",end='')
            self.sendMessages()
          if (time.time() - lastIgnitionFalse < 4):
            print("sending canbus because ignition turned on")
            self.sendMessages()
            time.sleep(1)
        except:
          pass
      else:
        lastIgnitionFalse = time.time()

      time.sleep(0.1)

if __name__ == '__main__':
  print('starting')
  can_bus = CanBus(can_device='can1')
  can_bus.run()
