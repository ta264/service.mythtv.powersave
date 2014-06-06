import urlparse
import xbmc
from resources.lib.safePowerManager import SafePowerManager

def get_params():
    param = {}
    
    if(len(sys.argv) > 1):
        for i in sys.argv:
            args = i
            if(args.startswith('?')):
                args = args[1:]
            param.update(dict(urlparse.parse_qsl(args)))
            
    return param

params = get_params()
_safePowerManager = SafePowerManager()

if("powerfunc" in params):
    functionstr = params['powerfunc']
    xbmc.log(msg="script.mythtv.powersave: Requested function is %s" % functionstr, level=xbmc.LOGDEBUG)
    _safePowerManager.do(functionstr)
else:
    xbmc.log(msg="script.mythtv.powersave: Requested function not found", level=xbmc.LOGDEBUG)
