import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from Client import Client

if __name__ == "__main__":
	try:
		serverAddr = sys.argv[1]
		serverPort = sys.argv[2]
		rtpPort = sys.argv[3]
		fileName = sys.argv[4]
		win = Client(serverAddr, serverPort, rtpPort, fileName)
		win.connect("destroy", Gtk.main_quit)
		win.show_all()
		Gtk.main()
	except:
		print("[Usage: ClientLauncher.py Server_name Server_port RTP_port Video_file]\n")
