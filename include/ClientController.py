import ClientCaches
import ClientData
import ClientDaemons
import ClientDefaults
import ClientNetworking
import ClientThreading
import hashlib
import httplib
import HydrusConstants as HC
import HydrusController
import HydrusData
import HydrusExceptions
import HydrusGlobals
import HydrusNetworking
import HydrusSerialisable
import HydrusSessions
import HydrusTags
import HydrusThreading
import ClientConstants as CC
import ClientDB
import ClientGUI
import ClientGUIDialogs
import os
import psutil
import random
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import wx
from twisted.internet import reactor
from twisted.internet import defer

class Controller( HydrusController.HydrusController ):
    
    pubsub_binding_errors_to_ignore = [ wx.PyDeadObjectError ]
    
    def __init__( self ):
        
        HydrusController.HydrusController.__init__( self )
        
        HydrusGlobals.client_controller = self
        
        # just to set up some defaults, in case some db update expects something for an odd yaml-loading reason
        self._options = ClientDefaults.GetClientDefaultOptions()
        self._new_options = ClientData.ClientOptions()
        
        HC.options = self._options
        
        self._last_mouse_position = None
        self._menu_open = False
        self._previously_idle = False
        self._idle_started = None
        
    
    def _InitDB( self ):
        
        return ClientDB.DB( self, HC.DB_DIR, 'client', no_wal = self._no_wal )
        
    
    def BackupDatabase( self ):
        
        with wx.DirDialog( self._gui, 'Select backup location.' ) as dlg:
            
            if dlg.ShowModal() == wx.ID_OK:
                
                path = HydrusData.ToUnicode( dlg.GetPath() )
                
                text = 'Are you sure "' + path + '" is the correct directory?'
                text += os.linesep * 2
                text += 'The database will be locked while the backup occurs, which may lock up your gui as well.'
                
                with ClientGUIDialogs.DialogYesNo( self._gui, text ) as dlg_yn:
                    
                    if dlg_yn.ShowModal() == wx.ID_YES:
                        
                        self.Write( 'backup', path )
                        
                    
                
            
        
    
    def CallBlockingToWx( self, callable, *args, **kwargs ):
        
        def wx_code( job_key ):
            
            try:
                
                result = callable( *args, **kwargs )
                
                job_key.SetVariable( 'result', result )
                
            except HydrusExceptions.PermissionException as e:
                
                job_key.SetVariable( 'error', e )
                
            except Exception as e:
                
                job_key.SetVariable( 'error', e )
                
                HydrusData.Print( 'CallBlockingToWx just caught this error:' )
                HydrusData.DebugPrint( traceback.format_exc() )
                
            finally: job_key.Finish()
            
        
        job_key = ClientThreading.JobKey()
        
        job_key.Begin()
        
        wx.CallAfter( wx_code, job_key )
        
        while not job_key.IsDone():
            
            if self._model_shutdown:
                
                return
                
            
            time.sleep( 0.05 )
            
        
        if job_key.HasVariable( 'result' ):
            
            return job_key.GetVariable( 'result' )
            
        elif job_key.HasVariable( 'error' ):
            
            raise job_key.GetVariable( 'error' )
            
        else:
            
            raise HydrusExceptions.ShutdownException()
            
        
    
    def CheckAlreadyRunning( self ):
    
        while HydrusData.IsAlreadyRunning( 'client' ):
            
            self.pub( 'splash_set_status_text', 'client already running' )
            
            def wx_code():
                
                message = 'It looks like another instance of this client is already running, so this instance cannot start.'
                message += os.linesep * 2
                message += 'If the old instance is closing and does not quit for a _very_ long time, it is usually safe to force-close it from task manager.'
                
                with ClientGUIDialogs.DialogYesNo( self._splash, message, 'The client is already running.', yes_label = 'wait a bit, then try again', no_label = 'forget it' ) as dlg:
                    
                    if dlg.ShowModal() != wx.ID_YES:
                        
                        raise HydrusExceptions.PermissionException()
                        
                    
                
            
            self.CallBlockingToWx( wx_code )
            
            for i in range( 10, 0, -1 ):
                
                if not HydrusData.IsAlreadyRunning( 'client' ):
                    
                    break
                    
                
                self.pub( 'splash_set_status_text', 'waiting ' + str( i ) + ' seconds' )
                
                time.sleep( 1 )
                
            
        
    
    def CheckMouseIdle( self ):
        
        mouse_position = wx.GetMousePosition()
        
        if self._last_mouse_position is None:
            
            self._last_mouse_position = mouse_position
            
        elif mouse_position != self._last_mouse_position:
            
            idle_before = self.CurrentlyIdle()
            
            self._timestamps[ 'last_mouse_action' ] = HydrusData.GetNow()
            
            self._last_mouse_position = mouse_position
            
            idle_after = self.CurrentlyIdle()
            
            if idle_before != idle_after:
                
                self.pub( 'refresh_status' )
                
            
        
    
    def Clipboard( self, data_type, data ):
        
        # need this cause can't do it in a non-gui thread
        
        if data_type == 'paths':
            
            paths = data
            
            if wx.TheClipboard.Open():
                
                data = wx.DataObjectComposite()
                
                file_data = wx.FileDataObject()
                
                for path in paths: file_data.AddFile( path )
                
                text_data = wx.TextDataObject( os.linesep.join( paths ) )
                
                data.Add( file_data, True )
                data.Add( text_data, False )
                
                wx.TheClipboard.SetData( data )
                
                wx.TheClipboard.Close()
                
            else: wx.MessageBox( 'Could not get permission to access the clipboard!' )
            
        elif data_type == 'text':
            
            text = data
            
            if wx.TheClipboard.Open():
                
                data = wx.TextDataObject( text )
                
                wx.TheClipboard.SetData( data )
                
                wx.TheClipboard.Close()
                
            else: wx.MessageBox( 'I could not get permission to access the clipboard.' )
            
        elif data_type == 'bmp':
            
            media = data
            
            image_container = self.GetCache( 'fullscreen' ).GetImage( media )
            
            def CopyToClipboard():
                
                if wx.TheClipboard.Open():
                    
                    hydrus_bmp = image_container.GetHydrusBitmap()
                    
                    wx_bmp = hydrus_bmp.GetWxBitmap()
                    
                    data = wx.BitmapDataObject( wx_bmp )
                    
                    wx.TheClipboard.SetData( data )
                    
                    wx.TheClipboard.Close()
                    
                else: wx.MessageBox( 'I could not get permission to access the clipboard.' )
                
            
            def THREADWait():
                
                # have to do this in thread, because the image needs the wx event queue to render
                
                start_time = time.time()
                
                while not image_container.IsRendered():
                    
                    if HydrusData.TimeHasPassed( start_time + 15 ): raise Exception( 'The image did not render in fifteen seconds, so the attempt to copy it to the clipboard was abandoned.' )
                    
                    time.sleep( 0.1 )
                    
                
                wx.CallAfter( CopyToClipboard )
                
            
            self.CallToThread( THREADWait )
            
        
    
    def CreateSplash( self ):
        
        try:
            
            self._splash = ClientGUI.FrameSplash( self )
            
        except:
            
            HydrusData.Print( 'There was an error trying to start the splash screen!' )
            
            HydrusData.Print( traceback.format_exc() )
            
            raise
            
        
    
    def CurrentlyIdle( self ):
        
        if HydrusGlobals.force_idle_mode:
            
            self._idle_started = 0
            
            return True
            
        
        if not HydrusData.TimeHasPassed( self._timestamps[ 'boot' ] + 120 ):
            
            return False
            
        
        idle_normal = self._options[ 'idle_normal' ]
        idle_period = self._options[ 'idle_period' ]
        idle_mouse_period = self._options[ 'idle_mouse_period' ]
        
        if idle_normal:
            
            currently_idle = True
            
            if idle_period is not None:
                
                if not HydrusData.TimeHasPassed( self._timestamps[ 'last_user_action' ] + idle_period ):
                    
                    currently_idle = False
                    
                
            
            if idle_mouse_period is not None:
                
                if not HydrusData.TimeHasPassed( self._timestamps[ 'last_mouse_action' ] + idle_mouse_period ):
                    
                    currently_idle = False
                    
                
            
        else:
            
            currently_idle = False
            
        
        turning_idle = currently_idle and not self._previously_idle
        
        self._previously_idle = currently_idle
        
        if turning_idle:
            
            self._idle_started = HydrusData.GetNow()
            
            self.pub( 'wake_daemons' )
            
        
        if not currently_idle:
            
            self._idle_started = None
            
        
        return currently_idle
        
    
    def CurrentlyVeryIdle( self ):
        
        if self._idle_started is not None and HydrusData.TimeHasPassed( self._idle_started + 3600 ):
            
            return True
            
        
        return False
        
    
    def DoHTTP( self, *args, **kwargs ): return self._http.Request( *args, **kwargs )
    
    def DoIdleShutdownWork( self ):
        
        stop_time = HydrusData.GetNow() + ( self._options[ 'idle_shutdown_max_minutes' ] * 60 )
        
        self._client_files_manager.Rebalance( partial = False, stop_time = stop_time )
        
        self.MaintainDB( stop_time = stop_time )
        
        if not self._options[ 'pause_repo_sync' ]:
            
            services = self.GetServicesManager().GetServices( HC.REPOSITORIES )
            
            for service in services:
                
                if HydrusData.TimeHasPassed( stop_time ):
                    
                    return
                    
                
                service.Sync( only_when_idle = False, stop_time = stop_time )
                
            
        
    
    def Exit( self ):
        
        if HydrusGlobals.emergency_exit:
            
            self.ShutdownView()
            self.ShutdownModel()
            
        else:
            
            try:
                
                self.CreateSplash()
                
                idle_shutdown_action = self._options[ 'idle_shutdown' ]
                
                if idle_shutdown_action in ( CC.IDLE_ON_SHUTDOWN, CC.IDLE_ON_SHUTDOWN_ASK_FIRST ):
                    
                    if self.ThereIsIdleShutdownWorkDue():
                        
                        if idle_shutdown_action == CC.IDLE_ON_SHUTDOWN_ASK_FIRST:
                            
                            text = 'Is now a good time for the client to do up to ' + HydrusData.ConvertIntToPrettyString( self._options[ 'idle_shutdown_max_minutes' ] ) + ' minutes\' maintenance work?'
                            
                            with ClientGUIDialogs.DialogYesNo( self._splash, text, title = 'Maintenance is due' ) as dlg_yn:
                                
                                if dlg_yn.ShowModal() == wx.ID_YES:
                                    
                                    HydrusGlobals.do_idle_shutdown_work = True
                                    
                                
                            
                        else:
                            
                            HydrusGlobals.do_idle_shutdown_work = True
                            
                        
                    
                
                exit_thread = threading.Thread( target = self.THREADExitEverything, name = 'Application Exit Thread' )
                
                exit_thread.start()
                
            except:
                
                self.pub( 'splash_destroy' )
                
                HydrusData.DebugPrint( traceback.format_exc() )
                
                HydrusGlobals.emergency_exit = True
                
                self.Exit()
                
            
        
    
    def ForceIdle( self ):
        
        HydrusGlobals.force_idle_mode = not HydrusGlobals.force_idle_mode
        
        self.pub( 'wake_daemons' )
        self.pub( 'refresh_status' )
        
    
    def GetClientFilesManager( self ):
        
        return self._client_files_manager
        
    
    def GetClientSessionManager( self ):
        
        return self._client_session_manager
        
    
    def GetDB( self ): return self._db
    
    def GetGUI( self ): return self._gui
    
    def GetOptions( self ):
        
        return self._options
        
    
    def GetNewOptions( self ):
        
        return self._new_options
        
    
    def GetServicesManager( self ):
        
        return self._services_manager
        
    
    def InitModel( self ):
        
        self.pub( 'splash_set_title_text', 'booting db...' )
        
        self._http = ClientNetworking.HTTPConnectionManager()
        
        HydrusController.HydrusController.InitModel( self )
        
        self._options = self.Read( 'options' )
        self._new_options = self.Read( 'serialisable', HydrusSerialisable.SERIALISABLE_TYPE_CLIENT_OPTIONS )
        
        HC.options = self._options
        
        self._services_manager = ClientCaches.ServicesManager( self )
        
        self._client_files_manager = ClientCaches.ClientFilesManager( self )
        
        self._client_session_manager = ClientCaches.HydrusSessionManager( self )
        
        self._managers[ 'local_booru' ] = ClientCaches.LocalBooruCache( self )
        self._managers[ 'tag_censorship' ] = ClientCaches.TagCensorshipManager( self )
        self._managers[ 'tag_siblings' ] = ClientCaches.TagSiblingsManager( self )
        self._managers[ 'tag_parents' ] = ClientCaches.TagParentsManager( self )
        self._managers[ 'undo' ] = ClientCaches.UndoManager( self )
        self._managers[ 'web_sessions' ] = ClientCaches.WebSessionManagerClient( self )
        
        if HC.options[ 'proxy' ] is not None:
            
            ( proxytype, host, port, username, password ) = HC.options[ 'proxy' ]
            
            ClientNetworking.SetProxy( proxytype, host, port, username, password )
            
        
        def wx_code():
            
            self._caches[ 'fullscreen' ] = ClientCaches.RenderedImageCache( self, 'fullscreen' )
            self._caches[ 'preview' ] = ClientCaches.RenderedImageCache( self, 'preview' )
            self._caches[ 'thumbnail' ] = ClientCaches.ThumbnailCache( self )
            
            CC.GlobalBMPs.STATICInitialise()
            
        
        self.CallBlockingToWx( wx_code )
        
        self.sub( self, 'Clipboard', 'clipboard' )
        self.sub( self, 'RestartServer', 'restart_server' )
        self.sub( self, 'RestartBooru', 'restart_booru' )
        
    
    def InitView( self ):
        
        if self._options[ 'password' ] is not None:
            
            self.pub( 'splash_set_status_text', 'waiting for password' )
            
            def wx_code_password():
                
                while True:
                    
                    with wx.PasswordEntryDialog( self._splash, 'Enter your password', 'Enter password' ) as dlg:
                        
                        if dlg.ShowModal() == wx.ID_OK:
                            
                            if hashlib.sha256( dlg.GetValue() ).digest() == self._options[ 'password' ]: break
                            
                        else: raise HydrusExceptions.PermissionException( 'Bad password check' )
                        
                    
                
            
            self.CallBlockingToWx( wx_code_password )
            
        
        self.pub( 'splash_set_title_text', 'booting gui...' )
        
        def wx_code_gui():
            
            self._gui = ClientGUI.FrameGUI( self )
            
            # this is because of some bug in wx C++ that doesn't add these by default
            wx.richtext.RichTextBuffer.AddHandler( wx.richtext.RichTextHTMLHandler() )
            wx.richtext.RichTextBuffer.AddHandler( wx.richtext.RichTextXMLHandler() )
            
            self.ResetIdleTimer()
            
        
        self.CallBlockingToWx( wx_code_gui )
        
        HydrusController.HydrusController.InitView( self )
        
        self._local_service = None
        self._booru_service = None
        
        self.RestartServer()
        self.RestartBooru()
        
        if not self._no_daemons:
            
            self._daemons.append( HydrusThreading.DAEMONWorker( self, 'CheckMouseIdle', ClientDaemons.DAEMONCheckMouseIdle, period = 10 ) )
            self._daemons.append( HydrusThreading.DAEMONWorker( self, 'DownloadFiles', ClientDaemons.DAEMONDownloadFiles, ( 'notify_new_downloads', 'notify_new_permissions' ) ) )
            self._daemons.append( HydrusThreading.DAEMONWorker( self, 'SynchroniseAccounts', ClientDaemons.DAEMONSynchroniseAccounts, ( 'permissions_are_stale', ) ) )
            self._daemons.append( HydrusThreading.DAEMONWorker( self, 'SynchroniseSubscriptions', ClientDaemons.DAEMONSynchroniseSubscriptions, ( 'notify_restart_subs_sync_daemon', 'notify_new_subscriptions' ) ) )
            
            self._daemons.append( HydrusThreading.DAEMONBigJobWorker( self, 'CheckImportFolders', ClientDaemons.DAEMONCheckImportFolders, ( 'notify_restart_import_folders_daemon', 'notify_new_import_folders' ), period = 180 ) )
            self._daemons.append( HydrusThreading.DAEMONBigJobWorker( self, 'CheckExportFolders', ClientDaemons.DAEMONCheckExportFolders, ( 'notify_restart_export_folders_daemon', 'notify_new_export_folders' ), period = 180 ) )
            self._daemons.append( HydrusThreading.DAEMONBigJobWorker( self, 'MaintainTrash', ClientDaemons.DAEMONMaintainTrash, init_wait = 60 ) )
            self._daemons.append( HydrusThreading.DAEMONBigJobWorker( self, 'RebalanceClientFiles', ClientDaemons.DAEMONRebalanceClientFiles, period = 3600 ) )
            self._daemons.append( HydrusThreading.DAEMONBigJobWorker( self, 'SynchroniseRepositories', ClientDaemons.DAEMONSynchroniseRepositories, ( 'notify_restart_repo_sync_daemon', 'notify_new_permissions' ), period = 4 * 3600 ) )
            self._daemons.append( HydrusThreading.DAEMONBigJobWorker( self, 'UPnP', ClientDaemons.DAEMONUPnP, ( 'notify_new_upnp_mappings', ), init_wait = 120, pre_callable_wait = 6 ) )
            
            self._daemons.append( HydrusThreading.DAEMONQueue( self, 'FlushRepositoryUpdates', ClientDaemons.DAEMONFlushServiceUpdates, 'service_updates_delayed', period = 5 ) )
            
        
        if HydrusGlobals.is_first_start: wx.CallAfter( self._gui.DoFirstStart )
        if HydrusGlobals.is_db_updated: wx.CallLater( 1, HydrusData.ShowText, 'The client has updated to version ' + str( HC.SOFTWARE_VERSION ) + '!' )
        
    
    def MaintainDB( self, stop_time = None ):
        
        if stop_time is None:
            
            if not self.CurrentlyVeryIdle():
                
                stop_time = HydrusData.GetNow() + 30
                
            
        
        self.WriteInterruptable( 'vacuum', stop_time = stop_time )
        
        self.pub( 'splash_set_status_text', 'analyzing' )
        
        self.WriteInterruptable( 'analyze', stop_time = stop_time, only_when_idle = True )
        
        if stop_time is None or not HydrusData.TimeHasPassed( stop_time ):
            
            if HydrusData.TimeHasPassed( self._timestamps[ 'last_service_info_cache_fatten' ] + ( 60 * 20 ) ):
                
                self.pub( 'splash_set_status_text', 'fattening service info' )
                
                services = self.GetServicesManager().GetServices()
                
                for service in services:
                    
                    try: self.Read( 'service_info', service.GetServiceKey() )
                    except: pass # sometimes this breaks when a service has just been removed and the client is closing, so ignore the error
                    
                
                self._timestamps[ 'last_service_info_cache_fatten' ] = HydrusData.GetNow()
                
            
        
    
    def MaintainMemory( self ):
        
        HydrusController.HydrusController.MaintainMemory( self )
        
        if self._timestamps[ 'last_page_change' ] == 0:
            
            self._timestamps[ 'last_page_change' ] = HydrusData.GetNow()
            
        
        if HydrusData.TimeHasPassed( self._timestamps[ 'last_page_change' ] + 30 * 60 ):
            
            self.pub( 'clear_closed_pages' )
            
            self._timestamps[ 'last_page_change' ] = HydrusData.GetNow()
            
        
    
    def MenuIsOpen( self ):
        
        return self._menu_open
        
    
    def NotifyPubSubs( self ):
        
        wx.CallAfter( self.ProcessPubSub )
        
    
    def PageDeleted( self, page_key ):
        
        try:
            
            return self._gui.PageDeleted( page_key )
            
        except wx.PyDeadObjectError:
            
            return True
            
        
    
    def PageHidden( self, page_key ):
        
        return self._gui.PageHidden( page_key )
        
    
    def PopupMenu( self, window, menu ):
        
        if menu.GetMenuItemCount() > 0:
            
            self._menu_open = True
            
            window.PopupMenu( menu )
            
            self._menu_open = False
            
        
        wx.CallAfter( menu.Destroy )
        
    
    def PrepStringForDisplay( self, text ):
        
        if self._options[ 'gui_capitalisation' ]: return text
        else: return text.lower()
        
    
    def ResetIdleTimer( self ):
        
        self._timestamps[ 'last_user_action' ] = HydrusData.GetNow()
        
    
    def ResetPageChangeTimer( self ):
        
        self._timestamps[ 'last_page_change' ] = HydrusData.GetNow()
        
    
    def RestartBooru( self ):
        
        service = self.GetServicesManager().GetService( CC.LOCAL_BOORU_SERVICE_KEY )
        
        info = service.GetInfo()
        
        port = info[ 'port' ]
        
        def TWISTEDRestartServer():
            
            def StartServer( *args, **kwargs ):
                
                try:
                    
                    try:
                        
                        connection = HydrusNetworking.GetLocalConnection( port )
                        connection.close()
                        
                        text = 'The client\'s booru server could not start because something was already bound to port ' + str( port ) + '.'
                        text += os.linesep * 2
                        text += 'This usually means another hydrus client is already running and occupying that port. It could be a previous instantiation of this client that has yet to shut itself down.'
                        text += os.linesep * 2
                        text += 'You can change the port this client tries to host its local server on in services->manage services.'
                        
                        wx.CallLater( 1, HydrusData.ShowText, text )
                        
                    except:
                        
                        import ClientLocalServer
                        
                        self._booru_service = reactor.listenTCP( port, ClientLocalServer.HydrusServiceBooru( CC.LOCAL_BOORU_SERVICE_KEY, HC.LOCAL_BOORU, 'This is the local booru.' ) )
                        
                        try:
                            
                            connection = HydrusNetworking.GetLocalConnection( port )
                            connection.close()
                            
                        except Exception as e:
                            
                            text = 'Tried to bind port ' + str( port ) + ' for the local booru, but it failed:'
                            text += os.linesep * 2
                            text += HydrusData.ToUnicode( e )
                            
                            wx.CallLater( 1, HydrusData.ShowText, text )
                            
                        
                    
                except Exception as e:
                    
                    wx.CallAfter( HydrusData.ShowException, e )
                    
                
            
            if self._booru_service is None:
                
                if port is not None:
                    
                    StartServer()
                    
                
            else:
                
                deferred = defer.maybeDeferred( self._booru_service.stopListening )
                
                if port is not None:
                    
                    deferred.addCallback( StartServer )
                    
                
            
        
        reactor.callFromThread( TWISTEDRestartServer )
        
    
    def RestartServer( self ):
        
        port = self._options[ 'local_port' ]
        
        def TWISTEDRestartServer():
            
            def StartServer( *args, **kwargs ):
                
                try:
                    
                    try:
                        
                        connection = HydrusNetworking.GetLocalConnection( port )
                        connection.close()
                        
                        text = 'The client\'s local server could not start because something was already bound to port ' + str( port ) + '.'
                        text += os.linesep * 2
                        text += 'This usually means another hydrus client is already running and occupying that port. It could be a previous instantiation of this client that has yet to shut itself down.'
                        text += os.linesep * 2
                        text += 'You can change the port this client tries to host its local server on in file->options.'
                        
                        wx.CallLater( 1, HydrusData.ShowText, text )
                        
                    except:
                        
                        import ClientLocalServer
                        
                        self._local_service = reactor.listenTCP( port, ClientLocalServer.HydrusServiceLocal( CC.LOCAL_FILE_SERVICE_KEY, HC.LOCAL_FILE, 'This is the local file service.' ) )
                        
                        try:
                            
                            connection = HydrusNetworking.GetLocalConnection( port )
                            connection.close()
                            
                        except Exception as e:
                            
                            text = 'Tried to bind port ' + str( port ) + ' for the local server, but it failed:'
                            text += os.linesep * 2
                            text += HydrusData.ToUnicode( e )
                            
                            wx.CallLater( 1, HydrusData.ShowText, text )
                            
                        
                    
                except Exception as e:
                    
                    wx.CallAfter( HydrusData.ShowException, e )
                    
                
            
            if self._local_service is None:
                
                if port is not None:
                    
                    StartServer()
                    
                
            else:
                
                deferred = defer.maybeDeferred( self._local_service.stopListening )
                
                if port is not None:
                    
                    deferred.addCallback( StartServer )
                    
                
            
        
        reactor.callFromThread( TWISTEDRestartServer )
        
    
    def RestoreDatabase( self ):
        
        with wx.DirDialog( self._gui, 'Select backup location.' ) as dlg:
            
            if dlg.ShowModal() == wx.ID_OK:
                
                path = HydrusData.ToUnicode( dlg.GetPath() )
                
                text = 'Are you sure you want to restore a backup from "' + path + '"?'
                text += os.linesep * 2
                text += 'Everything in your current database will be deleted!'
                text += os.linesep * 2
                text += 'The gui will shut down, and then it will take a while to complete the restore. Once it is done, the client will restart.'
                
                with ClientGUIDialogs.DialogYesNo( self._gui, text ) as dlg_yn:
                    
                    if dlg_yn.ShowModal() == wx.ID_YES:
                        
                        def THREADRestart():
                            
                            wx.CallAfter( self.Exit )
                            
                            while not self._db.LoopIsFinished():
                                
                                time.sleep( 0.1 )
                                
                            
                            self._db.RestoreBackup( path )
                            
                            while not HydrusGlobals.shutdown_complete:
                                
                                time.sleep( 0.1 )
                                
                            
                            HydrusData.RestartProcess()
                            
                        
                        restart_thread = threading.Thread( target = THREADRestart, name = 'Application Restart Thread' )
                        
                        restart_thread.start()
                        
                    
                
            
        
    
    def Run( self ):
        
        self._app = wx.App()
        
        self._app.SetAssertMode( wx.PYAPP_ASSERT_SUPPRESS )
        
        HydrusData.Print( 'booting controller...' )
        
        self.CreateSplash()
        
        boot_thread = threading.Thread( target = self.THREADBootEverything, name = 'Application Boot Thread' )
        
        boot_thread.start()
        
        self._app.MainLoop()
        
        HydrusData.Print( 'shutting down controller...' )
        
    
    def ShutdownView( self ):
        
        if not HydrusGlobals.emergency_exit:
            
            self.pub( 'splash_set_status_text', 'waiting for daemons to exit' )
            
            self._ShutdownDaemons()
            
            if HydrusGlobals.do_idle_shutdown_work:
                
                self.DoIdleShutdownWork()
                
            
        
        HydrusController.HydrusController.ShutdownView( self )
        
    
    def StartFileQuery( self, query_key, search_context ):
        
        self.CallToThread( self.THREADDoFileQuery, query_key, search_context )
        
    
    def SystemBusy( self ):
        
        if HydrusGlobals.force_idle_mode:
            
            return False
            
        
        max_cpu = self._options[ 'idle_cpu_max' ]
        
        if max_cpu is None:
            
            self._system_busy = False
            
        else:
            
            if HydrusData.TimeHasPassed( self._timestamps[ 'last_cpu_check' ] + 60 ):
                
                cpu_times = psutil.cpu_percent( percpu = True )
                
                if True in ( cpu_time > max_cpu for cpu_time in cpu_times ):
                    
                    self._system_busy = True
                    
                else:
                    
                    self._system_busy = False
                    
                
                self._timestamps[ 'last_cpu_check' ] = HydrusData.GetNow()
                
            
        
        return self._system_busy
        
    
    def ThereIsIdleShutdownWorkDue( self ):
        
        maintenance_due = self.Read( 'maintenance_due' )
        
        if maintenance_due:
            
            return True
            
        
        if not self._options[ 'pause_repo_sync' ]:
            
            services = self.GetServicesManager().GetServices( HC.REPOSITORIES )
            
            for service in services:
                
                if service.CanDownloadUpdate() or service.CanProcessUpdate():
                    
                    return True
                    
                
            
        
        return False
        
    
    def THREADDoFileQuery( self, query_key, search_context ):
        
        query_hash_ids = self.Read( 'file_query_ids', search_context )
        
        media_results = []
        
        for sub_query_hash_ids in HydrusData.SplitListIntoChunks( query_hash_ids, 256 ):
            
            if query_key.IsCancelled(): return
            
            more_media_results = self.Read( 'media_results_from_ids', sub_query_hash_ids )
            
            media_results.extend( more_media_results )
            
            self.pub( 'set_num_query_results', len( media_results ), len( query_hash_ids ) )
            
            self.WaitUntilPubSubsEmpty()
            
        
        search_context.SetComplete()
        
        self.pub( 'file_query_done', query_key, media_results )
        
    
    def THREADBootEverything( self ):
        
        try:
            
            self.CheckAlreadyRunning()
            
            HydrusData.RecordRunningStart( 'client' )
            
            self.InitModel()
            
            self.InitView()
            
        except HydrusExceptions.PermissionException as e:
            
            HydrusData.Print( e )
            
            HydrusGlobals.emergency_exit = True
            
            self.Exit()
            
        except Exception as e:
            
            text = 'A serious error occured while trying to start the program. Its traceback will be shown next. It should have also been written to client.log.'
            
            HydrusData.DebugPrint( text )
            
            traceback.print_exc()
            
            wx.CallAfter( wx.MessageBox, traceback.format_exc() )
            wx.CallAfter( wx.MessageBox, text )
            
            HydrusGlobals.emergency_exit = True
            
            self.Exit()
            
        finally:
            
            self.pub( 'splash_destroy' )
            
        
    
    def THREADExitEverything( self ):
        
        try:
            
            self.pub( 'splash_set_title_text', 'shutting down gui...' )
            
            self.ShutdownView()
            
            self.pub( 'splash_set_title_text', 'shutting down db...' )
            
            self.ShutdownModel()
            
        except HydrusExceptions.PermissionException: pass
        except HydrusExceptions.ShutdownException: pass
        except:
            
            text = 'A serious error occured while trying to exit the program. Its traceback may be shown next. It should have also been written to client.log. You may need to quit the program from task manager.'
            
            HydrusData.DebugPrint( text )
            
            traceback.print_exc()
            
            wx.CallAfter( wx.MessageBox, traceback.format_exc() )
            wx.CallAfter( wx.MessageBox, text )
            
        finally:
            
            self.pub( 'splash_destroy' )
            
        
    
    def Write( self, action, *args, **kwargs ):
        
        if action == 'content_updates': self._managers[ 'undo' ].AddCommand( 'content_updates', *args, **kwargs )
        
        return HydrusController.HydrusController.Write( self, action, *args, **kwargs )
        
    