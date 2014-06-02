import sys, os, socket, telnetlib, time
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import MythTV

from safePowerManager import SafePowerManager

Addon = xbmcaddon.Addon(id="mythtv.powersave")

class Main:
	_base = sys.argv[0]
	_enum_forerun = [1,2,5,10,15,20]
	_enum_overrun = [1,2,5,10,15,20]
	_enum_idle = [5,10,15,20,25,30,40,50,60,90,120,180,240,300,360,420,480,540,600]
	_enum_warn_time = [10,30,60,120,300,600]
	_enum_powerfunc = ['Suspend', 'Hibernate', 'Powerdown']
	# reduce sleep time so we don't get caught with our pants down when xbmc tries to exit
	_sleep_interval = 2 * 1000
	# poll timers/shutdown status every 60 seconds
	_poll_interval = 60 * 1000 / _sleep_interval
	_nextWakeup = 0
	_lastWakeup = 0
	_idleTime = 0
	_lastIdleTime = 0
	_realIdleTime = 0
	_lastPlaying = False
	_isPlaying = False
	_lastRecording = False
	_isRecording = False
	_MythDB = False
	_MythBackend = False
	_SafePowerManager = False

	# main routine
	def __init__(self):
		xbmc.log(msg="mythtv.powersave: Plugin started", level=xbmc.LOGNOTICE)
		self.getSettings()
		pollCounter = self._poll_interval
		self._SafePowerManager = SafePowerManager()

		# main loop
		while (not xbmc.abortRequested):
			# try to connect to backend
			if (self._MythBackend == False):
				xbmc.log(msg="mythtv.powersave: Mythbackend not connected - pause/retry", level=xbmc.LOGNOTICE)
				try:
					self._MythDB = MythTV.MythDB(DBHostName = self.settings['mythps_host'],
								     DBName = self.settings['mythps_dbname'],
								     DBUserName = self.settings['mythps_dbuser'],
								     DBPassword = self.settings['mythps_dbpass'])
					self._MythBackend = MythTV.MythBE(self.settings['mythps_host'], db=self._MythDB)
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
			if (self._lastPlaying  == True) & (self._isPlaying == False) & (self._realIdleTime >= self.settings['mythps_sleepmode_after']):
				self._realIdleTime = self.settings['mythps_sleepmode_after'] - self.settings['mythps_overrun']
				#xbmc.log(msg="mythtv.powersave: playback stopped!", level=xbmc.LOGDEBUG)

			# notice changes in recording
			self._lastRecording = self._isRecording
			self._isRecording = self.getIsRecording()

			# same trick, for recording issues - gives time to postprocess
			if (self._lastRecording  == True) & (self._isRecording == False) & (self._realIdleTime >= self.settings['mythps_sleepmode_after']):
				self._realIdleTime = self.settings['mythps_sleepmode_after'] - self.settings['mythps_overrun']

			xbmc.log(msg="mythtv.powersave: IsRecording: %s" % self._isRecording, level=xbmc.LOGDEBUG)
			xbmc.log(msg="mythtv.powersave: IdleTime: %d" % self._realIdleTime, level=xbmc.LOGDEBUG)

			# powersave checks ...
			if (self.settings['mythps_sleepmode'] > 0) & \
			   (self._realIdleTime >= self.settings['mythps_sleepmode_after']):
				# sleeping time already?
				if (self._isPlaying):
					xbmc.log(msg="mythtv.powersave: powersave postponed - xbmc is playing ...", level=xbmc.LOGDEBUG)
				elif (self._isRecording):
					xbmc.log(msg="mythtv.powersave: powersave postponed - mythtv is recording ...", level=xbmc.LOGDEBUG)
				else:
					self.doPowersave()
					
			
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
		self.settings['mythps_host'] = Addon.getSetting('mythps_host')
		self.settings['mythps_dbname'] = Addon.getSetting('mythps_dbname')
		self.settings['mythps_dbuser'] = Addon.getSetting('mythps_dbuser')
		self.settings['mythps_dbpass'] = Addon.getSetting('mythps_dbpass')
		self.settings['mythps_forerun'] = self._enum_forerun[int(Addon.getSetting('mythps_forerun'))] * 60
		self.settings['mythps_wakecmd'] = Addon.getSetting('mythps_wakecmd')
		self.settings['mythps_overrun'] = self._enum_overrun[int(Addon.getSetting('mythps_overrun'))] * 60
		self.settings['mythps_warn_time'] = self._enum_warn_time[int(Addon.getSetting('mythps_warn_time'))]
		self.settings['mythps_sleepmode'] = int(Addon.getSetting('mythps_sleepmode'))
		self.settings['mythps_sleepmode_after'] = self._enum_idle[int(Addon.getSetting('mythps_sleepmode_after'))] * 60
		self.settings['mythps_dailywakeup'] = Addon.getSetting('mythps_dailywakeup')
		self.settings['mythps_dailywakeup_time'] = int(Addon.getSetting('mythps_dailywakeup_time')) * 1800

	# get timers from mythtv
	def getTimers(self):
		xbmc.log(msg="mythtv.powersave: Getting timers ...", level=xbmc.LOGDEBUG)
		# if we have lost the connection to mythbackend, don't try to update the timers.  This should never happen
		# because self._MythBackend == False should get caught at the top of the loop.
		if (self._MythBackend != False):
			self._nextWakeup = self.getNextWake()

		self._SafePowerManager.updateStatus()

	# set the alarm clock if necessary
	def setWakeup(self):
		xbmc.log(msg="mythtv.powersave: Setting wake time...", level=xbmc.LOGDEBUG)
		# calculate next wakeup time
		stampWakeup = self.getMostRecentTimer() - self.settings['mythps_forerun']

		stampNow = int(time.time())

		# some extra calculations for daily wakeing
		if (self.settings['mythps_dailywakeup'] == "true"):
			# extract date and time only
			tupleNow = time.localtime(stampNow)
			stampTimeOnly = (tupleNow.tm_hour*3600)+(tupleNow.tm_min*60)+tupleNow.tm_sec
			stampDateOnly = time.mktime((tupleNow.tm_year,tupleNow.tm_mon,tupleNow.tm_mday,0,0,0,tupleNow.tm_wday,tupleNow.tm_yday,tupleNow.tm_isdst))

			# wake me today, or tomorrow?
			if (self.settings['mythps_dailywakeup_time'] > stampTimeOnly):
				stampDailyWakeup = stampDateOnly + self.settings['mythps_dailywakeup_time']
			else:
				# add a whole day
				stampDailyWakeup = stampDateOnly + self.settings['mythps_dailywakeup_time'] + 86400
			

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
			os.system("%s %d" % (self.settings['mythps_wakecmd'],stampFinalWakeup))
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
			return self._nextWakeup

		#we need this try in case there are no recordings scheduled
		try:
			rectime = progs.next().recstartts
			xbmc.log(msg="mythtv.powersave: got record time: %s" % rectime, level=xbmc.LOGDEBUG)
			return int(rectime.strftime("%s"))
		except:
			return self._nextWakeup

	# returns if any timer is actually recording
	def getIsRecording(self):
		return not self._SafePowerManager.okToShutdown()
	
	# this returns the most recent enabled timestamp, or None
	def getMostRecentTimer(self):
		return self._nextWakeup

	# function to actually do the powersaving
	def doPowersave(self):
		
		#show dialog box - give chance to abort
		duration = self.settings['mythps_warn_time']
		powerFunc = self._enum_powerfunc[self.settings['mythps_sleepmode']-1]

		xbmc.log(msg="mythtv.powersave: creating powersave dialog box for %s" % powerFunc, level=xbmc.LOGDEBUG)
		pDialog = xbmcgui.DialogProgress()
		pDialog.create("MythTV Powersave", "Preparing to %s" % powerFunc)

		i = 0
		while(i < duration and not pDialog.iscanceled()):
			percent = int(i/float(duration) * 100)
			text = "%s in %d seconds" % (powerFunc, (duration - i))
			xbmc.log(msg="mythtv.powersave: updating dialog with %d" % percent, level=xbmc.LOGDEBUG)
			pDialog.update(percent, text)
			i = i + 1
			xbmc.sleep(1000)

		pDialog.close()

		# reset idle time in case dialog was cancelled.
		self._realIdleTime = 0

		# check if dialog was cancelled.  If not, try to powerdown (this will check status again)
		if not pDialog.iscanceled():
			self._SafePowerManager.do(powerFunc)

