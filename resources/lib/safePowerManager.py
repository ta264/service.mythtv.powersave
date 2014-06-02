import xbmc, subprocess

class SafePowerManager:
    _checkshutdown = "checkshutdown"
    _okToShutdown = False

    def __init__(self):
        self.updateStatus()

    def updateStatus(self):

        try:
            output = subprocess.call(self._checkshutdown)
            xbmc.log(msg="mythtv.powersave: Checkshutdown returned: %d" % output, level=xbmc.LOGDEBUG)
            self._okToShutdown = (output == 0)
        except:
            self._okToShutdown = False
            xbmc.log(msg="mythtv.powersave: Querying checkshutdown failed! Not allowing powersave", level=xbmc.LOGERROR)

    def okToShutdown(self):
        return self._okToShutdown
            
    def do(self, functionstr):
        self.updateStatus()
        if self.okToShutdown():
            xbmc.log(msg="mythtv.powersave: executing builtin function: '%s'" % functionstr, level=xbmc.LOGNOTICE)
            xbmc.executebuiltin(functionstr)

    def Reboot(self):
        self.do("Reboot")

    def ShutDown(self):
        self.do("ShutDown")

    def Powerdown(self):
        self.do("Powerdown")

    def Hibernate(self):
        self.do("Hibernate")

    def Suspend(self):
        self.do("Suspend")



    
