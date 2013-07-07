import sys, os, socket, telnetlib, time, subprocess
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import MythTV

Addon = xbmcaddon.Addon(id="mythtv.powersave")



class Main:
	_base = sys.argv[0]
	_enum_forerun = [1,2,5,10,15,20]
	_enum_overrun = [1,2,5,10,15,20]
	_enum_idle= [5,10,15,20,25,30,40,50,60,90,120,180,240,300,360,420,480,540,600]
	# reduce sleep time so we don't get caught with our pants down when xbmc tries to exit
	_sleep_interval = 2 * 1000
	# poll timers/shutdown status every 60 seconds
	_poll_interval = 60 * 1000 / _sleep_interval
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
		xbmc.log(msg="mythtv.powersave: Plugin started", level=xbmc.LOGNOTICE)
		self.getSettings()
		pollCounter = self._poll_interval

		# main loop
		while (not xbmc.abortRequested):
			# try to connect to backend
			if (self._MythBackend == False):
				xbmc.log(msg="mythtv.powersave: Mythbackend not connected - pause/retry", level=xbmc.LOGNOTICE)
				try:
					self._MythBackend = MythTV.MythBE()
				except:
					xbmc.sleep(self._sleep_interval)
					continue
				xbmc.log(msg="mythtv.powersave: Mythbackend connected!", level=xbmc.LOGNOTICE)
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
				#xbmc.log(msg="mythtv.powersave: playback stopped!", level=xbmc.LOGDEBUG)

			# notice changes in recording
			self._lastRecording = self._isRecording
			self._isRecording = self.getIsRecording()

			# same trick, for recording issues - gives time to postprocess
			if (self._lastRecording  == True) & (self._isRecording == False) & (self._realIdleTime >= self.settings['vdrps_sleepmode_after']):
				self._realIdleTime = self.settings['vdrps_sleepmode_after'] - self.settings['vdrps_overrun']

			xbmc.log(msg="mythtv.powersave: IsRecording: %s" % self._isRecording, level=xbmc.LOGDEBUG)

			# powersave checks ...
			if (self.settings['vdrps_sleepmode'] > 0) & \
			   (self._realIdleTime >= self.settings['vdrps_sleepmode_after']):
				# sleeping time already?
				if (self._isPlaying):
					xbmc.log(msg="mythtv.powersave: powersave postponed - xbmc is playing ...", level=xbmc.LOGDEBUG)
				elif (self._isRecording):
					xbmc.log(msg="mythtv.powersave: powersave postponed - mythtv is recording ...", level=xbmc.LOGDEBUG)
				else:
					if (self.settings['vdrps_sleepmode'] == 1):
						#xbmc.log(msg="mythtv.powersave: initiating sleepmode S3 ...", level=xbmc.LOGNOTICE)
						xbmc.executebuiltin('Suspend')
					elif (self.settings['vdrps_sleepmode'] == 2):
						#xbmc.log(msg="mythtv.powersave: initiating sleepmode S4 ...", level=xbmc.LOGNOTICE)
						xbmc.executebuiltin('Hibernate')
					elif (self.settings['vdrps_sleepmode'] == 3):
						#xbmc.log(msg="mythtv.powersave: initiating powerdown ...", level=xbmc.LOGNOTICE)
						xbmc.executebuiltin('Powerdown')
			
			# sleep a little ...
			xbmc.sleep(self._sleep_interval)
		# last second check
		self.getTimers()
		# last second alarm clock
		self.setWakeup()
		xbmc.log(msg="mythtv.powersave: Plugin exited", level=xbmc.LOGNOTICE)
		
	# get settings from xbmc
	def getSettings(self):
		xbmc.log(msg="mythtv.powersave: Getting settings ...", level=xbmc.LOGDEBUG)
		self.settings = {}
		self.settings['vdrps_host'] = Addon.getSetting('vdrps_host')
		self.settings['vdrps_port'] = int(Addon.getSetting('vdrps_port'))
		self.settings['vdrps_forerun'] = self._enum_forerun[int(Addon.getSetting('vdrps_forerun'))] * 60
		self.settings['vdrps_wakecmd'] = Addon.getSetting('vdrps_wakecmd')
		self.settings['vdrps_overrun'] = self._enum_forerun[int(Addon.getSetting('vdrps_overrun'))] * 60
		self.settings['vdrps_sleepmode'] = int(Addon.getSetting('vdrps_sleepmode'))
		self.settings['vdrps_sleepmode_after'] = self._enum_idle[int(Addon.getSetting('vdrps_sleepmode_after'))] * 60
		self.settings['vdrps_dailywakeup'] = Addon.getSetting('vdrps_dailywakeup')
		self.settings['vdrps_dailywakeup_time'] = int(Addon.getSetting('vdrps_dailywakeup_time')) * 1800

	# get timers from vdr
	def getTimers(self):
		xbmc.log(msg="mythtv.powersave: Getting timers ...", level=xbmc.LOGDEBUG)
		# if we have lost the connection to mythbackend, don't try to update the timers.  This should never happen
		# because self._MythBackend == False should get caught at the top of the loop.
		if (self._MythBackend != False):
			self._nextWakeUp = self.getNextWake()

		xbmc.log(msg="mythtv.powersave: Getting shutdown status", level=xbmc.LOGDEBUG)
		mythStatus=subprocess.Popen("mythshutdownstatus", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
		self._mythShutdownStatus=int(mythStatus.stdout.read())

		xbmc.log(msg="mythtv.powersave: Mythshutdown status: %d" % self._mythShutdownStatus, level=xbmc.LOGDEBUG)


	# set the alarm clock if necessary
	def setWakeup(self):
		xbmc.log(msg="mythtv.powersave: Setting wake time...", level=xbmc.LOGDEBUG)
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
			

			xbmc.log(msg="mythtv.powersave: next scheduled wake: %d" % stampDailyWakeup, level=xbmc.LOGDEBUG)
				
			# daily wakeup is before next timer, so set the alarm clock to it
			if (stampDailyWakeup<stampWakeup) | (stampWakeup < 300000):
				stampFinalWakeup = stampDailyWakeup
			else:
				stampFinalWakeup = stampWakeup
		else:
			stampFinalWakeup = stampWakeup
		
		# is it in the future and not already set?
		xbmc.log(msg="mythtv.powersave: next recording: %d" % stampWakeup, level=xbmc.LOGDEBUG)
		xbmc.log(msg="mythtv.powersave: final wake time: %d" % stampFinalWakeup, level=xbmc.LOGDEBUG)
		xbmc.log(msg="mythtv.powersave: time now: %d" % stampNow, level=xbmc.LOGDEBUG)
		xbmc.log(msg="mythtv.powersave: last wake: %d" % self._lastWakeup, level=xbmc.LOGDEBUG)
		if (stampFinalWakeup>stampNow) & (stampFinalWakeup <> self._lastWakeup):
			# yes we do have to wakeup
			xbmc.log(msg="mythtv.powersave: Setting wake up on timestamp %d (%s)" % (stampFinalWakeup, time.asctime(time.localtime(stampFinalWakeup))), level=xbmc.LOGNOTICE)
			# call the alarm script
			os.system("%s %d" % (self.settings['vdrps_wakecmd'],stampFinalWakeup))
			# remember the stamp, not to call alarm script twice with the same value
			self._lastWakeup = stampFinalWakeup
		else:
			xbmc.log(msg="mythtv.powersave: no wake required", level=xbmc.LOGDEBUG)
			
	def getNextWake(self):
		#check for exception connecting to backend
		try:
			progs = self._MythBackend.getUpcomingRecordings()
		except:
			self._MythBackend = False
			xbmc.log(msg="mythtv.powersave: Connection to mythbackend lost!!", level=xbmc.LOGERROR)
			# return previous recording - don't want to change wake timer
			return self._nextWakeUp

		#we need this try in case there are no recordings scheduled
		try:
			rectime = progs.next().recstartts
			xbmc.log(msg="mythtv.powersave: got record time: %s" % rectime, level=xbmc.LOGDEBUG)
			return int(rectime.strftime("%s"))
		except:
			return self._nextWakeUp

	# returns if any timer is actually recording
	def getIsRecording(self):
		return (self._mythShutdownStatus != 0)
	
	# this returns the most recent enabled timestamp, or None
	def getMostRecentTimer(self):
		return self._nextWakeUp
