import sys, os, socket, telnetlib, time, subprocess
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import MythTV

Addon = xbmcaddon.Addon(id="mythtv.powersave")



class Main:
	_base = sys.argv[0]
	_enum_forerun = [1,2,5,10,15,20]
	_enum_overrun = [1,2,5,10,15,20]
	_enum_idle= [5,10,15,20,25,30,40,50,60,90,120,180,240,300,360,420,480,540,600]
	_sleep_interval = 10000
	_poll_interval = 6
	_timers = {}
	_nextWakeup = 0
	_lastWakeup = 0
	_idleTime = 0
	_lastIdleTime = 0
	_realIdleTime = 0
	_isLoggedOn = False
	_lastPlaying = False
	_isPlaying = False
	_lastRecording = False
	_isRecording = False
	_MythBackend = False
	_mythShutdownStatus = -2

	# main routine
	def __init__(self):
		print "mythtv.powersave: Plugin started"
		self.getSettings()
		# self.getTimers()
		pollCounter = self._poll_interval
		# main loop
		while (not xbmc.abortRequested):
			# try to connect to backend
			# print("mythtv.powersave: %s" % self._MythBackend)
			if (self._MythBackend == False):
				print "mythtv.powersave: Mythbackend not connected - pause/retry"
				try:
					self._MythBackend = MythTV.MythBE()
				except:
					xbmc.sleep(self._sleep_interval)
					continue
				print "mythtv.powersave: Mythbackend connected!"
				self.getTimers()
					
			# reload timers periodically
			if (pollCounter > self._poll_interval):
				pollCounter = 0
				self.getTimers()
			else:
				pollCounter = pollCounter + 1
				
			# set wakeup
			self.setWakeup()
			
			# time warp calculations demands to have our own idle timers
			self._lastIdleTime = self._idleTime
			self._idleTime = xbmc.getGlobalIdleTime()
			if (self._idleTime > self._lastIdleTime):
				self._realIdleTime = self._realIdleTime + (self._idleTime - self._lastIdleTime)
			else:
				self._realIdleTime = self._idleTime

			# notice changes in playback
			self._lastPlaying = self._isPlaying
			self._isPlaying = xbmc.Player().isPlaying()
			
			# now this one is tricky: a playback ended, idle would suggest to powersave, but we set the clock back for overrun. 
			# Otherwise xbmc could sleep instantly at the end of a movie
			if (self._lastPlaying  == True) & (self._isPlaying == False) & (self._realIdleTime >= self.settings['vdrps_sleepmode_after']):
				self._realIdleTime = self.settings['vdrps_sleepmode_after'] - self.settings['vdrps_overrun']
				#print "mythtv.powersave: playback stopped!"

			# notice changes in recording
			self._lastRecording = self._isRecording
			self._isRecording = self.getIsRecording()

			# same trick, for recording issues - gives time to postprocess
			if (self._lastRecording  == True) & (self._isRecording == False) & (self._realIdleTime >= self.settings['vdrps_sleepmode_after']):
				self._realIdleTime = self.settings['vdrps_sleepmode_after'] - self.settings['vdrps_overrun']

			
			
			print "mythtv.powersave: Mark"
			print self._isRecording

			# powersave checks ...
			if (self.settings['vdrps_sleepmode'] > 0) & \
			   (self._realIdleTime >= self.settings['vdrps_sleepmode_after']):
				# sleeping time already?
				if (self._isPlaying):
					print "mythtv.powersave: powersave postponed - xbmc is playing ..."
				elif (self._isRecording):
					print "mythtv.powersave: powersave postponed - vdr is recording ..."
				elif (self.getIsRecordPending()):
					print "mythtv.powersave: powersave postponed - record upcomming ..."
				else:
					if (self.settings['vdrps_sleepmode'] == 1):
						#print "mythtv.powersave: initiating sleepmode S3 ..."
						xbmc.executebuiltin('Suspend')
					elif (self.settings['vdrps_sleepmode'] == 2):
						#print "mythtv.powersave: initiating sleepmode S4 ..."
						xbmc.executebuiltin('Hibernate')
					elif (self.settings['vdrps_sleepmode'] == 3):
						#print "mythtv.powersave: initiating powerdown ..."
						xbmc.executebuiltin('Powerdown')
			
			
			# Disabled due to bugged service abort on logouts
			# are we logged on? (Dialog <> 10029)			
			#self._isLoggedOn = (xbmcgui.getCurrentWindowId()<>10029)
			# check for automatic logout ...
			#if (self.settings['vdrps_autologout'] == "true") & \
			   #(self._idleTime > self.settings['vdrps_autologout_after']) & \
			   #self._isLoggedOn:
				## logging out is safe
				#xbmc.executebuiltin('System.LogOff')
			
			
			# sleep a little ...
			xbmc.sleep(self._sleep_interval)
		# last second check
		self.getTimers()
		# last second alarm clock
		self.setWakeup()
		print "mythtv.powersave: Plugin exited"
		
	# get settings from xbmc
	def getSettings(self):
		print "mythtv.powersave: Getting settings ..."
		self.settings = {}
		self.settings['vdrps_host'] = Addon.getSetting('vdrps_host')
		self.settings['vdrps_port'] = int(Addon.getSetting('vdrps_port'))
		self.settings['vdrps_forerun'] = self._enum_forerun[int(Addon.getSetting('vdrps_forerun'))] * 60
		self.settings['vdrps_wakecmd'] = Addon.getSetting('vdrps_wakecmd')
		self.settings['vdrps_overrun'] = self._enum_forerun[int(Addon.getSetting('vdrps_overrun'))] * 60
		# Disabled due to bugged service abort on logouts
		#self.settings['vdrps_autologout'] = Addon.getSetting('vdrps_autologout')
		#self.settings['vdrps_autologout_after'] = self._enum_idle[int(Addon.getSetting('vdrps_autologout_after'))] * 60
		self.settings['vdrps_sleepmode'] = int(Addon.getSetting('vdrps_sleepmode'))
		self.settings['vdrps_sleepmode_after'] = self._enum_idle[int(Addon.getSetting('vdrps_sleepmode_after'))] * 60
		self.settings['vdrps_dailywakeup'] = Addon.getSetting('vdrps_dailywakeup')
		self.settings['vdrps_dailywakeup_time'] = int(Addon.getSetting('vdrps_dailywakeup_time')) * 1800

	# get timers from vdr
	def getTimers(self):
		print "mythtv.powersave: Getting timers ..."
		# contact SVDRP and parse resopnse
		# raw = self._querySVDRP(self.settings['vdrps_host'], self.settings['vdrps_port'])
		# # parse when get a response
		# if (raw != None):
		# 	self._parseSVDRP(raw)
		self._nextWakeUp = self.getNextWake()
		print "mythtv.powersave: Got timer"

		
		# self._mythShutdownStatus = os.system("checkshutdown --syslog")
		# self._mythShutdownStatus = os.system("mythshutdown -v --status --logpath=/home/tom/Desktop")
		mythStatus=subprocess.Popen("mythshutdownstatus", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
		self._mythShutdownStatus=int(mythStatus.stdout.read())

		print("mythtv.powersave: Mythshutdown status: %d" % self._mythShutdownStatus)


	# set the alarm clock if necessary
	def setWakeup(self):
		print "mythtv.powersave: Setting wake time..."
		# calculate next wakeup time
		stampWakeup = self.getMostRecentTimer() - self.settings['vdrps_forerun']

		stampNow = int(time.time())

		# some extra calculations for daily wakeing
		if (self.settings['vdrps_dailywakeup'] == "true"):
			# extract date and time only
			tupleNow = time.localtime(stampNow)
			stampTimeOnly = (tupleNow.tm_hour*3600)+(tupleNow.tm_min*60)+tupleNow.tm_sec
			stampDateOnly = time.mktime((tupleNow.tm_year,tupleNow.tm_mon,tupleNow.tm_mday,0,0,0,tupleNow.tm_wday,tupleNow.tm_yday,tupleNow.tm_isdst))

			# wake me today, or tomorrow?
			if (self.settings['vdrps_dailywakeup_time'] > stampTimeOnly):
				stampDailyWakeup = stampDateOnly + self.settings['vdrps_dailywakeup_time']
			else:
				# add a whole day
				stampDailyWakeup = stampDateOnly + self.settings['vdrps_dailywakeup_time'] + 86400


				
			# daily wakeup is before next timer, so set the alarm clock to it
			if (stampDailyWakeup<stampWakeup) | (stampWakeup < 300000):
				stampFinalWakeup = stampDailyWakeup
			else:
				stampFinalWakeup = stampWakeup
		else:
			stampFinalWakeup = stampWakeup
		
		# is it in the future and not already set?
		print("mythtv.powersave: next recording: %d" % stampWakeup)
		print("mythtv.powersave: next scheduled wake: %d" % stampDailyWakeup)
		print("mythtv.powersave: final wake time: %d" % stampFinalWakeup)
		print("mythtv.powersave: time now: %d" % stampNow)
		print("mythtv.powersave: last wake: %d" % self._lastWakeup)
		if (stampFinalWakeup>stampNow) & (stampFinalWakeup <> self._lastWakeup):
			# yes we do have to wakeup
			print "mythtv.powersave: Wake up on timestamp %d (%s)" % (stampFinalWakeup, time.asctime(time.localtime(stampFinalWakeup)) )
			# call the alarm script
			os.system("%s %d" % (self.settings['vdrps_wakecmd'],stampFinalWakeup))
			# remember the stamp, not to call alarm script twice with the same value
			self._lastWakeup = stampFinalWakeup
		else:
			print "mythtv.powersave: no wake required"
			
	# contact SVDRP service and get raw timers
	# def _querySVDRP(self, host, port):
	# 	try:
	# 		tndata = None
	# 		# getting in contact
	# 		tnsession = telnetlib.Telnet(host,port,5)
	# 		try:
	# 			# sending commands
	# 			tnsession.write("LSTT\n")
	# 			tnsession.write("QUIT\n")
	# 			# getting data
	# 			tndata = tnsession.read_until("closing connection")
	# 		finally:
	# 			# clean up our mess, and get back
	# 			tnsession.close()
	# 			return tndata

	# 	except:
	# 		# made a boo boo
	# 		print "mythtv.powersave: cannot get list of timers from %s:%s " % (host, port)
	# 		return None
			
	# # this function parses the SVDRP session dump for timers and returns a dictonary with status
	# def _parseSVDRP(self, raw):
	# 	# empty result list
	# 	timers = {}
	# 	# loop thru lines
	# 	for line in raw.splitlines():
	# 		# as we know timers getting returned with status 250 (ok) 
	# 		if line.startswith("250"):
	# 			try:
	# 				# get into the fields
	# 				fields = line[4:].split(":")
	# 				# check the timer status (flags 1: enabled, 2, instant record, 4, vps, 8: active)
	# 				timer_status = fields[0].split(" ")[1]
	# 				# decode starting time
	# 				timer_start = int(time.mktime(time.strptime(fields[2]+fields[3], "%Y-%m-%d%H%M")))
	# 				# fill the timer dictonary
	# 				if timer_start>0:
	# 					timers[timer_start] = int(timer_status)
	# 			except: 
	# 				# some lines may fail
	# 				print "mythtv.powersave: unable to parse line '%s' " % (line)
	# 	self._timers = timers

	def getNextWake(self):
		progs = self._MythBackend.getUpcomingRecordings()
		try:
			rectime = progs.next().recstartts
			print("mythtv.powersave: got record time: %s" % rectime)
			return int(rectime.strftime("%s"))
		except:
			return 0

	# returns if any timer is actually recording
	def getIsRecording(self):
		# for status in self._timers.values():
		# 	if (status & 8) == 8:
		# 		return True
		# return False
		
		# query checkshutdown
		return (self._mythShutdownStatus != 0)
	
	# returns if a record is upcomming within forerun, or idle time to prevent powersave 
	def getIsRecordPending(self):
		# decide which period lasts longer
		# if (self.settings['vdrps_forerun'] > self.settings['vdrps_sleepmode_after']):
		# 	delta = self.settings['vdrps_forerun']
		# else:
		# 	# odd people may set the recording prerun smaller than idle time
		# 	delta = self.settings['vdrps_sleepmode_after']
		# # we need the stamps
		# stamps = self._timers.keys()
		# stampNow = int(time.time())
		# for stamp in stamps:
		# 	if (self._timers[stamp] & 1 == 1) & (stamp-delta < stampNow ):
		# 		# there is a record upcomming
		# 		return True
		return False

	# this returns the most recent enabled timestamp, or None
	def getMostRecentTimer(self):
		# # we need a sorted list of the timestamps
		# stamps = self._timers.keys()
		# stamps.sort()
		# # now search for the first enabled one
		# for stamp in stamps:
		# 	if self._timers[stamp] & 1 == 1:
		# 		return int(stamp)
		# return 0;
		return self._nextWakeUp
