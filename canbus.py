#!/usr/bin/env python3
# vim: sw=2 tw=2 et
import socket
import struct
import time

last1Hz = 0.0
canformat = '<IB3x8s' # from https://python-can.readthedocs.io/en/1.5.2/_modules/can/interfaces/socketcan_native.html
targetVoltage = 0.0
targetCurrent = 0.0

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
    try:
      raw_bytes = self.canSocket.recv(16)
      if raw_bytes != None: # if a CAN message was waiting
        print('v',end='')
        rawID,DLC,candata = struct.unpack(canformat,raw_bytes)
        canID = rawID & 0x1FFFFFFF
        if canID == 0x18FF50E5:
          voltage = candata[1] + (candata[0] * 256)
          current = candata[3] + (candata[2] * 256)
          status  = candata[4] & 0x1F
          status_text = "Hardware failure" if (status & 1) else ""
          status_text = status_text + ", too hot"            if (status & 2) else status_text
          status_text = status_text + ", Wrong input voltage at AC plug" if (status & 4) else status_text
          status_text = status_text + ", No battery detected"      if (status & 8) else status_text
          print("voltage: {}	current: {}	Errors: ".format(voltage, current)+status_text)
    except:
      pass

  def sendMessages(self):
    global last1Hz
    timenow = time.time() # only call time.time() once to save time

    if timenow - last1Hz > 1.0: # these CAN messages go out one time per second
      last1Hz  = timenow
      print("s",end='')

      rawID = 0x1806E5F4 | CAN_EFF_FLAG # B cansend can1 1806E5F4#0DC8003200000000
      candatalist = [0,0,0,0,0,0,0,0] # init list
      candatalist[0] = int((targetVoltage * 10) / 256)
      candatalist[1] = int((targetVoltage * 10))
      candatalist[2] = int((targetCurrent * 10) / 256)
      candatalist[3] = int((targetCurrent * 10))

      candata = bytes(candatalist) # turn into bytes to be sent
      self.canSocket.send(struct.pack(canformat, rawID, 8, candata))

  def run(self):
    while True:
      self.receiveMessages()
      self.sendMessages()
      time.sleep(0.1)

if __name__ == '__main__':
  can_bus = CanBus(can_device='can1')
  can_bus.run()
