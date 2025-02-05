import collections
import gc
import HydrusConstants as HC
import HydrusDaemons
import HydrusData
import HydrusDB
import HydrusExceptions
import HydrusGlobals
import HydrusPubSub
import HydrusThreading
import os
import random
import sys
import threading
import time
import traceback

class HydrusController( object ):
    
    pubsub_binding_errors_to_ignore = []
    
    def __init__( self ):
        
        HydrusGlobals.controller = self
        
        self._no_daemons = False
        self._no_wal = False
        
        self._InitArgsBools()
        
        self._no_wal_path = os.path.join( HC.DB_DIR, 'no-wal' )
        
        if os.path.exists( self._no_wal_path ):
            
            self._no_wal = True
            
        
        self._model_shutdown = False
        self._view_shutdown = False
        
        self._db = None
        
        self._pubsub = HydrusPubSub.HydrusPubSub( self, self.pubsub_binding_errors_to_ignore )
        
        self._currently_doing_pubsub = False
        
        self._daemons = []
        self._caches = {}
        self._managers = {}
        
        self._call_to_threads = [ HydrusThreading.THREADCallToThread( self ) for i in range( 10 ) ]
        
        self._timestamps = collections.defaultdict( lambda: 0 )
        
        self._timestamps[ 'boot' ] = HydrusData.GetNow()
        
        self._just_woke_from_sleep = False
        self._system_busy = False
        
    
    def _InitArgsBools( self ):
        
        args = sys.argv[1:]
        
        for arg in args:
            
            while arg.startswith( '-' ):
                
                arg = arg[ 1: ]
                
            
            if arg in ( 'no-daemon', 'no-daemons' ):
                
                self._no_daemons = True
                
            
            if arg == 'no-wal':
                
                self._no_wal = True
                
            
        
    
    def _InitDB( self ):
        
        raise NotImplementedError()
        
    
    def _Read( self, action, *args, **kwargs ):
        
        result = self._db.Read( action, HC.HIGH_PRIORITY, *args, **kwargs )
        
        time.sleep( 0.00001 )
        
        return result
        
    
    def _ShutdownDaemons( self ):
        
        for daemon in self._daemons:
            
            daemon.shutdown()
            
        
        while True in ( daemon.is_alive() for daemon in self._daemons ):
            
            time.sleep( 0.1 )
            
        
        self._daemons = []
        
    
    def _Write( self, action, priority, synchronous, *args, **kwargs ):
        
        result = self._db.Write( action, priority, synchronous, *args, **kwargs )
        
        time.sleep( 0.00001 )
        
        return result
        
    
    def pub( self, topic, *args, **kwargs ):
        
        self._pubsub.pub( topic, *args, **kwargs )
        
    
    def pubimmediate( self, topic, *args, **kwargs ):
        
        self._pubsub.pubimmediate( topic, *args, **kwargs )
        
    
    def sub( self, object, method_name, topic ):
        
        self._pubsub.sub( object, method_name, topic )
        
    
    def CallToThread( self, callable, *args, **kwargs ):
        
        call_to_thread = random.choice( self._call_to_threads )
        
        while call_to_thread == threading.current_thread: call_to_thread = random.choice( self._call_to_threads )
        
        call_to_thread.put( callable, *args, **kwargs )
        
    
    def ClearCaches( self ):
        
        for cache in self._caches.values(): cache.Clear()
        
    
    def CreateNoWALFile( self ):
        
        with open( self._no_wal_path, 'wb' ) as f:
            
            f.write( 'This file was created because the database failed to set WAL journalling. It will not reattempt WAL as long as this file exists.' )
            
        
    
    def CurrentlyIdle( self ): return True
    
    def GetCache( self, name ): return self._caches[ name ]
    
    def GetManager( self, name ): return self._managers[ name ]
    
    def GoodTimeToDoBackgroundWork( self ):
        
        return not ( self.JustWokeFromSleep() or self.SystemBusy() )
        
    
    def JustWokeFromSleep( self ):
        
        self.SleepCheck()
        
        return self._just_woke_from_sleep
        
    
    def InitModel( self ):
        
        for thread in self._call_to_threads:
            
            thread.start()
            
        
        self._db = self._InitDB()
        
    
    def InitView( self ):
        
        if not self._no_daemons:
            
            self._daemons.append( HydrusThreading.DAEMONWorker( self, 'SleepCheck', HydrusDaemons.DAEMONSleepCheck, period = 120 ) )
            self._daemons.append( HydrusThreading.DAEMONWorker( self, 'MaintainMemory', HydrusDaemons.DAEMONMaintainMemory, period = 300 ) )
            
            self._daemons.append( HydrusThreading.DAEMONBigJobWorker( self, 'MaintainDB', HydrusDaemons.DAEMONMaintainDB, period = 300 ) )
            
        
    
    def MaintainDB( self, stop_time = None ):
        
        pass
        
    
    def MaintainMemory( self ):
        
        sys.stdout.flush()
        sys.stderr.flush()
        
        gc.collect()
        
    
    def ModelIsShutdown( self ):
        
        return self._model_shutdown
        
    
    def NotifyPubSubs( self ):
        
        raise NotImplementedError()
        
    
    def ProcessPubSub( self ):
        
        self._currently_doing_pubsub = True
        
        try: self._pubsub.Process()
        finally: self._currently_doing_pubsub = False
        
    
    def Read( self, action, *args, **kwargs ): return self._Read( action, *args, **kwargs )
    
    def ShutdownModel( self ):
        
        self._model_shutdown = True
        HydrusGlobals.model_shutdown = True
        
        if self._db is not None:
            
            while not self._db.LoopIsFinished(): time.sleep( 0.1 )
            
        
    
    def ShutdownView( self ):
        
        self._view_shutdown = True
        HydrusGlobals.view_shutdown = True
        
        self._ShutdownDaemons()
        
    
    def ShutdownFromServer( self ):
        
        raise Exception( 'This hydrus application cannot be shut down from the server!' )
        
    
    def SleepCheck( self ):
        
        if HydrusData.TimeHasPassed( self._timestamps[ 'now_awake' ] ):
            
            last_sleep_check = self._timestamps[ 'last_sleep_check' ]
            
            if last_sleep_check == 0:
                
                self._just_woke_from_sleep = False
                
            else:
                
                if HydrusData.TimeHasPassed( last_sleep_check + 600 ):
                    
                    self._just_woke_from_sleep = True
                    
                    self._timestamps[ 'now_awake' ] = HydrusData.GetNow() + 180
                    
                else:
                    
                    self._just_woke_from_sleep = False
                    
                
            
        
        self._timestamps[ 'last_sleep_check' ] = HydrusData.GetNow()
        
    
    def SystemBusy( self ):
        
        return self._system_busy
        
    
    def ViewIsShutdown( self ):
        
        return self._view_shutdown
        
    
    def WaitUntilPubSubsEmpty( self ):
        
        while True:
            
            if self._view_shutdown:
                
                raise HydrusExceptions.ShutdownException( 'Application shutting down!' )
                
            elif self._pubsub.NoJobsQueued() and not self._currently_doing_pubsub:
                
                return
                
            else:
                
                time.sleep( 0.00001 )
                
            
        
    
    def Write( self, action, *args, **kwargs ):
        
        return self._Write( action, HC.HIGH_PRIORITY, False, *args, **kwargs )
        
    
    def WriteInterruptable( self, action, *args, **kwargs ):
        
        return self._Write( action, HC.INTERRUPTABLE_PRIORITY, True, *args, **kwargs )
        
    
    def WriteSynchronous( self, action, *args, **kwargs ):
        
        return self._Write( action, HC.LOW_PRIORITY, True, *args, **kwargs )
        
    