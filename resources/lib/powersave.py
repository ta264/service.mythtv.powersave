import sys, os, time
import xbmc, xbmcaddon, xbmcgui
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
	_nextRecStart = 0
	_lastSetWakeup = 0
	_idleTime = 0
	_lastIdleTime = 0
	_realIdleTime = 0
        _wasBusy = False
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
			self._lastIdleTime, self._idleTime = self._idleTime, xbmc.getGlobalIdleTime()
			if (self._idleTime > self._lastIdleTime):
				self._realIdleTime += self._idleTime - self._lastIdleTime
			else:
				self._realIdleTime = self._idleTime

			# now this one is tricky: a playback ended, idle would suggest to powersave, but we set the clock back for overrun. 
			# Otherwise xbmc could sleep instantly at the end of a movie
                        isBusyTemp = self.isBusy()
			if (self._wasBusy  == True and 
                            isBusyTemp == False and 
                            self._realIdleTime >= self.settings['mythps_sleepmode_after']):
				self._realIdleTime = self.settings['mythps_sleepmode_after'] - self.settings['mythps_overrun']
                        self._wasBusy = isBusyTemp

			xbmc.log(msg="mythtv.powersave: isBusy: %s" % isBusyTemp, level=xbmc.LOGDEBUG)
			xbmc.log(msg="mythtv.powersave: IdleTime: %d" % self._realIdleTime, level=xbmc.LOGDEBUG)

			# powersave checks ...
			if (self.settings['mythps_sleepmode'] > 0 and
                            self._realIdleTime >= self.settings['mythps_sleepmode_after']):
				# sleeping time already?
				if (self._wasBusy):
					xbmc.log(msg="mythtv.powersave: powersave postponed - busy...", level=xbmc.LOGDEBUG)
				else:
					self.doPowersave()
			
			# sleep a little ...
			xbmc.sleep(self._sleep_interval)

		# Exiting, last second check of timers
		self.getTimers()
		# last second alarm clock update
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

		#check for exception connecting to backend
		try:
			progs = self._MythBackend.getUpcomingRecordings()
		except:
			self._MythBackend = False
			xbmc.log(msg="mythtv.powersave: Connection to mythbackend lost!!", level=xbmc.LOGERROR)
			# Don't change recording

		#we need this try in case there are no recordings scheduled
		try:
                        # The python binding returns a datetime object.  Convert to UTC time object.
			rectime = progs.next().recstartts.utctimetuple()
			xbmc.log(msg="mythtv.powersave: next recording is at: %s" % time.strftime("%c", rectime), level=xbmc.LOGDEBUG)
			self._nextRecStart = time.mktime(rectime)
		except StopIteration:
                        # If we don't have a scheduled recording, return 0
                        xbmc.log(msg="mythtv.powersave: no scheduled recordings", level=xbmc.LOGDEBUG)
			self._nextRecStart = 0

		self._SafePowerManager.updateStatus()

	# set the alarm clock if necessary
	def setWakeup(self):

		xbmc.log(msg="mythtv.powersave: Setting wake time...", level=xbmc.LOGDEBUG)
		xbmc.log(msg="mythtv.powersave: next recording start time: %s" % time.asctime(time.gmtime(self.getNextRecStart())), level=xbmc.LOGDEBUG)

		# initial values
		stampNow = int(time.time())
		stampRecWakeup = max(self.getNextRecStart() - self.settings['mythps_forerun'], stampNow)
                stampDailyWakeup = stampRecWakeup

		# some extra calculations for daily wakeing
		if (self.settings['mythps_dailywakeup'] == "true"):

			# extract date and time only.  Assume daily wake time is in local time not UTC
			tupleNow = time.localtime(stampNow)
			stampTimeOnly = (tupleNow.tm_hour*3600)+(tupleNow.tm_min*60)+tupleNow.tm_sec
			stampDateOnly = time.mktime((tupleNow.tm_year,tupleNow.tm_mon,tupleNow.tm_mday,0,0,0,tupleNow.tm_wday,tupleNow.tm_yday,tupleNow.tm_isdst))

                        # Calculate daily wakup time and add a day if we have gone past today's
                        stampDailyWakeup = stampDateOnly + self.settings['mythps_dailywakeup_time']
			if (stampTimeOnly > self.settings['mythps_dailywakeup_time']):
				stampDailyWakeup += 86400
                
                        xbmc.log(msg="mythtv.powersave: next scheduled daily wake: %s" % time.asctime(time.gmtime(stampDailyWakeup)), level=xbmc.LOGDEBUG)
                
                # Wake at earlier of next daily wake or next recording wake
                stampFinalWakeup = min(stampRecWakeup, stampDailyWakeup)
		
		xbmc.log(msg="mythtv.powersave: final wake time: %s" % time.asctime(time.gmtime(stampFinalWakeup)), level=xbmc.LOGDEBUG)
		xbmc.log(msg="mythtv.powersave: time now: %s" % time.asctime(time.gmtime(stampNow)), level=xbmc.LOGDEBUG)
		xbmc.log(msg="mythtv.powersave: previously set wake at: %s" % time.asctime(time.gmtime(self._lastSetWakeup)), level=xbmc.LOGDEBUG)

                # Actually set wakeup
		if (stampFinalWakeup>stampNow) and (stampFinalWakeup != self._lastSetWakeup):
			xbmc.log(msg="mythtv.powersave: Setting wake up on timestamp %s (%s)" % (stampFinalWakeup, time.asctime(time.gmtime(stampFinalWakeup))), level=xbmc.LOGNOTICE)
			os.system("%s %d" % (self.settings['mythps_wakecmd'],stampFinalWakeup))
			self._lastSetWakeup = stampFinalWakeup
		else:
			xbmc.log(msg="mythtv.powersave: no wake required or wake time already set", level=xbmc.LOGDEBUG)
			
	# checks if SafePowerManager is happy, xbmc is playing or we are due to start recording soon.
	def isBusy(self):
                pm_busy = not self._SafePowerManager.okToShutdown()
                xbmc_busy = xbmc.Player().isPlaying()
                rec_starting = self.getNextRecStart() - self.settings['mythps_forerun'] - 5 * 60 <= int(time.time()) <= self.getNextRecStart() + 60

                xbmc.log(msg="mythtv.powersave: pm_busy: %s" % pm_busy, level=xbmc.LOGDEBUG)
                xbmc.log(msg="mythtv.powersave: xbmc_busy: %s" % xbmc_busy, level=xbmc.LOGDEBUG)
                xbmc.log(msg="mythtv.powersave: rec_starting: %s" % rec_starting, level=xbmc.LOGDEBUG)

                busy = pm_busy or xbmc_busy or rec_starting

		return busy

	# this returns the most recent enabled timestamp, or 0 if there isn't one
	def getNextRecStart(self):
		return self._nextRecStart

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

