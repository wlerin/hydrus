#!/usr/bin/env python2

import locale

try: locale.setlocale( locale.LC_ALL, '' )
except: pass

from include import HydrusConstants as HC
from include import ClientConstants as CC
from include import HydrusGlobals
from include import ClientDefaults
from include import ClientNetworking
from include import HydrusPubSub
from include import HydrusSessions
from include import HydrusTags
from include import HydrusThreading
from include import TestClientConstants
from include import TestClientDaemons
from include import TestClientDownloading
from include import TestConstants
from include import TestDialogs
from include import TestDB
from include import TestFunctions
from include import TestHydrusEncryption
from include import TestClientImageHandling
from include import TestHydrusNATPunch
from include import TestHydrusServer
from include import TestHydrusSessions
from include import TestHydrusTags
import collections
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import unittest
import wx
from twisted.internet import reactor
from include import ClientCaches
from include import ClientData
from include import HydrusData

only_run = None

class Controller( object ):
    
    def __init__( self ):
        
        HC.DB_DIR = tempfile.mkdtemp()
        
        HC.CLIENT_ARCHIVES_DIR = os.path.join( HC.DB_DIR, 'client_archives' )
        HC.CLIENT_FILES_DIR = os.path.join( HC.DB_DIR, 'client_files' )
        HC.CLIENT_THUMBNAILS_DIR = os.path.join( HC.DB_DIR, 'client_thumbnails' )
        HC.CLIENT_UPDATES_DIR = os.path.join( HC.DB_DIR, 'client_updates' )
        
        HC.SERVER_FILES_DIR = os.path.join( HC.DB_DIR, 'server_files' )
        HC.SERVER_THUMBNAILS_DIR = os.path.join( HC.DB_DIR, 'server_thumbnails' )
        HC.SERVER_UPDATES_DIR = os.path.join( HC.DB_DIR, 'server_updates' )
        
        os.makedirs( HC.CLIENT_FILES_DIR )
        
        HydrusGlobals.controller = self
        HydrusGlobals.client_controller = self
        HydrusGlobals.server_controller = self
        HydrusGlobals.test_controller = self
        
        self._pubsub = HydrusPubSub.HydrusPubSub( self )
        
        self._new_options = ClientData.ClientOptions()
        
        def show_text( text ): pass
        
        HydrusData.ShowText = show_text
        
        self._call_to_threads = [ HydrusThreading.THREADCallToThread( self ) for i in range( 10 ) ]
        
        for thread in self._call_to_threads:
            
            thread.start()
            
        
        self._http = ClientNetworking.HTTPConnectionManager()
        
        self._reads = {}
        
        self._reads[ 'hydrus_sessions' ] = []
        self._reads[ 'local_booru_share_keys' ] = []
        self._reads[ 'messaging_sessions' ] = []
        self._reads[ 'tag_censorship' ] = []
        self._reads[ 'options' ] = ClientDefaults.GetClientDefaultOptions()
        
        services = []
        services.append( ClientData.GenerateService( CC.LOCAL_BOORU_SERVICE_KEY, HC.LOCAL_BOORU, CC.LOCAL_BOORU_SERVICE_KEY, { 'max_monthly_data' : None, 'used_monthly_data' : 0 } ) )
        services.append( ClientData.GenerateService( CC.LOCAL_FILE_SERVICE_KEY, HC.LOCAL_FILE, CC.LOCAL_FILE_SERVICE_KEY, {} ) )
        services.append( ClientData.GenerateService( CC.LOCAL_TAG_SERVICE_KEY, HC.LOCAL_TAG, CC.LOCAL_TAG_SERVICE_KEY, {} ) )
        self._reads[ 'services' ] = services
        
        client_files_locations = { prefix : HC.CLIENT_FILES_DIR for prefix in HydrusData.IterateHexPrefixes() }
        
        self._reads[ 'client_files_locations' ] = client_files_locations
        
        self._reads[ 'sessions' ] = []
        self._reads[ 'tag_parents' ] = {}
        self._reads[ 'tag_siblings' ] = {}
        self._reads[ 'web_sessions' ] = {}
        
        HC.options = ClientDefaults.GetClientDefaultOptions()
        
        self._writes = collections.defaultdict( list )
        
        self._managers = {}
        
        self._services_manager = ClientCaches.ServicesManager( self )
        self._client_files_manager = ClientCaches.ClientFilesManager( self )
        self._client_session_manager = ClientCaches.HydrusSessionManager( self )
        
        self._managers[ 'tag_censorship' ] = ClientCaches.TagCensorshipManager( self )
        self._managers[ 'tag_siblings' ] = ClientCaches.TagSiblingsManager( self )
        self._managers[ 'tag_parents' ] = ClientCaches.TagParentsManager( self )
        self._managers[ 'undo' ] = ClientCaches.UndoManager( self )
        self._managers[ 'web_sessions' ] = TestConstants.FakeWebSessionManager()
        self._server_session_manager = HydrusSessions.HydrusSessionManagerServer()
        self._managers[ 'local_booru' ] = ClientCaches.LocalBooruCache( self )
        
        self._cookies = {}
        
    
    def pub( self, topic, *args, **kwargs ):
        
        pass
        
    
    def pubimmediate( self, topic, *args, **kwargs ):
        
        self._pubsub.pubimmediate( topic, *args, **kwargs )
        
    
    def sub( self, object, method_name, topic ):
        
        self._pubsub.sub( object, method_name, topic )
        
    
    def CallToThread( self, callable, *args, **kwargs ):
        
        call_to_thread = random.choice( self._call_to_threads )
        
        while call_to_thread == threading.current_thread: call_to_thread = random.choice( self._call_to_threads )
        
        call_to_thread.put( callable, *args, **kwargs )
        
    
    def DoHTTP( self, *args, **kwargs ): return self._http.Request( *args, **kwargs )
    
    def GetClientFilesManager( self ):
        
        return self._client_files_manager
        
    
    def GetClientSessionManager( self ):
        
        return self._client_session_manager
        
    
    def GetHTTP( self ): return self._http
    
    def GetNewOptions( self ):
        
        return self._new_options
        
    
    def GetOptions( self ):
        
        return HC.options
        
    
    def GetManager( self, manager_type ): return self._managers[ manager_type ]
    
    def GetServicesManager( self ):
        
        return self._services_manager
        
    
    def GetServerSessionManager( self ):
        
        return self._server_session_manager
        
    
    def GetWrite( self, name ):
        
        write = self._writes[ name ]
        
        del self._writes[ name ]
        
        return write
        
    
    def ModelIsShutdown( self ):
        
        return HydrusGlobals.model_shutdown
        
    
    def Read( self, name, *args, **kwargs ): return self._reads[ name ]
    
    def ResetIdleTimer( self ): pass
    
    def Run( self ):
        
        suites = []
        
        if only_run is None: run_all = True
        else: run_all = False
        
        if run_all or only_run == 'cc': suites.append( unittest.TestLoader().loadTestsFromModule( TestClientConstants ) )
        if run_all or only_run == 'daemons': suites.append( unittest.TestLoader().loadTestsFromModule( TestClientDaemons ) )
        if run_all or only_run == 'dialogs': suites.append( unittest.TestLoader().loadTestsFromModule( TestDialogs ) )
        if run_all or only_run == 'db': suites.append( unittest.TestLoader().loadTestsFromModule( TestDB ) )
        if run_all or only_run == 'downloading': suites.append( unittest.TestLoader().loadTestsFromModule( TestClientDownloading ) )
        if run_all or only_run == 'encryption': suites.append( unittest.TestLoader().loadTestsFromModule( TestHydrusEncryption ) )
        if run_all or only_run == 'functions': suites.append( unittest.TestLoader().loadTestsFromModule( TestFunctions ) )
        if run_all or only_run == 'image': suites.append( unittest.TestLoader().loadTestsFromModule( TestClientImageHandling ) )
        if run_all or only_run == 'nat': suites.append( unittest.TestLoader().loadTestsFromModule( TestHydrusNATPunch ) )
        if run_all or only_run == 'server': suites.append( unittest.TestLoader().loadTestsFromModule( TestHydrusServer ) )
        if run_all or only_run == 'sessions': suites.append( unittest.TestLoader().loadTestsFromModule( TestHydrusSessions ) )
        if run_all or only_run == 'tags': suites.append( unittest.TestLoader().loadTestsFromModule( TestHydrusTags ) )
        
        suite = unittest.TestSuite( suites )
        
        runner = unittest.TextTestRunner( verbosity = 1 )
        
        runner.run( suite )
        
    
    def SetHTTP( self, http ): self._http = http
    
    def SetRead( self, name, value ): self._reads[ name ] = value
    
    def SetWebCookies( self, name, value ): self._cookies[ name ] = value
    
    def TidyUp( self ):
        
        shutil.rmtree( HC.DB_DIR )
        
    
    def ViewIsShutdown( self ):
        
        return HydrusGlobals.view_shutdown
        
    
    def Write( self, name, *args, **kwargs ):
        
        self._writes[ name ].append( ( args, kwargs ) )
        
    
    def WriteSynchronous( self, name, *args, **kwargs ):
        
        self._writes[ name ].append( ( args, kwargs ) )
        
        if name == 'import_file':
            
            ( path, ) = args
            
            with open( path, 'rb' ) as f: file = f.read()
            
            if file == 'blarg': raise Exception( 'File failed to import for some reason!' )
            else: return ( CC.STATUS_SUCCESSFUL, '0123456789abcdef'.decode( 'hex' ) )
            
        
    
if __name__ == '__main__':
    
    args = sys.argv[1:]
    
    if len( args ) > 0:
        
        only_run = args[0]
        
    else: only_run = None
    
    try:
        
        original_db_dir = HC.DB_DIR
        
        threading.Thread( target = reactor.run, kwargs = { 'installSignalHandlers' : 0 } ).start()
        
        controller = Controller()
        
        app = wx.App()
        
        win = wx.Frame( None )
        
        wx.CallAfter( controller.Run )
        #threading.Thread( target = controller.Run ).start()
        
        wx.CallAfter( win.Destroy )
        
        app.MainLoop()
        
    except:
        
        import traceback
        
        traceback.print_exc()
        
    finally:
        
        HydrusGlobals.view_shutdown = True
        
        controller.pubimmediate( 'wake_daemons' )
        
        HydrusGlobals.model_shutdown = True
        
        controller.pubimmediate( 'wake_daemons' )
        
        if HC.DB_DIR != original_db_dir:
            
            controller.TidyUp()
            
        
        reactor.callFromThread( reactor.stop )
        
        raw_input()
        
    