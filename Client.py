import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf
from RtpPacket import RtpPacket

import socket, threading, sys, traceback, os
import time

class Client(Gtk.Window):
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    DESCRIBE = 2
    PAUSE = 3
    TEARDOWN = 4

    # For loss rate
    startFrame = 0
    receivedFrameCount = 0  # Overall, from start to finish
    currFrameNbr = 0  # Moved here from inside the RTP receiver

    # For seekable playback
    length = 1  # in frames

    # For bitrate and framerate. Resets every time playback is paused
    startTime = time.time_ns()
    tempFrameCount = 0
    byteCount = 0

    rtpThread = None
    rtspThread = None

    # Initialisation
    def __init__(self, serveraddr, serverport, rtpport, filename):
        Gtk.Window.__init__(self, title="RTSP/RTP Client")
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.frameNbr = 0

        self.setupMovie()

    def createWidgets(self):
        """Build GUI."""

        # Create grid layout
        self.grid = Gtk.Grid()
        self.add(self.grid)

        # Create an image to display the movie
        self.image = Gtk.Image()
        self.grid.attach(self.image, 0, 0, 4, 1)

        # Create Play button
        self.start = Gtk.Button(label="Play")
        self.start.connect("clicked", self.playMovie)
        self.grid.attach(self.start, 0, 2, 1, 1)

        # Create Describe button
        self.describe = Gtk.Button(label="Describe")
        self.describe.connect("clicked", self.describeStream)
        self.grid.attach(self.describe, 1, 2, 1, 1)

        # Create Pause button
        self.pause = Gtk.Button(label="Pause")
        self.pause.connect("clicked", self.pauseMovie)
        self.grid.attach(self.pause, 2, 2, 1, 1)

        # Create Teardown button
        self.stop = Gtk.Button(label="Stop")
        self.stop.connect("clicked", self.teardownConnection)
        self.grid.attach(self.stop, 3, 2, 1, 1)

        # Create a seekbar that has 255 fixed steps
        self.seekbar = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 255, 1)
        self.seekbar.connect("change_value", self.seek)
        self.grid.attach(self.seekbar, 0, 1, 4, 1)

        # Create a label to display the movie
        # self.label = Label(self.master, height=19)
        # self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5)

    def setupMovie(self):
        """Setup button handler."""
        self.connectToServer()
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def teardownConnection(self, button=None):
        """Teardown button handler, now no longer quits the client"""
        self.sendRtspRequest(self.TEARDOWN)

    def pauseMovie(self, button=None):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self, button=None):
        """Play button handler."""
        if self.state == self.INIT:
            self.setupMovie()
            while self.state != self.READY:
                pass  # Wait until it is ready
        if self.state == self.READY:
            # Create a new thread to listen for RTP packets
            self.rtpThread = threading.Thread(target=self.listenRtp)
            self.rtpThread.start()
            self.playEvent = threading.Event()
            self.playEvent.clear()
            self.sendRtspRequest(self.PLAY)
            self.startTime = time.time_ns()
            self.byteCount = 0
            self.tempFrameCount = 0
            self.receivedFrameCount = 0

    def describeStream(self, button=None):
        """Sends a DESCRIBE request to get information about the current stream."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.DESCRIBE)

    def listenRtp(self):
        """Listen for RTP packets."""
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)

                    self.currFrameNbr = rtpPacket.seqNum()
                    print("Current Seq Num: " + str(self.currFrameNbr))

                    if (
                        self.currFrameNbr > self.frameNbr
                    ):  # Only receive frames newer than current
                        if self.frameNbr + 1 != self.currFrameNbr:
                            print("Warning: Lost a packet")
                        else:
                            self.byteCount += rtpPacket.getPayloadSize()
                            self.receivedFrameCount += 1
                            self.tempFrameCount += 1
                            self.frameNbr = self.currFrameNbr
                            self.seekbar.set_value(255 * self.frameNbr / self.length)
                            self.updateMovie(rtpPacket.getPayload())

            except:
                # Stop listening upon requesting PAUSE or TEARDOWN
                if self.playEvent.isSet():
                    break

    def updateMovie(self, data):
        """Update the image file as video frame in the GUI."""
        l = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
        l.write(data)
        self.image.set_from_pixbuf(l.get_pixbuf())
        l.close()

        # print("Image: ", self.image.get_storage_type())

    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtspSocket.settimeout(0.5)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            errorDialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CANCEL,
                text="Failed to connect to the server.",
            )
            errorDialog.run()
            errorDialog.destroy()

    def seek(self, context, scroll, value):
        self.pauseMovie()
        while self.state != self.READY:
            pass
        self.frameNbr = int(round(self.length * int(value) / 255))
        self.sendRtspRequest(self.PLAY)

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        # Setup request
        if requestCode == self.SETUP and self.state == self.INIT:
            print("Starting RTSP listener thread...")
            self.readyEvent = threading.Event()
            self.readyEvent.clear()
            self.rtspThread = threading.Thread(target=self.recvRtspReply)
            self.rtspThread.start()
            self.rtspSeq = 1
            request = (
                "SETUP "
                + str(self.fileName)
                + " RTSP/1.0 "
                + "\n"
                + "CSeq: "
                + str(self.rtspSeq)
                + "\n"
                + "Transport: RTP/UDP; client_port= "
                + str(self.rtpPort)
            )
            self.requestSent = self.SETUP
        # Play request
        elif requestCode == self.PLAY and self.state != self.INIT:
            self.rtspSeq += 1
            request = (
                "PLAY "
                + str(self.fileName)
                + " RTSP/1.0 "
                + "\n"
                + "CSeq: "
                + str(self.rtspSeq)
                + "\n"
                + "Session: "
                + str(self.sessionId)
                + "\nFrame: "
                + str(self.frameNbr + 1)
            )
            self.requestSent = self.PLAY
            self.startFrame = self.frameNbr + 1

        elif requestCode == self.DESCRIBE and self.state != self.INIT:
            self.rtspSeq += 1
            # We use a reduced SDP protocol here
            request = (
                "DESCRIBE "
                + str(self.fileName)
                + " RTSP/1.0 "
                + "\n"
                + "CSeq: "
                + str(self.rtspSeq)
                + "\nAccept: application/sdp"
            )
            self.requestSent = self.DESCRIBE

        # Pause request
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq += 1
            request = (
                "PAUSE "
                + str(self.fileName)
                + " RTSP/1.0 "
                + "\n"
                + "CSeq: "
                + str(self.rtspSeq)
                + "\n"
                + "Session: "
                + str(self.sessionId)
            )
            self.requestSent = self.PAUSE

        # Teardown request
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            self.rtspSeq += 1
            request = (
                "TEARDOWN "
                + str(self.fileName)
                + " RTSP/1.0"
                + "\n"
                + "CSeq: "
                + str(self.rtspSeq)
                + "\n"
                + "Session: "
                + str(self.sessionId)
            )
            self.requestSent = self.TEARDOWN

        else:
            return

        self.rtspSocket.send(request.encode())

        print("\nData sent:\n" + request)

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            try:
                reply = self.rtspSocket.recv(4096)
                if reply:
                    self.parseRtspReply(reply.decode("utf-8"))
                else:
                    print(
                        "No connection to server. RTSP listener thread is stopping..."
                    )
                    break
            except:
                if self.readyEvent.isSet():
                    print("RTSP listener stopped")
                    self.rtspSocket.shutdown(socket.SHUT_RDWR)
                    self.rtspSocket.close()
                    break

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        lines = data.split("\n")
        seqNum = int(lines[1].split(" ")[1])
        # Process only if the server reply's sequence number is the same as the request's
        if seqNum == self.rtspSeq:
            session = int(lines[2].split(" ")[1])
            # New RTSP session ID
            if self.sessionId == 0:
                self.sessionId = session

            # Process only if the session ID is the same
            if self.sessionId == session:
                if int(lines[0].split(" ")[1]) == 200:
                    if self.requestSent == self.SETUP:
                        self.state = self.READY
                        # Open RTP port
                        self.openRtpPort()
                        # Update seekbar
                        self.length = int(lines[3].split(" ")[1])

                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING

                    elif self.requestSent == self.DESCRIBE:
                        sdpFileStr = "\n".join(lines[7:])
                        infoDialog = Gtk.MessageDialog(
                            transient_for=self,
                            flags=0,
                            message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.OK,
                            text=sdpFileStr,
                        )
                        infoDialog.run()
                        infoDialog.destroy()

                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        # The play thread exits. A new thread is created on resume.
                        self.playEvent.set()
                        # While paused, print out some stats
                        currentTime = time.time_ns()
                        print(
                            "Loss rate:",
                            1 - self.receivedFrameCount/(self.frameNbr - self.startFrame + 1),
                        )
                        print(
                            "Data rate:",
                            self.byteCount
                            / ((currentTime - self.startTime) / 1000000000)
                            / 1000,
                            "KBps",
                        )
                        print(
                            "Frame rate:",
                            self.tempFrameCount
                            / ((currentTime - self.startTime) / 1000000000),
                            "FPS",
                        )

                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        self.sessionId = 0
                        self.requestSent = -1
                        self.frameNbr = 0
                        # Reset connection
                        self.playEvent.set()  # Tell RTP thread to end
                        if self.rtpThread.is_alive():  # If it has not ended by now
                            print("Waiting for RTP thread to stop...")
                            self.rtpThread.join()
                            print("RTP thread stopped")
                        self.rtpSocket.close()

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Set the timeout value of the socket to 0.5sec
        self.rtpSocket.settimeout(0.5)
        try:
            self.rtpSocket.bind(("", self.rtpPort))

        except:
            errorDialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CANCEL,
                text="Unable to bind to port " + str(self.rtpPort),
            )
            errorDialog.run()
            errorDialog.destroy()

    # the old handler method is now an overriden version of the delete_event handler
    def do_delete_event(self, event):
        """Handler on explictly closing the GUI window."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Are you sure you want to exit?",
        )
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            if self.state != self.INIT:
                print("Tearing down connection before quitting...")
                self.teardownConnection()  # Teardown is now a separate function
            self.readyEvent.set()  # End RTSP listener
            if self.rtspThread.is_alive():
                print("Waiting for RTSP listener thread to stop...")
                self.rtspThread.join()
            return False
        else:
            return True
