from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import time
from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3

	# For loss rate
	receivedFrameCount = 0 # Overall, from start to finish
	currFrameNbr = 0 # Moved here from inside the RTP receiver

	# For bitrate and framerate. Resets every time playback is paused
	startTime=time.time_ns()
	tempFrameCount = 0
	byteCount = 0

	rtpThread = None
	rtspThread = None

	# Initialisation
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
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
		# Create Play button		
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=0, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Stop"
		self.teardown["command"] =  self.teardownConnection
		self.teardown.grid(row=1, column=2, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
	
	def setupMovie(self):
		"""Setup button handler."""
		self.connectToServer()
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)

	def teardownConnection(self):
		"""Teardown button handler, now no longer quits the client"""
		self.sendRtspRequest(self.TEARDOWN)

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.INIT:
			self.setupMovie()
			while (self.state != self.READY): pass # Wait until it is ready
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
										
					if self.currFrameNbr > self.frameNbr: # Only receive frames newer than current
						if self.frameNbr + 1 != self.currFrameNbr:
							print("Warning: Lost a packet")
						else:
							self.byteCount += rtpPacket.getPayloadSize()
							self.receivedFrameCount += 1
							self.tempFrameCount += 1
							self.frameNbr = self.currFrameNbr
							self.updateMovie(self.writeFrame(rtpPacket.getPayload()))

			except:
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.playEvent.isSet():
					break
					
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.rtspSocket.settimeout(0.5)
		try:
			
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkinter.messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)

	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		#-------------
		# TO COMPLETE
		#-------------
		
		# Setup request
		if requestCode == self.SETUP and self.state == self.INIT:
			print("Starting RTSP listener thread...")
			self.readyEvent = threading.Event()
			self.readyEvent.clear()
			self.rtspThread = threading.Thread(target=self.recvRtspReply)
			self.rtspThread.start()
			# Update RTSP sequence number.
			# ...

			self.rtspSeq = 1

			# Write the RTSP request to be sent.
			# request = ...

			request = ( "SETUP " + str(self.fileName) + " RTSP/1.0 " + "\n" + "CSeq: " + str(self.rtspSeq) + "\n" + "Transport: RTP/UDP; client_port= " + str(self.rtpPort))
			
			# Keep track of the sent request.
			# self.requestSent = ...

			self.requestSent = self.SETUP
		
		# Play request
		elif requestCode == self.PLAY and self.state == self.READY:
			# Update RTSP sequence number.
			# ...
			
			self.rtspSeq += 1

			# Write the RTSP request to be sent.
			# request = ...
			
			request = ("PLAY " + str(self.fileName) + " RTSP/1.0 " + "\n" + "CSeq: " + str(self.rtspSeq) + "\n" + "Session: " + str(self.sessionId))
			# Keep track of the sent request.
			# self.requestSent = ...

			self.requestSent = self.PLAY
		
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			# Update RTSP sequence number.
			# ...
			
			self.rtspSeq += 1

			# Write the RTSP request to be sent.
			# request = ...
			
			request = ( "PAUSE " + str(self.fileName) + " RTSP/1.0 " + "\n" + "CSeq: " + str(self.rtspSeq) + "\n" + "Session: " + str(self.sessionId))

			# Keep track of the sent request.
			# self.requestSent = ...

			self.requestSent = self.PAUSE
			
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			# Update RTSP sequence number.
			# ...
			
			self.rtspSeq += 1

			# Write the RTSP request to be sent.
			# request = ...
			
			request = ( "TEARDOWN " + str(self.fileName) + " RTSP/1.0" + "\n" + "CSeq: " + str(self.rtspSeq) + "\n" + "Session: " + str(self.sessionId))

			# Keep track of the sent request.
			# self.requestSent = ...

			self.requestSent = self.TEARDOWN

		else:
			return
		
		# Send the RTSP request using rtspSocket.
		# ...

		self.rtspSocket.send(request.encode())
		
		print('\nData sent:\n' + request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			try:
				reply = self.rtspSocket.recv(1024)
				if reply:
					self.parseRtspReply(reply.decode("utf-8"))
			except:
				if self.readyEvent.isSet():
					print("RTSP listener stopped")
					self.rtspSocket.shutdown(socket.SHUT_RDWR)
					self.rtspSocket.close()
					break
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		seqNum = int(lines[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP:
						#-------------
						# TO COMPLETE
						#-------------
						# Update RTSP state.
						# self.state = ...
						self.state = self.READY
						# Open RTP port.
						self.openRtpPort() 

					elif self.requestSent == self.PLAY:
						# self.state = ...
						self.state = self.PLAYING

					elif self.requestSent == self.PAUSE:
						# self.state = ...
						
						self.state = self.READY

						# The play thread exits. A new thread is created on resume.
						self.playEvent.set()

						# While paused, print out some stats
						currentTime = time.time_ns()
						print("Loss rate:", 1 - self.receivedFrameCount/self.currFrameNbr)
						print("Data rate:", self.byteCount / ((currentTime - self.startTime)/1000000000)/1000,"KBps")
						print("Frame rate:", self.tempFrameCount / ((currentTime - self.startTime)/1000000000), "FPS")

					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT
						os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
						self.sessionId = 0
						self.requestSent = -1
						self.frameNbr = 0
						# Reset connection
						self.playEvent.set() # Tell RTP thread to end
						if (self.rtpThread.is_alive()): # If it has not ended by now
							print("Waiting for RTP thread to stop...")
							self.rtpThread.join()
							print("RTP thread stopped")
						self.rtpSocket.close()

	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		#-------------
		# TO COMPLETE
		#-------------
		# Create a new datagram socket to receive RTP packets from the server
		# self.rtpSocket = ...

		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

		# Set the timeout value of the socket to 0.5sec
		# ...

		self.rtpSocket.settimeout(0.5)

		try:
			# Bind the socket to the address using the RTP port given by the client user
			# ...
			self.rtpSocket.bind(('',self.rtpPort))

		except:
			tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			if self.state != self.INIT:
				print("Tearing down connection before quitting...")
				self.teardownConnection() # Teardown is now a separate function
			self.readyEvent.set() # End RTSP listener
			if (self.rtspThread.is_alive()):
				print("Waiting for RTSP listener thread to stop...")
				self.rtspThread.join()
			self.master.destroy() # Close the gui window
		else: # When the user presses cancel, resume playing.
			self.playMovie()
