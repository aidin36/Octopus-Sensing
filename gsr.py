import threading
from config import processing_unit
import csv
import struct, serial
import math


class GSRStreaming(processing_unit):
    def __init__(self, file_queue):
        super().__init__()
        self._file_queue = file_queue
        self._stream_data = []
        self._record = None
        self._serial = serial.Serial("/dev/rfcomm0", 115200)
        self._serial.flushInput()
        print("port opening, done.")
        # send the set sensors command
        self._serial.write(struct.pack('BBBB', 0x08 , 0x04, 0x01, 0x00))  #GSR and PPG
        self._wait_for_ack()
        print("sensor setting, done.")

        # Enable the internal expansion board power
        self._serial.write(struct.pack('BB', 0x5E, 0x01))
        self._wait_for_ack()
        print("enable internal expansion board power, done.")

        # send the set sampling rate command

        '''
        sampling_freq = 32768 / clock_wait = X Hz
        '''
        sampling_freq = 50
        clock_wait = math.ceil((2 << 14) / sampling_freq)

        self._serial.write(struct.pack('<BH', 0x05, clock_wait))
        self._wait_for_ack()

        # send start streaming command
        self._serial.write(struct.pack('B', 0x07))
        self._wait_for_ack()
        print("start command sending, done.")

        self._record = None

    def run(self):
        threading.Thread(target=self._stream_loop).start()
        #plt.figure()
        #ln, = plt.plot([])
        #plt.ion()
        #plt.show()
        #while True:
        #    plt.pause(1)
        #    ln.set_xdata(range(len(self.stream)))
        #    ln.set_ydata(self.stream)
        #    plt.draw()

        while True:
            command = self._file_queue.get()
            if command == "terminate":
                break
            elif command == "stop_record":
                self._record = False
                self._save_to_file()

            else:
                # Command is the file name
                self._file_path = "created_files/gsr/" + command + '.csv'
                print(self._file_path)
                self._stream_data = []
                self._record = True

        self._serial.close()

    def _stream_loop(self):
        # read incoming data
       ddata = bytes("", 'utf-8')
       numbytes = 0
       framesize = 8 # 1byte packet type + 3byte timestamp + 2 byte GSR + 2 byte PPG(Int A13)

       try:
          while True:
             while numbytes < framesize:
                ddata += self._serial.read(framesize)
                numbytes = len(ddata)

             data = ddata[0:framesize]
             ddata = ddata[framesize:]
             numbytes = len(ddata)

             # read basic packet information
             (packettype) = struct.unpack('B', data[0:1])
             (timestamp0, timestamp1, timestamp2) = struct.unpack('BBB', data[1:4])

             # read packet payload
             (PPG_raw, GSR_raw) = struct.unpack('HH', data[4:framesize])

             # get current GSR range resistor value
             Range = ((GSR_raw >> 14) & 0xff)  # upper two bits
             if(Range == 0):
                Rf = 40.2   # kohm
             elif(Range == 1):
                Rf = 287.0  # kohm
             elif(Range == 2):
                Rf = 1000.0 # kohm
             elif(Range == 3):
                Rf = 3300.0 # kohm

             # convert GSR to kohm value
             gsr_to_volts = (GSR_raw & 0x3fff) * (3.0/4095.0)
             GSR_ohm = Rf/( (gsr_to_volts /0.5) - 1.0)

             # convert PPG to milliVolt value
             PPG_mv = PPG_raw * (3000.0/4095.0)

             timestamp = timestamp0 + timestamp1*256 + timestamp2*65536
             if self._record:
                 self._stream_data.append([packettype[0], timestamp, GSR_ohm, PPG_mv])

             #print("0x%02x\t\t%5d,\t%4d,\t%4d" % (packettype[0], timestamp, GSR_ohm, PPG_mv))


       except KeyboardInterrupt:
          #send stop streaming command
          self._serial.write(struct.pack('B', 0x20))

          print("stop command sent, waiting for ACK_COMMAND")
          self._wait_for_ack()
          print("ACK_COMMAND received.")
          #close serial port
          self._serial.close()
          print("All done")


    def _wait_for_ack(self):
       ddata = ""
       ack = struct.pack('B', 0xff)
       while ddata != ack:
          ddata = self._serial.read(1)
          print(ddata)

    def _save_to_file(self):
        print("save gsr and ppg")
        print(len(self._stream_data))
        with open(self._file_path, 'w') as csv_file:
            writer = csv.writer(csv_file)
            for row in self._stream_data:
                writer.writerow(row)