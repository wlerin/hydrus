import HydrusConstants as HC
import ClientConstants as CC
import ClientData
import ClientCaches
import ClientFiles
import ClientGUICommon
import ClientGUIDialogs
import ClientGUIDialogsManage
import ClientGUIHoverFrames
import ClientMedia
import ClientRatings
import collections
import gc
import HydrusImageHandling
import HydrusPaths
import HydrusTags
import HydrusVideoHandling
import os
import Queue
import random
import shutil
import time
import traceback
import urllib
import wx
import wx.media
import ClientRendering
import HydrusData
import HydrusGlobals

if HC.PLATFORM_WINDOWS: import wx.lib.flashwin

ID_TIMER_VIDEO = wx.NewId()
ID_TIMER_RENDER_WAIT = wx.NewId()
ID_TIMER_ANIMATION_BAR_UPDATE = wx.NewId()
ID_TIMER_SLIDESHOW = wx.NewId()
ID_TIMER_CURSOR_HIDE = wx.NewId()
ID_TIMER_HOVER_SHOW = wx.NewId()

ANIMATED_SCANBAR_HEIGHT = 20
ANIMATED_SCANBAR_CARET_WIDTH = 10

OPEN_EXTERNALLY_BUTTON_SIZE = ( 200, 45 )

def CalculateCanvasMediaSize( media, ( canvas_width, canvas_height ) ):
    
    if ShouldHaveAnimationBar( media ):
        
        canvas_height -= ANIMATED_SCANBAR_HEIGHT
        
    
    if media.GetMime() == HC.APPLICATION_FLASH:
        
        canvas_height -= 10
        canvas_width -= 10
        
    
    return ( canvas_width, canvas_height )
    
def CalculateCanvasFitZoom( media, ( canvas_width, canvas_height ) ):
    
    ( media_width, media_height ) = media.GetResolution()
    
    if media_width == 0 or media_height == 0:
        
        return 1.0
        
    
    ( canvas_width, canvas_height ) = CalculateCanvasMediaSize( media, ( canvas_width, canvas_height ) )
    
    width_zoom = canvas_width / float( media_width )
    
    height_zoom = canvas_height / float( media_height )
    
    canvas_zoom = min( ( width_zoom, height_zoom ) )
    
    return canvas_zoom
    
def CalculateMediaContainerSize( media, zoom ):
    
    action = HC.options[ 'mime_media_viewer_actions' ][ media.GetDisplayMedia().GetMime() ]
    
    if action == CC.MEDIA_VIEWER_DO_NOT_SHOW:
        
        raise Exception( 'This media should not be shown in the media viewer!' )
        
    elif action == CC.MEDIA_VIEWER_SHOW_OPEN_EXTERNALLY_BUTTON:
        
        return OPEN_EXTERNALLY_BUTTON_SIZE
        
    else:
        
        ( media_width, media_height ) = CalculateMediaSize( media, zoom )
        
        if ShouldHaveAnimationBar( media ): media_height += ANIMATED_SCANBAR_HEIGHT
        
        return ( media_width, media_height )
        
    
def CalculateMediaSize( media, zoom ):
    
    ( original_width, original_height ) = media.GetResolution()
    
    media_width = int( round( zoom * original_width ) )
    media_height = int( round( zoom * original_height ) )
    
    return ( media_width, media_height )
    
def ShouldHaveAnimationBar( media ):
    
    is_animated_gif = media.GetMime() == HC.IMAGE_GIF and media.HasDuration()
    
    is_animated_flash = media.GetMime() == HC.APPLICATION_FLASH and media.HasDuration()
    
    is_native_video = media.GetMime() in HC.NATIVE_VIDEO
    
    return is_animated_gif or is_animated_flash or is_native_video
    
class Animation( wx.Window ):
    
    def __init__( self, parent, media, initial_size, initial_position, start_paused ):
        
        wx.Window.__init__( self, parent, size = initial_size, pos = initial_position )
        
        self.SetDoubleBuffered( True )
        
        ( initial_width, initial_height ) = initial_size
        
        self._media = media
        self._video_container = ClientRendering.RasterContainerVideo( self._media, initial_size )
        
        self._animation_bar = None
        
        self._drag_happened = False
        self._left_down_event = None
        
        self._a_frame_has_been_drawn = False
        self._has_played_once_through = False
        
        self._num_frames = self._media.GetNumFrames()
        
        self._current_frame_index = int( ( self._num_frames - 1 ) * HC.options[ 'animation_start_position' ] )
        self._current_frame_drawn = False
        self._current_frame_drawn_at = 0.0
        self._next_frame_due_at = 0.0
        
        self._paused = start_paused
        
        self._canvas_bmp = wx.EmptyBitmap( initial_width, initial_height, 24 )
        
        self._timer_video = wx.Timer( self, id = ID_TIMER_VIDEO )
        
        self.Bind( wx.EVT_PAINT, self.EventPaint )
        self.Bind( wx.EVT_SIZE, self.EventResize )
        self.Bind( wx.EVT_TIMER, self.TIMEREventVideo, id = ID_TIMER_VIDEO )
        self.Bind( wx.EVT_MOUSE_EVENTS, self.EventPropagateMouse )
        self.Bind( wx.EVT_KEY_UP, self.EventPropagateKey )
        self.Bind( wx.EVT_ERASE_BACKGROUND, self.EventEraseBackground )
        
        self._timer_video.Start( 5, wx.TIMER_CONTINUOUS )
        
        self.Refresh()
        
    
    def __del__( self ):
        
        wx.CallLater( 500, gc.collect )
        
    
    def _DrawFrame( self, dc ):
        
        current_frame = self._video_container.GetFrame( self._current_frame_index )
        
        ( my_width, my_height ) = self._canvas_bmp.GetSize()
        
        ( frame_width, frame_height ) = current_frame.GetSize()
        
        x_scale = my_width / float( frame_width )
        y_scale = my_height / float( frame_height )
        
        dc.SetUserScale( x_scale, y_scale )
        
        wx_bmp = current_frame.GetWxBitmap()
        
        dc.DrawBitmap( wx_bmp, 0, 0 )
        
        wx.CallAfter( wx_bmp.Destroy )
        
        dc.SetUserScale( 1.0, 1.0 )
        
        if self._animation_bar is not None:
            
            self._animation_bar.GotoFrame( self._current_frame_index )
            
        
        self._current_frame_drawn = True
        
        next_frame_time_s = self._video_container.GetDuration( self._current_frame_index ) / 1000.0
        
        if HydrusData.TimeHasPassedPrecise( self._next_frame_due_at + next_frame_time_s ):
            
            # we are rendering slower than the animation demands, so we'll slow down
            # this also initialises self._next_frame_due_at
            
            self._current_frame_drawn_at = HydrusData.GetNowPrecise()
            
        else:
            
            # to make timings more accurate and keep frame throughput accurate, let's pretend we drew this at the right time
            
            self._current_frame_drawn_at = self._next_frame_due_at
            
        
        self._next_frame_due_at = self._current_frame_drawn_at + next_frame_time_s
        
        self._a_frame_has_been_drawn = True
        
    
    def _DrawWhite( self, dc ):
        
        dc.SetBackground( wx.Brush( wx.Colour( *HC.options[ 'gui_colours' ][ 'media_background' ] ) ) )
        
        dc.Clear()
        
    
    def _TellAnimationBarAboutPausedStatus( self ):
        
        if self._animation_bar is not None:
            
            self._animation_bar.SetPaused( self._paused )
            
        
    
    def CurrentFrame( self ): return self._current_frame_index
    
    def EventEraseBackground( self, event ): pass
    
    def EventPaint( self, event ):
        
        dc = wx.BufferedPaintDC( self, self._canvas_bmp )
        
        if not self._current_frame_drawn and self._video_container.HasFrame( self._current_frame_index ):
            
            self._DrawFrame( dc )
            
        elif not self._a_frame_has_been_drawn:
            
            self._DrawWhite( dc )
            
        
    
    def EventPropagateKey( self, event ):
        
        event.ResumePropagation( 1 )
        event.Skip()
        
    
    def EventPropagateMouse( self, event ):
        
        if self._animation_bar is not None:
            
            etype = event.GetEventType()
            
            if not ( event.ShiftDown() or event.CmdDown() or event.AltDown() ):
                
                if etype == wx.wxEVT_LEFT_DOWN:
                    
                    self.PausePlay()
                    
                    self.GetParent().BeginDrag()
                    
                    return
                    
                
            
        
        screen_position = self.ClientToScreen( event.GetPosition() )
        ( x, y ) = self.GetParent().ScreenToClient( screen_position )
        
        event.SetX( x )
        event.SetY( y )
        
        event.ResumePropagation( 1 )
        event.Skip()
        
    
    def EventResize( self, event ):
        
        ( my_width, my_height ) = self.GetClientSize()
        
        ( current_bmp_width, current_bmp_height ) = self._canvas_bmp.GetSize()
        
        if my_width != current_bmp_width or my_height != current_bmp_height:
            
            if my_width > 0 and my_height > 0:
                
                ( image_width, image_height ) = self._video_container.GetSize()
                
                we_just_zoomed_in = my_width > image_width
                
                if we_just_zoomed_in and self._video_container.IsScaled():
                    
                    full_resolution = self._video_container.GetResolution()
                    
                    self._video_container = ClientRendering.RasterContainerVideo( self._media, full_resolution )
                    
                
                self._video_container.SetFramePosition( self._current_frame_index )
                
                self._current_frame_drawn = False
                self._a_frame_has_been_drawn = False
                
                wx.CallAfter( self._canvas_bmp.Destroy )
                
                self._canvas_bmp = wx.EmptyBitmap( my_width, my_height, 24 )
                
                self.Refresh()
                
            
        
    
    def GotoFrame( self, frame_index ):
        
        if frame_index != self._current_frame_index:
            
            self._current_frame_index = frame_index
            
            self._video_container.SetFramePosition( self._current_frame_index )
            
            self._current_frame_drawn_at = 0.0
            self._current_frame_drawn = False
            
            self.Refresh()
            
        
        self._paused = True
        
        self._TellAnimationBarAboutPausedStatus()
        
    
    def HasPlayedOnceThrough( self ):
        
        return self._has_played_once_through
        
    
    def IsPlaying( self ):
        
        return not self._paused
        
    
    def Play( self ):
        
        self._paused = False
        
        self._TellAnimationBarAboutPausedStatus()
        
    
    def Pause( self ):
        
        self._paused = True
        
        self._TellAnimationBarAboutPausedStatus()
        
    
    def PausePlay( self ):
        
        self._paused = not self._paused
        
        self._TellAnimationBarAboutPausedStatus()
        
    
    def SetAnimationBar( self, animation_bar ):
        
        self._animation_bar = animation_bar
        
        if self._animation_bar is not None:
            
            self._animation_bar.GotoFrame( self._current_frame_index )
            
            self._TellAnimationBarAboutPausedStatus()
            
        
    
    def TIMEREventVideo( self, event ):
        
        try:
            
            if self.IsShownOnScreen():
                
                if self._current_frame_drawn:
                    
                    if not self._paused and HydrusData.TimeHasPassedPrecise( self._next_frame_due_at ):
                        
                        num_frames = self._media.GetNumFrames()
                        
                        self._current_frame_index = ( self._current_frame_index + 1 ) % num_frames
                        
                        if self._current_frame_index == 0:
                            
                            self._has_played_once_through = True
                            
                        
                        self._current_frame_drawn = False
                        
                        self._video_container.SetFramePosition( self._current_frame_index )
                        
                    
                
                if not self._current_frame_drawn and self._video_container.HasFrame( self._current_frame_index ):
                    
                    self.Refresh()
                    
                
            
        except wx.PyDeadObjectError:
            
            self._timer_video.Stop()
            
        except:
            
            self._timer_video.Stop()
            
            raise
            
        
    
class AnimationBar( wx.Window ):
    
    def __init__( self, parent, media, media_window ):
        
        ( parent_width, parent_height ) = parent.GetClientSize()
        
        wx.Window.__init__( self, parent, size = ( parent_width, ANIMATED_SCANBAR_HEIGHT ), pos = ( 0, parent_height - ANIMATED_SCANBAR_HEIGHT ) )
        
        self._dirty = True
        
        self._canvas_bmp = wx.EmptyBitmap( parent_width, ANIMATED_SCANBAR_HEIGHT, 24 )
        
        self.SetCursor( wx.StockCursor( wx.CURSOR_ARROW ) )
        
        self._paused = True
        self._media = media
        self._media_window = media_window
        self._num_frames = self._media.GetNumFrames()
        self._current_frame_index = 0
        
        self._currently_in_a_drag = False
        self._it_was_playing = False
        
        self.Bind( wx.EVT_MOUSE_EVENTS, self.EventMouse )
        self.Bind( wx.EVT_TIMER, self.TIMEREventUpdate, id = ID_TIMER_ANIMATION_BAR_UPDATE )
        self.Bind( wx.EVT_PAINT, self.EventPaint )
        self.Bind( wx.EVT_SIZE, self.EventResize )
        self.Bind( wx.EVT_ERASE_BACKGROUND, self.EventEraseBackground )
        
        self._timer_update = wx.Timer( self, id = ID_TIMER_ANIMATION_BAR_UPDATE )
        self._timer_update.Start( 100, wx.TIMER_CONTINUOUS )
        
    
    def _Redraw( self, dc ):
        
        ( my_width, my_height ) = self._canvas_bmp.GetSize()
        
        dc.SetPen( wx.TRANSPARENT_PEN )
        
        background_colour = wx.SystemSettings.GetColour( wx.SYS_COLOUR_BTNFACE )
        
        if self._paused:
            
            ( r, g, b ) = background_colour.Get()
            
            r = int( r * 0.85 )
            g = int( g * 0.85 )
            b = int( b * 0.85 )
            
            background_colour = wx.Colour( r, g, b )
            
        
        dc.SetBackground( wx.Brush( background_colour ) )
        
        dc.Clear()
        
        #
        
        dc.SetBrush( wx.Brush( wx.SystemSettings.GetColour( wx.SYS_COLOUR_BTNSHADOW ) ) )
        
        dc.DrawRectangle( int( float( my_width - ANIMATED_SCANBAR_CARET_WIDTH ) * float( self._current_frame_index ) / float( self._num_frames - 1 ) ), 0, ANIMATED_SCANBAR_CARET_WIDTH, ANIMATED_SCANBAR_HEIGHT )
        
        #
        
        dc.SetFont( wx.SystemSettings.GetFont( wx.SYS_DEFAULT_GUI_FONT ) )
        
        dc.SetTextForeground( wx.BLACK )
        
        s = HydrusData.ConvertValueRangeToPrettyString( self._current_frame_index + 1, self._num_frames )
        
        ( x, y ) = dc.GetTextExtent( s )
        
        dc.DrawText( s, my_width - x - 3, 3 )
        
        self._dirty = False
        
    
    def EventEraseBackground( self, event ): pass
    
    def EventMouse( self, event ):
        
        CC.CAN_HIDE_MOUSE = False
        
        ( my_width, my_height ) = self.GetClientSize()
        
        if event.Dragging(): self._currently_in_a_drag = True
        
        if event.ButtonIsDown( wx.MOUSE_BTN_ANY ):
            
            if not self._currently_in_a_drag:
                
                self._it_was_playing = self._media_window.IsPlaying()
                
            
            ( x, y ) = event.GetPosition()
            
            compensated_x_position = x - ( ANIMATED_SCANBAR_CARET_WIDTH / 2 )
            
            proportion = float( compensated_x_position ) / float( my_width - ANIMATED_SCANBAR_CARET_WIDTH )
            
            if proportion < 0: proportion = 0
            if proportion > 1: proportion = 1
            
            self._current_frame_index = int( proportion * ( self._num_frames - 1 ) + 0.5 )
            
            self._dirty = True
            
            self.Refresh()
            
            self._media_window.GotoFrame( self._current_frame_index )
            
        elif event.ButtonUp( wx.MOUSE_BTN_ANY ):
            
            if self._it_was_playing:
                
                self._media_window.Play()
                
            
            self._currently_in_a_drag = False
            
        
    
    def EventPaint( self, event ):
        
        dc = wx.BufferedPaintDC( self, self._canvas_bmp )
        
        if self._dirty:
            
            self._Redraw( dc )
            
        
    
    def EventResize( self, event ):
        
        ( my_width, my_height ) = self.GetClientSize()
        
        ( current_bmp_width, current_bmp_height ) = self._canvas_bmp.GetSize()
        
        if my_width != current_bmp_width or my_height != current_bmp_height:
            
            if my_width > 0 and my_height > 0:
                
                wx.CallAfter( self._canvas_bmp.Destroy )
                
                self._canvas_bmp = wx.EmptyBitmap( my_width, my_height, 24 )
                
                self._dirty = True
                
                self.Refresh()
                
            
        
    
    def GotoFrame( self, frame_index ):
        
        self._current_frame_index = frame_index
        
        self._dirty = True
        
        self.Refresh()
        
    
    def SetPaused( self, paused ):
        
        self._paused = paused
        
        self._dirty = True
        
        self.Refresh()
        
    
    def TIMEREventUpdate( self, event ):
        
        try:
            
            if self.IsShownOnScreen():
                
                if self._media.GetMime() == HC.APPLICATION_FLASH:
                    
                    try:
                        
                        frame_index = self._media_window.CurrentFrame()
                        
                    except AttributeError:
                        
                        text = 'The flash window produced an unusual error that probably means it never initialised properly. This is usually because Flash has not been installed for Internet Explorer. '
                        text += os.linesep * 2
                        text += 'Please close the client, open Internet Explorer, and install flash from Adobe\'s site and then try again. If that does not work, please tell the hydrus developer.'
                        
                        HydrusData.ShowText( text )
                        
                        self._timer_update.Stop()
                        
                        raise
                        
                    
                    if frame_index != self._current_frame_index:
                        
                        self._current_frame_index = frame_index
                        
                        self._dirty = True
                        
                        self.Refresh()
                        
                    
                
            
        except wx.PyDeadObjectError:
            
            self._timer_update.Stop()
            
        except:
            
            self._timer_update.Stop()
            
            raise
            
        
    
class Canvas( wx.Window ):
    
    BORDER = wx.SIMPLE_BORDER
    
    def __init__( self, parent, image_cache, claim_focus = True ):
        
        wx.Window.__init__( self, parent, style = self.BORDER )
        
        self._file_service_key = CC.LOCAL_FILE_SERVICE_KEY
        self._image_cache = image_cache
        self._claim_focus = claim_focus
        
        self._canvas_key = HydrusData.GenerateKey()
        
        self._dirty = True
        self._closing = False
        
        self._service_keys_to_services = {}
        
        self._focus_holder = wx.Window( self )
        self._focus_holder.Hide()
        self._focus_holder.SetEventHandler( self )
        
        self._current_media = None
        self._current_display_media = None
        self._media_container = None
        self._current_zoom = 1.0
        self._canvas_zoom = 1.0
        
        self._last_drag_coordinates = None
        self._last_motion_coordinates = ( 0, 0 )
        self._total_drag_delta = ( 0, 0 )
        
        self.SetBackgroundColour( wx.Colour( *HC.options[ 'gui_colours' ][ 'media_background' ] ) )
        
        self._canvas_bmp = wx.EmptyBitmap( 20, 20, 24 )
        
        self.Bind( wx.EVT_SIZE, self.EventResize )
        
        self.Bind( wx.EVT_PAINT, self.EventPaint )
        self.Bind( wx.EVT_ERASE_BACKGROUND, self.EventEraseBackground )
        
        HydrusGlobals.client_controller.sub( self, 'ZoomIn', 'canvas_zoom_in' )
        HydrusGlobals.client_controller.sub( self, 'ZoomOut', 'canvas_zoom_out' )
        HydrusGlobals.client_controller.sub( self, 'ZoomSwitch', 'canvas_zoom_switch' )
        HydrusGlobals.client_controller.sub( self, 'OpenExternally', 'canvas_open_externally' )
        HydrusGlobals.client_controller.sub( self, 'ManageTags', 'canvas_manage_tags' )
        
    
    def _Archive( self ): HydrusGlobals.client_controller.Write( 'content_updates', { CC.LOCAL_FILE_SERVICE_KEY : [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_ARCHIVE, ( self._current_display_media.GetHash(), ) ) ] } )
    
    def _CopyBMPToClipboard( self ):
        
        HydrusGlobals.client_controller.pub( 'clipboard', 'bmp', self._current_display_media )
        
    
    def _CopyHashToClipboard( self, hash_type ):
        
        sha256_hash = self._current_display_media.GetHash()
        
        if hash_type == 'sha256':
            
            hex_hash = sha256_hash.encode( 'hex' )
            
        else:
            
            if self._current_display_media.GetLocationsManager().HasLocal():
                
                ( other_hash, ) = HydrusGlobals.client_controller.Read( 'file_hashes', ( sha256_hash, ), 'sha256', hash_type )
                
                hex_hash = other_hash.encode( 'hex' )
                
            else:
                
                wx.MessageBox( 'Unfortunately, you do not have that file in your database, so its non-sha256 hashes are unknown.' )
                
                return
                
            
        
        HydrusGlobals.client_controller.pub( 'clipboard', 'text', hex_hash )
        
    
    def _CopyLocalUrlToClipboard( self ):
        
        local_url = 'http://127.0.0.1:' + str( HC.options[ 'local_port' ] ) + '/file?hash=' + self._current_display_media.GetHash().encode( 'hex' )
        
        HydrusGlobals.client_controller.pub( 'clipboard', 'text', local_url )
        
    
    def _CopyPathToClipboard( self ):
        
        client_files_manager = HydrusGlobals.client_controller.GetClientFilesManager()
        
        path = client_files_manager.GetFilePath( self._current_display_media.GetHash(), self._current_display_media.GetMime() )
        
        HydrusGlobals.client_controller.pub( 'clipboard', 'text', path )
        
    
    def _Delete( self, service_key = None ):
        
        do_it = False
        
        if service_key is None:
            
            locations_manager = self._current_display_media.GetLocationsManager()
            
            if CC.LOCAL_FILE_SERVICE_KEY in locations_manager.GetCurrent():
                
                service_key = CC.LOCAL_FILE_SERVICE_KEY
                
            elif CC.TRASH_SERVICE_KEY in locations_manager.GetCurrent():
                
                service_key = CC.TRASH_SERVICE_KEY
                
            else:
                
                return
                
            
        
        if service_key == CC.LOCAL_FILE_SERVICE_KEY:
            
            if not HC.options[ 'confirm_trash' ]:
                
                do_it = True
                
            
            text = 'Send this file to the trash?'
            
        elif service_key == CC.TRASH_SERVICE_KEY:
            
            text = 'Permanently delete this file?'
            
        
        if not do_it:
            
            with ClientGUIDialogs.DialogYesNo( self, text ) as dlg:
                
                if dlg.ShowModal() == wx.ID_YES:
                    
                    do_it = True
                    
                
            
            
            self.SetFocus() # annoying bug because of the modal dialog
            
        
        if do_it:
            
            hashes = { self._current_display_media.GetHash() }
            
            HydrusGlobals.client_controller.Write( 'content_updates', { service_key : [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_DELETE, hashes ) ] } )
            
        
    
    def _DrawBackgroundBitmap( self, dc ):
        
        dc.SetBackground( wx.Brush( wx.Colour( *HC.options[ 'gui_colours' ][ 'media_background' ] ) ) )
        
        dc.Clear()
        
        self._DrawBackgroundDetails( dc )
        
        self._dirty = False
        
    
    def _DrawBackgroundDetails( self, dc ): pass
    
    def _DrawCurrentMedia( self ):
        
        ( my_width, my_height ) = self.GetClientSize()
        
        if my_width > 0 and my_height > 0:
            
            if self._current_media is not None: self._SizeAndPositionMediaContainer()
            
        
    
    def _GetIndexString( self ): return ''
    
    def _GetMediaContainerSizeAndPosition( self ):
        
        ( my_width, my_height ) = self.GetClientSize()
        
        ( media_width, media_height ) = CalculateMediaContainerSize( self._current_display_media, self._current_zoom )
        
        ( drag_x, drag_y ) = self._total_drag_delta
        
        x_offset = ( my_width - media_width ) / 2 + drag_x
        y_offset = ( my_height - media_height ) / 2 + drag_y
        
        new_size = ( media_width, media_height )
        new_position = ( x_offset, y_offset )
        
        return ( new_size, new_position )
        
    
    def _HydrusShouldNotProcessInput( self ):
        
        if self._current_display_media.GetMime() == HC.APPLICATION_FLASH:
            
            if self.MouseIsOverMedia(): return True
            
        
        return False
        
    
    def _Inbox( self ): HydrusGlobals.client_controller.Write( 'content_updates', { CC.LOCAL_FILE_SERVICE_KEY : [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_INBOX, ( self._current_display_media.GetHash(), ) ) ] } )
    
    def _IsZoomable( self ):
        
        return HC.options[ 'mime_media_viewer_actions' ][ self._current_display_media.GetMime() ] != CC.MEDIA_VIEWER_SHOW_OPEN_EXTERNALLY_BUTTON
        
    
    def _ManageRatings( self ):
    
        if len( HydrusGlobals.client_controller.GetServicesManager().GetServices( HC.RATINGS_SERVICES ) ) > 0:
            
            if self._current_media is not None:
                
                with ClientGUIDialogsManage.DialogManageRatings( self, ( self._current_display_media, ) ) as dlg: dlg.ShowModal()
                
            
        
    
    def _ManageTags( self ):
        
        if self._current_display_media is not None:
            
            with ClientGUIDialogsManage.DialogManageTags( self, self._file_service_key, ( self._current_display_media, ), canvas_key = self._canvas_key ) as dlg:
                
                dlg.ShowModal()
                
            
        
    
    def _OpenExternally( self ):
        
        if self._current_display_media is not None:
            
            hash = self._current_display_media.GetHash()
            mime = self._current_display_media.GetMime()
            
            client_files_manager = HydrusGlobals.client_controller.GetClientFilesManager()
            
            path = client_files_manager.GetFilePath( hash, mime )
            
            HydrusPaths.LaunchFile( path )
            
            if self._current_display_media.HasDuration() and mime != HC.APPLICATION_FLASH:
                
                self._media_container.Pause()
                
            
        
    
    def _PrefetchNeighbours( self ): pass
    
    def _RecalcZoom( self ):
        
        if self._current_display_media is None:
            
            self._current_zoom = 1.0
            
        else:
            
            ( my_width, my_height ) = self.GetClientSize()
            
            ( media_width, media_height ) = self._current_display_media.GetResolution()
            
            ( canvas_media_width, canvas_media_height ) = CalculateCanvasMediaSize( self._current_display_media, ( my_width, my_height ) )
            
            media_needs_to_be_scaled_down = media_width > canvas_media_width or media_height > canvas_media_height
            media_needs_to_be_scaled_up = media_width < canvas_media_width and media_height < canvas_media_height and HC.options[ 'fit_to_canvas' ]
            
            self._canvas_zoom = CalculateCanvasFitZoom( self._current_display_media, ( my_width, my_height ) )
            
            if media_needs_to_be_scaled_down or media_needs_to_be_scaled_up:
                
                self._current_zoom = self._canvas_zoom
                
            else:
                
                self._current_zoom = 1.0
                
            
        
        HydrusGlobals.client_controller.pub( 'canvas_new_zoom', self._canvas_key, self._current_zoom )
        
    
    def _SetDirty( self ):
        
        self._dirty = True
        
        self.Refresh()
        
    
    def _SizeAndPositionMediaContainer( self ):
        
        ( new_size, new_position ) = self._GetMediaContainerSizeAndPosition()
        
        if new_size != self._media_container.GetSize(): self._media_container.SetSize( new_size )
        
        if HC.PLATFORM_OSX and new_position == self._media_container.GetPosition(): self._media_container.Refresh()
        
        if new_position != self._media_container.GetPosition(): self._media_container.SetPosition( new_position )
        
    
    def _Undelete( self ):
        
        locations_manager = self._current_display_media.GetLocationsManager()
        
        if CC.TRASH_SERVICE_KEY in locations_manager.GetCurrent():
            
            do_it = False
            
            if not HC.options[ 'confirm_trash' ]:
                
                do_it = True
                
            else:
                
                with ClientGUIDialogs.DialogYesNo( self, 'Undelete this file?' ) as dlg:
                    
                    if dlg.ShowModal() == wx.ID_YES:
                        
                        do_it = True
                        
                    
                
            
            if do_it:
                
                HydrusGlobals.client_controller.Write( 'content_updates', { CC.TRASH_SERVICE_KEY : [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_UNDELETE, ( self._current_display_media.GetHash(), ) ) ] } )
                
            
            self.SetFocus() # annoying bug because of the modal dialog
            
        
    
    def _ZoomIn( self ):
        
        if self._current_display_media is not None and self._IsZoomable():
            
            my_zoomins = list( CC.ZOOMS )
            
            if self._canvas_zoom not in my_zoomins:
                
                my_zoomins.append( self._canvas_zoom )
                
                my_zoomins.sort()
                
            
            for zoom in my_zoomins:
                
                if zoom > self._current_zoom:
                    
                    if self._current_display_media.GetMime() == HC.APPLICATION_FLASH:
                        
                        # we want to preserve whitespace around flash
                        
                        ( my_width, my_height ) = self.GetClientSize()
                        
                        ( new_media_width, new_media_height ) = CalculateMediaContainerSize( self._current_display_media, zoom )
                        
                        if new_media_width >= my_width or new_media_height >= my_height: return
                        
                    
                    ( drag_x, drag_y ) = self._total_drag_delta
                    
                    zoom_ratio = zoom / self._current_zoom
                    
                    self._total_drag_delta = ( int( drag_x * zoom_ratio ), int( drag_y * zoom_ratio ) )
                    
                    self._current_zoom = zoom
                    
                    HydrusGlobals.client_controller.pub( 'canvas_new_zoom', self._canvas_key, self._current_zoom )
                    
                    self._SetDirty()
                    
                    break
                    
                
            
        
    
    def _ZoomOut( self ):
        
        if self._current_display_media is not None and self._IsZoomable():
            
            my_zoomouts = list( CC.ZOOMS )
            
            if self._canvas_zoom not in my_zoomouts:
                
                my_zoomouts.append( self._canvas_zoom )
                
            
            my_zoomouts.sort( reverse = True )
            
            for zoom in my_zoomouts:
                
                if zoom < self._current_zoom:
                    
                    ( drag_x, drag_y ) = self._total_drag_delta
                    
                    zoom_ratio = zoom / self._current_zoom
                    
                    self._total_drag_delta = ( int( drag_x * zoom_ratio ), int( drag_y * zoom_ratio ) )
                    
                    self._current_zoom = zoom
                    
                    HydrusGlobals.client_controller.pub( 'canvas_new_zoom', self._canvas_key, self._current_zoom )
                    
                    self._SetDirty()
                    
                    break
                    
                
            
        
    
    def _ZoomSwitch( self ):
        
        if self._current_display_media is not None and self._IsZoomable():
            
            ( my_width, my_height ) = self.GetClientSize()
            
            ( media_width, media_height ) = self._current_display_media.GetResolution()
            
            if self._current_display_media.GetMime() != HC.APPLICATION_FLASH:
                
                if self._current_zoom == 1.0: new_zoom = self._canvas_zoom
                else: new_zoom = 1.0
                
                if new_zoom != self._current_zoom:
                    
                    ( drag_x, drag_y ) = self._total_drag_delta
                    
                    zoom_ratio = new_zoom / self._current_zoom
                    
                    self._total_drag_delta = ( int( drag_x * zoom_ratio ), int( drag_y * zoom_ratio ) )
                    
                    self._current_zoom = new_zoom
                    
                    HydrusGlobals.client_controller.pub( 'canvas_new_zoom', self._canvas_key, self._current_zoom )
                    
                    self._SetDirty()
                    
                
            
        
    
    def BeginDrag( self, pos = None ):
        
        if pos is None:
            
            ( x, y ) = self.ScreenToClient( wx.GetMousePosition() )
            
        else:
            
            ( x, y ) = pos
            
        
        self._last_drag_coordinates = ( x, y )
        
        
    
    def EventEraseBackground( self, event ): pass
    
    def EventPaint( self, event ):
        
        dc = wx.BufferedPaintDC( self, self._canvas_bmp )
        
        if self._dirty:
            
            self._DrawBackgroundBitmap( dc )
            
            if self._media_container is not None:
                
                self._DrawCurrentMedia()
                
            
        
    
    def EventResize( self, event ):
        
        if not self._closing:
            
            ( my_width, my_height ) = self.GetClientSize()
            
            wx.CallAfter( self._canvas_bmp.Destroy )
            
            self._canvas_bmp = wx.EmptyBitmap( my_width, my_height, 24 )
            
            if self._media_container is not None:
                
                ( media_width, media_height ) = self._media_container.GetClientSize()
                
                if my_width != media_width or my_height != media_height:
                    
                    self._RecalcZoom()
                    
                
            
            self._SetDirty()
            
        
        event.Skip()
        
    
    def KeepCursorAlive( self ): pass
    
    def ManageTags( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._ManageTags()
            
        
    
    def MouseIsNearAnimationBar( self ):
        
        if self._media_container is None:
            
            return False
            
        else:
            
            return self._media_container.MouseIsNearAnimationBar()
            
        
    
    def MouseIsOverMedia( self ):
        
        ( x, y ) = self._media_container.GetScreenPosition()
        ( width, height ) = self._media_container.GetSize()
        
        ( mouse_x, mouse_y ) = wx.GetMousePosition()
        
        if mouse_x >= x and mouse_x <= x + width and mouse_y >= y and mouse_y <= y + height: return True
        
        return False
        
    
    def OpenExternally( self, canvas_key ):
        
        if self._canvas_key == canvas_key:
            
            self._OpenExternally()
            
        
    
    def SetMedia( self, media ):
        
        if media is not None:
            
            locations_manager = media.GetLocationsManager()
            
            if not locations_manager.HasLocal():
                
                media = None
                
            elif HC.options[ 'mime_media_viewer_actions' ][ media.GetDisplayMedia().GetMime() ] == CC.MEDIA_VIEWER_DO_NOT_SHOW:
                
                media = None
                
            
        
        if media != self._current_media:
            
            HydrusGlobals.client_controller.ResetIdleTimer()
            
            self._current_media = media
            self._current_display_media = None
            self._total_drag_delta = ( 0, 0 )
            self._last_drag_coordinates = None
            
            if self._media_container is not None:
                
                self._media_container.Hide()
                
                wx.CallAfter( self._media_container.Destroy )
                
                self._media_container = None
                
            
            if self._current_media is not None:
                
                self._current_display_media = self._current_media.GetDisplayMedia()
                
                self._RecalcZoom()
                
                ( initial_size, initial_position ) = self._GetMediaContainerSizeAndPosition()
                
                ( initial_width, initial_height ) = initial_size
                
                if self._current_display_media.GetLocationsManager().HasLocal() and initial_width > 0 and initial_height > 0:
                    
                    self._media_container = MediaContainer( self, self._image_cache, self._current_display_media, initial_size, initial_position )
                    
                    if self._claim_focus: self._media_container.SetFocus()
                    
                    self._PrefetchNeighbours()
                    
                else:
                    
                    self._current_media = None
                    
                
            
            HydrusGlobals.client_controller.pub( 'canvas_new_display_media', self._canvas_key, self._current_display_media )
            
            HydrusGlobals.client_controller.pub( 'canvas_new_index_string', self._canvas_key, self._GetIndexString() )
            
            self._SetDirty()
            
        
    
    def ZoomIn( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._ZoomIn()
            
        
    
    def ZoomOut( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._ZoomOut()
            
        
    
    def ZoomSwitch( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._ZoomSwitch()
            
        
    
class CanvasWithDetails( Canvas ):
    
    BORDER = wx.NO_BORDER
    
    def __init__( self, parent, image_cache ):
        
        Canvas.__init__( self, parent, image_cache )
        
        self._hover_commands = ClientGUIHoverFrames.FullscreenHoverFrameCommands( self, self._canvas_key )
        self._hover_tags = ClientGUIHoverFrames.FullscreenHoverFrameTags( self, self._canvas_key )
        
        ratings_services = HydrusGlobals.client_controller.GetServicesManager().GetServices( ( HC.RATINGS_SERVICES ) )
        
        if len( ratings_services ) > 0:
            
            self._hover_ratings = ClientGUIHoverFrames.FullscreenHoverFrameRatings( self, self._canvas_key )
            
        
    
    def _DrawBackgroundDetails( self, dc ):
        
        if self._current_media is not None:
            
            ( client_width, client_height ) = self.GetClientSize()
            
            # tags on the top left
            
            dc.SetFont( wx.SystemSettings.GetFont( wx.SYS_DEFAULT_GUI_FONT ) )
            
            tags_manager = self._current_media.GetDisplayMedia().GetTagsManager()
            
            siblings_manager = HydrusGlobals.client_controller.GetManager( 'tag_siblings' )
            
            current = siblings_manager.CollapseTags( tags_manager.GetCurrent() )
            pending = siblings_manager.CollapseTags( tags_manager.GetPending() )
            petitioned = siblings_manager.CollapseTags( tags_manager.GetPetitioned() )
            
            tags_i_want_to_display = set()
            
            tags_i_want_to_display.update( current )
            tags_i_want_to_display.update( pending )
            tags_i_want_to_display.update( petitioned )
            
            tags_i_want_to_display = list( tags_i_want_to_display )
            
            ClientData.SortTagsList( tags_i_want_to_display, HC.options[ 'default_tag_sort' ] )
            
            current_y = 3
            
            namespace_colours = HC.options[ 'namespace_colours' ]
            
            for tag in tags_i_want_to_display:
                
                display_string = HydrusTags.RenderTag( tag )
                
                if tag in pending:
                    
                    display_string += ' (+)'
                    
                
                if tag in petitioned:
                    
                    display_string += ' (-)'
                    
                
                if ':' in tag:
                    
                    ( namespace, sub_tag ) = tag.split( ':', 1 )
                    
                    if namespace in namespace_colours: ( r, g, b ) = namespace_colours[ namespace ]
                    else: ( r, g, b ) = namespace_colours[ None ]
                    
                else:
                    
                    ( r, g, b ) = namespace_colours[ '' ]
                    
                
                dc.SetTextForeground( wx.Colour( r, g, b ) )
                
                ( x, y ) = dc.GetTextExtent( display_string )
                
                dc.DrawText( display_string, 5, current_y )
                
                current_y += y
                
            
            dc.SetTextForeground( wx.Colour( *HC.options[ 'gui_colours' ][ 'media_text' ] ) )
            
            # top right
            
            current_y = 2
            
            # icons
            
            icons_to_show = []
            
            if CC.TRASH_SERVICE_KEY in self._current_media.GetLocationsManager().GetCurrent():
                
                icons_to_show.append( CC.GlobalBMPs.trash )
                
            
            if self._current_media.HasInbox():
                
                icons_to_show.append( CC.GlobalBMPs.inbox )
                
            
            if len( icons_to_show ) > 0:
                
                icon_x = 0
                
                for icon in icons_to_show:
                    
                    dc.DrawBitmap( icon, client_width + icon_x - 18, 2 )
                    
                    icon_x -= 18
                    
                
                current_y += 18
                
            
            # repo strings
            
            remote_strings = self._current_media.GetLocationsManager().GetRemoteLocationStrings()
            
            for remote_string in remote_strings:
                
                ( text_width, text_height ) = dc.GetTextExtent( remote_string )
                
                dc.DrawText( remote_string, client_width - text_width - 3, current_y )
                
                current_y += text_height + 4
                
            
            # ratings
            
            ( local_ratings, remote_ratings ) = self._current_display_media.GetRatings()
            
            services_manager = HydrusGlobals.client_controller.GetServicesManager()
            
            like_services = services_manager.GetServices( ( HC.LOCAL_RATING_LIKE, ), randomised = False )
            
            like_services.reverse()
            
            like_rating_current_x = client_width - 16
            
            for like_service in like_services:
                
                service_key = like_service.GetServiceKey()
                
                rating_state = ClientRatings.GetLikeStateFromMedia( ( self._current_display_media, ), service_key )
                
                ClientRatings.DrawLike( dc, like_rating_current_x, current_y, service_key, rating_state )
                
                like_rating_current_x -= 16
                
            
            if len( like_services ) > 0: current_y += 20
            
            
            numerical_services = services_manager.GetServices( ( HC.LOCAL_RATING_NUMERICAL, ), randomised = False )
            
            for numerical_service in numerical_services:
                
                service_key = numerical_service.GetServiceKey()
                
                ( rating_state, rating ) = ClientRatings.GetNumericalStateFromMedia( ( self._current_display_media, ), service_key )
                
                numerical_width = ClientRatings.GetNumericalWidth( service_key )
                
                ClientRatings.DrawNumerical( dc, client_width - numerical_width, current_y, service_key, rating_state, rating )
                
                current_y += 20
                
            
            # middle
            
            current_y = 3
            
            title_string = self._current_display_media.GetTitleString()
            
            if len( title_string ) > 0:
                
                ( x, y ) = dc.GetTextExtent( title_string )
                
                dc.DrawText( title_string, ( client_width - x ) / 2, current_y )
                
                current_y += y + 3
                
            
            info_string = self._GetInfoString()
            
            ( x, y ) = dc.GetTextExtent( info_string )
            
            dc.DrawText( info_string, ( client_width - x ) / 2, current_y )
            
            index_string = self._GetIndexString()
            
            if len( index_string ) > 0:
                
                ( x, y ) = dc.GetTextExtent( index_string )
                
                dc.DrawText( index_string, client_width - x - 3, client_height - y - 3 )
                
            
        
    
    def _GetInfoString( self ):
        
        lines = self._current_display_media.GetPrettyInfoLines()
        
        lines.insert( 1, ClientData.ConvertZoomToPercentage( self._current_zoom ) )
        
        info_string = ' | '.join( lines )
        
        return info_string
        
    
class CanvasPanel( Canvas ):
    
    def __init__( self, parent, page_key ):
        
        Canvas.__init__( self, parent, HydrusGlobals.client_controller.GetCache( 'preview' ), claim_focus = False )
        
        self._page_key = page_key
        
        HydrusGlobals.client_controller.sub( self, 'FocusChanged', 'focus_changed' )
        HydrusGlobals.client_controller.sub( self, 'ProcessContentUpdates', 'content_updates_gui' )
        
        self.Bind( wx.EVT_RIGHT_DOWN, self.EventShowMenu )
        
        self.Bind( wx.EVT_MENU, self.EventMenu )
        
        wx.CallAfter( self.Refresh )
        
    
    def EventMenu( self, event ):
        
        # is None bit means this is prob from a keydown->menu event
        if event.GetEventObject() is None and self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            action = ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetAction( event.GetId() )
            
            if action is not None:
                
                ( command, data ) = action
                
                if command == 'archive': self._Archive()
                elif command == 'copy_bmp': self._CopyBMPToClipboard()
                elif command == 'copy_files':
                    with wx.BusyCursor(): HydrusGlobals.client_controller.Write( 'copy_files', ( self._current_display_media.GetHash(), ) )
                elif command == 'copy_hash': self._CopyHashToClipboard( data )
                elif command == 'copy_local_url': self._CopyLocalUrlToClipboard()
                elif command == 'copy_path': self._CopyPathToClipboard()
                elif command == 'delete': self._Delete( data )
                elif command == 'inbox': self._Inbox()
                elif command == 'manage_ratings': self._ManageRatings()
                elif command == 'manage_tags': wx.CallAfter( self._ManageTags )
                elif command == 'open_externally': self._OpenExternally()
                elif command == 'undelete': self._Undelete()
                else: event.Skip()
                
            
        
    
    def EventShowMenu( self, event ):
        
        if self._current_display_media is not None:
            
            services = HydrusGlobals.client_controller.GetServicesManager().GetServices()
            
            locations_manager = self._current_display_media.GetLocationsManager()
            
            local_ratings_services = [ service for service in services if service.GetServiceType() in ( HC.LOCAL_RATING_LIKE, HC.LOCAL_RATING_NUMERICAL ) ]
            
            i_can_post_ratings = len( local_ratings_services ) > 0
            
            menu = wx.Menu()
            
            for line in self._current_display_media.GetPrettyInfoLines():
                
                menu.Append( CC.ID_NULL, line )
                
            
            #
            
            menu.AppendSeparator()
            
            if i_can_post_ratings:
                
                manage_menu = wx.Menu()
                
                manage_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'manage_tags' ), 'tags' )
                manage_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'manage_ratings' ), 'ratings' )
                
                menu.AppendMenu( CC.ID_NULL, 'manage', manage_menu )
                
            else:
                
                menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'manage_tags' ), 'manage tags' )
                
            
            menu.AppendSeparator()
            
            if self._current_display_media.HasInbox(): menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'archive' ), '&archive' )
            if self._current_display_media.HasArchive(): menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'inbox' ), 'return to &inbox' )
            
            if CC.LOCAL_FILE_SERVICE_KEY in locations_manager.GetCurrent():
                
                menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'delete', CC.LOCAL_FILE_SERVICE_KEY ), '&delete' )
                
            elif CC.TRASH_SERVICE_KEY in locations_manager.GetCurrent():
                
                menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'delete', CC.TRASH_SERVICE_KEY ), '&delete from trash now' )
                menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'undelete' ), '&undelete' )
                
            
            menu.AppendSeparator()
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'open_externally' ), '&open externally' )
            
            share_menu = wx.Menu()
            
            copy_menu = wx.Menu()
            
            copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_files' ), 'file' )
            
            copy_hash_menu = wx.Menu()
            
            copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'sha256' ) , 'sha256 (hydrus default)' )
            copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'md5' ) , 'md5' )
            copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'sha1' ) , 'sha1' )
            copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'sha512' ) , 'sha512' )
            
            copy_menu.AppendMenu( CC.ID_NULL, 'hash', copy_hash_menu )
            
            if self._current_display_media.GetMime() in HC.IMAGES and self._current_display_media.GetDuration() is None:
                
                copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_bmp' ), 'image' )
                
            
            copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_path' ), 'path' )
            
            if HC.options[ 'local_port' ] is not None:
                
                copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_local_url' ), 'local url' )
                
            
            share_menu.AppendMenu( CC.ID_NULL, 'copy', copy_menu )
            
            menu.AppendMenu( CC.ID_NULL, 'share', share_menu )
            
            HydrusGlobals.client_controller.PopupMenu( self, menu )
            
            event.Skip()
            
        
    
    def FocusChanged( self, page_key, media ):
        
        if page_key == self._page_key: self.SetMedia( media )
        
    
    def ProcessContentUpdates( self, service_keys_to_content_updates ):
        
        if self._current_display_media is not None:
            
            my_hash = self._current_display_media.GetHash()
            
            do_redraw = False
            
            for ( service_key, content_updates ) in service_keys_to_content_updates.items():
                
                if True in ( my_hash in content_update.GetHashes() for content_update in content_updates ):
                    
                    do_redraw = True
                    
                    break
                    
                
            
            if do_redraw:
                
                self._SetDirty()
                
            
        
    
class CanvasFrame( ClientGUICommon.FrameThatResizes ):
    
    def __init__( self, parent ):
        
        ClientGUICommon.FrameThatResizes.__init__( self, parent, resize_option_prefix = 'fs_', title = 'hydrus client media viewer' )
        
    
    def Close( self ):
        
        if HC.PLATFORM_OSX and self.IsFullScreen():
            
            self.ShowFullScreen( False, wx.FULLSCREEN_ALL )
            
        
        self.Destroy()
        
    
    def FullscreenSwitch( self ):
        
        if self.IsFullScreen():
            
            self.ShowFullScreen( False, wx.FULLSCREEN_ALL )
            
        else:
            
            self.ShowFullScreen( True, wx.FULLSCREEN_ALL )
            
        
    
    def SetCanvas( self, canvas_window ):
        
        self._canvas_window = canvas_window
        
        vbox = wx.BoxSizer( wx.VERTICAL )
        
        vbox.AddF( self._canvas_window, CC.FLAGS_EXPAND_SIZER_BOTH_WAYS )
        
        self.SetSizer( vbox )
        
        self.Show( True )
        
        wx.GetApp().SetTopWindow( self )
        
        self.Bind( wx.EVT_CLOSE, self._canvas_window.EventClose )
        
    
class CanvasMediaList( ClientMedia.ListeningMediaList, CanvasWithDetails ):
    
    def __init__( self, parent, page_key, media_results ):
        
        CanvasWithDetails.__init__( self, parent, HydrusGlobals.client_controller.GetCache( 'fullscreen' ) )
        ClientMedia.ListeningMediaList.__init__( self, CC.LOCAL_FILE_SERVICE_KEY, media_results )
        
        self._page_key = page_key
        
        self._just_started = True
        
        self._timer_cursor_hide = wx.Timer( self, id = ID_TIMER_CURSOR_HIDE )
        
        self.Bind( wx.EVT_TIMER, self.TIMEREventCursorHide, id = ID_TIMER_CURSOR_HIDE )
        
        self.Bind( wx.EVT_MOTION, self.EventDrag )
        self.Bind( wx.EVT_LEFT_DOWN, self.EventDragBegin )
        self.Bind( wx.EVT_LEFT_UP, self.EventDragEnd )
        
        HydrusGlobals.client_controller.pub( 'set_focus', self._page_key, None )
        
        HydrusGlobals.client_controller.sub( self, 'Close', 'canvas_close' )
        HydrusGlobals.client_controller.sub( self, 'FullscreenSwitch', 'canvas_fullscreen_switch' )
        
    
    def _Close( self ):
        
        self._closing = True
        
        HydrusGlobals.client_controller.pub( 'set_focus', self._page_key, self._current_media )
        
        self.GetParent().Close()
        
    
    def _DoManualPan( self, delta_x_step, delta_y_step ):
        
        ( my_x, my_y ) = self.GetClientSize()
        ( media_x, media_y ) = self._media_container.GetClientSize()
        
        x_pan_distance = min( my_x / 12, media_x / 12 )
        y_pan_distance = min( my_y / 12, media_y / 12 )
        
        delta_x = delta_x_step * x_pan_distance
        delta_y = delta_y_step * y_pan_distance
        
        ( old_delta_x, old_delta_y ) = self._total_drag_delta
        
        self._total_drag_delta = ( old_delta_x + delta_x, old_delta_y + delta_y )
        
        self._DrawCurrentMedia()
        
    
    def _GetIndexString( self ):
        
        if self._current_media is None:
            
            index_string = '-/' + HydrusData.ConvertIntToPrettyString( len( self._sorted_media ) )
            
        else:
            
            index_string = HydrusData.ConvertValueRangeToPrettyString( self._sorted_media.index( self._current_media ) + 1, len( self._sorted_media ) )
            
        
        return index_string
        
    
    def _PrefetchNeighbours( self ):
        
        media_looked_at = set()
        
        to_render = []
        
        previous = self._current_media
        next = self._current_media
        
        if self._just_started:
            
            delay_base = 800
            
            num_to_go_back = 1
            num_to_go_forward = 1
            
            self._just_started = False
            
        else:
            
            delay_base = 400
            
            num_to_go_back = 3
            num_to_go_forward = 5
            
        
        # if media_looked_at nukes the list, we want shorter delays, so do next first
        
        for i in range( num_to_go_forward ):
            
            next = self._GetNext( next )
            
            if next in media_looked_at:
                
                break
                
            else:
                
                media_looked_at.add( next )
                
            
            delay = delay_base * ( i + 1 )
            
            to_render.append( ( next, delay ) )
            
        
        for i in range( num_to_go_back ):
            
            previous = self._GetPrevious( previous )
            
            if previous in media_looked_at:
                
                break
                
            else:
                
                media_looked_at.add( previous )
                
            
            delay = delay_base * 2 * ( i + 1 )
            
            to_render.append( ( previous, delay ) )
            
        
        ( my_width, my_height ) = self.GetClientSize()
        
        for ( media, delay ) in to_render:
            
            hash = media.GetHash()
            
            if media.GetMime() in ( HC.IMAGE_JPEG, HC.IMAGE_PNG ):
                
                ( media_width, media_height ) = media.GetResolution()
                
                ( canvas_media_width, canvas_media_height ) = CalculateCanvasMediaSize( media, ( my_width, my_height ) )
                
                if media_width > canvas_media_width or media_height > canvas_media_height:
                    
                    zoom = CalculateCanvasFitZoom( media, ( my_width, my_height ) )
                    
                else:
                    
                    zoom = 1.0
                    
                
                resolution_to_request = ( int( round( zoom * media_width ) ), int( round( zoom * media_height ) ) )
                
                if not self._image_cache.HasImage( hash, resolution_to_request ):
                    
                    wx.CallLater( delay, self._image_cache.GetImage, media, resolution_to_request )
                    
                
            
        
    
    def _Remove( self ):
        
        next_media = self._GetNext( self._current_media )
        
        if next_media == self._current_media: next_media = None
        
        hashes = { self._current_display_media.GetHash() }
        
        HydrusGlobals.client_controller.pub( 'remove_media', self._page_key, hashes )
        
        singleton_media = { self._current_display_media }
        
        ClientMedia.ListeningMediaList._RemoveMedia( self, singleton_media, {} )
        
        if self.HasNoMedia(): self._Close()
        elif self.HasMedia( self._current_media ):
            
            HydrusGlobals.client_controller.pub( 'canvas_new_index_string', self._canvas_key, self._GetIndexString() )
            
            self._SetDirty()
            
        else: self.SetMedia( next_media )
        
    
    def _ShowFirst( self ): self.SetMedia( self._GetFirst() )
    
    def _ShowLast( self ): self.SetMedia( self._GetLast() )
    
    def _ShowNext( self ): self.SetMedia( self._GetNext( self._current_media ) )
    
    def _ShowPrevious( self ): self.SetMedia( self._GetPrevious( self._current_media ) )
    
    def _StartSlideshow( self, interval ): pass
    
    def AddMediaResults( self, page_key, media_results ):
        
        if page_key == self._page_key:
            
            ClientMedia.ListeningMediaList.AddMediaResults( self, media_results )
            
            HydrusGlobals.client_controller.pub( 'canvas_new_index_string', self._canvas_key, self._GetIndexString() )
            
            self._SetDirty()
            
        
    
    def Close( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._Close()
            
        
    
    def EventClose( self, event ):
        
        self._Close()
        
    
    def EventDrag( self, event ):
        
        CC.CAN_HIDE_MOUSE = True
        
        self._focus_holder.SetFocus()
        
        ( x, y ) = event.GetPosition()
        
        show_mouse = False
        
        if ( x, y ) != self._last_motion_coordinates:
            
            self._last_motion_coordinates = ( x, y )
            
            show_mouse = True
            
        
        if event.Dragging() and self._last_drag_coordinates is not None:
            
            ( old_x, old_y ) = self._last_drag_coordinates
            
            ( delta_x, delta_y ) = ( x - old_x, y - old_y )
            
            if HC.PLATFORM_WINDOWS:
                
                show_mouse = False
                
                self.WarpPointer( old_x, old_y )
                
            else:
                
                show_mouse = True
                
                self._last_drag_coordinates = ( x, y )
                
            
            ( old_delta_x, old_delta_y ) = self._total_drag_delta
            
            self._total_drag_delta = ( old_delta_x + delta_x, old_delta_y + delta_y )
            
            self._DrawCurrentMedia()
            
        
        if show_mouse:
        
            self.SetCursor( wx.StockCursor( wx.CURSOR_ARROW ) )
            
            self._timer_cursor_hide.Start( 800, wx.TIMER_ONE_SHOT )
            
        
    
    def EventDragBegin( self, event ):
        
        ( x, y ) = event.GetPosition()
        
        self.BeginDrag( ( x, y ) )
        
        event.Skip()
        
    
    def EventDragEnd( self, event ):
        
        self._last_drag_coordinates = None
        
        event.Skip()
        
    
    def EventFullscreenSwitch( self, event ):
        
        self.GetParent().FullscreenSwitch()
        
    
    def FullscreenSwitch( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self.GetParent().FullscreenSwitch()
            
        
    
    def KeepCursorAlive( self ): self._timer_cursor_hide.Start( 800, wx.TIMER_ONE_SHOT )
    
    def ProcessContentUpdates( self, service_keys_to_content_updates ):
        
        next_media = self._GetNext( self._current_media )
        
        if next_media == self._current_media: next_media = None
        
        ClientMedia.ListeningMediaList.ProcessContentUpdates( self, service_keys_to_content_updates )
        
        if self.HasNoMedia(): self._Close()
        elif self.HasMedia( self._current_media ):
            
            HydrusGlobals.client_controller.pub( 'canvas_new_index_string', self._canvas_key, self._GetIndexString() )
            
            self._SetDirty()
            
        else: self.SetMedia( next_media )
        
    
    def TIMEREventCursorHide( self, event ):
        
        try:
            
            if not CC.CAN_HIDE_MOUSE:
                
                return
                
            
            if HydrusGlobals.client_controller.MenuIsOpen():
                
                self._timer_cursor_hide.Start( 800, wx.TIMER_ONE_SHOT )
                
            else:
                
                self.SetCursor( wx.StockCursor( wx.CURSOR_BLANK ) )
                
            
        except wx.PyDeadObjectError:
            
            self._timer_cursor_hide.Stop()
            
        except:
            
            self._timer_cursor_hide.Stop()
            
            raise
            
        
    
class CanvasMediaListFilter( CanvasMediaList ):
    
    def __init__( self, my_parent, page_key, media_results ):
        
        CanvasMediaList.__init__( self, my_parent, page_key, media_results )
        
        self._kept = set()
        self._deleted = set()
        
        self.Bind( wx.EVT_LEFT_DOWN, self.EventMouseKeep )
        self.Bind( wx.EVT_LEFT_DCLICK, self.EventMouseKeep )
        self.Bind( wx.EVT_MIDDLE_DOWN, self.EventBack )
        self.Bind( wx.EVT_MIDDLE_DCLICK, self.EventBack )
        self.Bind( wx.EVT_MOUSEWHEEL, self.EventMouseWheel )
        self.Bind( wx.EVT_RIGHT_DOWN, self.EventDelete )
        self.Bind( wx.EVT_RIGHT_DCLICK, self.EventDelete )
        
        self.Bind( wx.EVT_MENU, self.EventMenu )
        
        self.Bind( wx.EVT_CHAR_HOOK, self.EventCharHook )
        
        wx.CallAfter( self.SetMedia, self._GetFirst() ) # don't set this until we have a size > (20, 20)!
        
    
    def _Back( self ):
        
        if not self._HydrusShouldNotProcessInput():
            
            if self._current_media == self._GetFirst(): return
            else:
                
                self._ShowPrevious()
                
                self._kept.discard( self._current_media )
                self._deleted.discard( self._current_media )
                
            
        
    
    def _Close( self ):
        
        if not self._HydrusShouldNotProcessInput():
            
            if len( self._kept ) > 0 or len( self._deleted ) > 0:
                
                with ClientGUIDialogs.DialogFinishFiltering( self, len( self._kept ), len( self._deleted ) ) as dlg:
                    
                    modal = dlg.ShowModal()
                    
                    if modal == wx.ID_CANCEL:
                        
                        if self._current_media in self._kept: self._kept.remove( self._current_media )
                        if self._current_media in self._deleted: self._deleted.remove( self._current_media )
                        
                    else:
                        
                        if modal == wx.ID_YES:
                            
                            self._deleted_hashes = [ media.GetHash() for media in self._deleted ]
                            self._kept_hashes = [ media.GetHash() for media in self._kept ]
                            
                            content_updates = []
                            
                            content_updates.append( HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_DELETE, self._deleted_hashes ) )
                            content_updates.append( HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_ARCHIVE, self._kept_hashes ) )
                            
                            HydrusGlobals.client_controller.Write( 'content_updates', { CC.LOCAL_FILE_SERVICE_KEY : content_updates } )
                            
                            self._kept = set()
                            self._deleted = set()
                            
                            self._current_media = self._GetFirst() # so the pubsub on close is better
                            
                            if HC.options[ 'remove_filtered_files' ]:
                                
                                all_hashes = set()
                                
                                all_hashes.update( self._deleted_hashes )
                                all_hashes.update( self._kept_hashes )
                                
                                HydrusGlobals.client_controller.pub( 'remove_media', self._page_key, all_hashes )
                                
                            
                        
                        CanvasMediaList._Close( self )
                        
                    
                
            else:
                
                CanvasMediaList._Close( self )
                
            
        
    
    def _Delete( self ):
        
        self._deleted.add( self._current_media )
        
        if self._current_media == self._GetLast(): self._Close()
        else: self._ShowNext()
        
    
    def _Keep( self ):
        
        self._kept.add( self._current_media )
        
        if self._current_media == self._GetLast(): self._Close()
        else: self._ShowNext()
        
    
    def _Skip( self ):
        
        if not self._HydrusShouldNotProcessInput():
            
            if self._current_media == self._GetLast(): self._Close()
            else: self._ShowNext()
            
        
    
    def Keep( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._Keep()
            
        
    
    def Back( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._Back()
            
        
    
    def Delete( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._Delete()
            
        
    
    def EventBack( self, event ):
        
        self._Back()
        
    
    def EventButtonBack( self, event ): self.EventBack( event )
    def EventButtonDelete( self, event ): self._Delete()
    def EventButtonDone( self, event ): self._Close()
    def EventButtonKeep( self, event ): self._Keep()
    def EventButtonSkip( self, event ):
        
        if self._current_media == self._GetLast(): self._Close()
        else: self._ShowNext()
        
    
    def EventCharHook( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else:
        
            ( modifier, key ) = ClientData.GetShortcutFromEvent( event )
            
            if modifier == wx.ACCEL_NORMAL and key == wx.WXK_SPACE: self._Keep()
            elif modifier == wx.ACCEL_NORMAL and key in ( ord( '+' ), wx.WXK_ADD, wx.WXK_NUMPAD_ADD ): self._ZoomIn()
            elif modifier == wx.ACCEL_NORMAL and key in ( ord( '-' ), wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT ): self._ZoomOut()
            elif modifier == wx.ACCEL_NORMAL and key == ord( 'Z' ): self._ZoomSwitch()
            elif modifier == wx.ACCEL_NORMAL and key == wx.WXK_BACK: self.EventBack( event )
            elif modifier == wx.ACCEL_NORMAL and key in ( wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_ESCAPE ): self._Close()
            elif modifier == wx.ACCEL_NORMAL and key in CC.DELETE_KEYS: self.EventDelete( event )
            elif modifier == wx.ACCEL_CTRL and key == ord( 'C' ):
                with wx.BusyCursor(): HydrusGlobals.client_controller.Write( 'copy_files', ( self._current_display_media.GetHash(), ) )
            elif not event.ShiftDown() and key in ( wx.WXK_UP, wx.WXK_NUMPAD_UP ): self.EventSkip( event )
            else:
                
                key_dict = HC.options[ 'shortcuts' ][ modifier ]
                
                if key in key_dict:
                    
                    action = key_dict[ key ]
                    
                    self.ProcessEvent( wx.CommandEvent( commandType = wx.wxEVT_COMMAND_MENU_SELECTED, winid = ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( action ) ) )
                    
                else: event.Skip()
                
            
        
    
    def EventDelete( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else: self._Delete()
        
    
    def EventMouseKeep( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            if event.ShiftDown(): self.EventDragBegin( event )
            else: self._Keep()
            
        
    
    def EventMenu( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            action = ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetAction( event.GetId() )
            
            if action is not None:
                
                ( command, data ) = action
                
                if command == 'archive': self._Keep()
                elif command == 'back': self.EventBack( event )
                elif command == 'close': self._Close()
                elif command == 'delete': self.EventDelete( event )
                elif command == 'fullscreen_switch': self.GetParent().FullscreenSwitch()
                elif command == 'filter': self._Close()
                elif command == 'frame_back': self._media_container.GotoPreviousOrNextFrame( -1 )
                elif command == 'frame_next': self._media_container.GotoPreviousOrNextFrame( 1 )
                elif command == 'manage_ratings': self._ManageRatings()
                elif command == 'manage_tags': wx.CallAfter( self._ManageTags )
                elif command in ( 'pan_up', 'pan_down', 'pan_left', 'pan_right' ):
                    
                    if command == 'pan_up': self._DoManualPan( 0, -1 )
                    elif command == 'pan_down': self._DoManualPan( 0, 1 )
                    elif command == 'pan_left': self._DoManualPan( -1, 0 )
                    elif command == 'pan_right': self._DoManualPan( 1, 0 )
                    
                elif command == 'zoom_in': self._ZoomIn()
                elif command == 'zoom_out': self._ZoomOut()
                else: event.Skip()
                
            
        
    
    def EventMouseWheel( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            if event.CmdDown():
                
                if event.GetWheelRotation() > 0: self._ZoomIn()
                else: self._ZoomOut()
                
            
        
    
    def EventSkip( self, event ):
        
        self._Skip()
        
    
    def EventUndelete( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else: self._Undelete()
        
    
    def Skip( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._Skip()
            
        
    
    def Undelete( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._Undelete()
            
        
    
class CanvasMediaListFilterInbox( CanvasMediaListFilter ):
    
    def __init__( self, my_parent, page_key, media_results ):
        
        CanvasMediaListFilter.__init__( self, my_parent, page_key, media_results )
        
        HydrusGlobals.client_controller.sub( self, 'Keep', 'canvas_archive' )
        HydrusGlobals.client_controller.sub( self, 'Delete', 'canvas_delete' )
        HydrusGlobals.client_controller.sub( self, 'Skip', 'canvas_show_next' )
        HydrusGlobals.client_controller.sub( self, 'Undelete', 'canvas_undelete' )
        HydrusGlobals.client_controller.sub( self, 'Back', 'canvas_show_previous' )
        
        self._hover_commands.SetNavigable( False )
        self._hover_commands.SetAlwaysArchive( True )
        
    
class CanvasMediaListNavigable( CanvasMediaList ):
    
    def __init__( self, my_parent, page_key, media_results ):
        
        CanvasMediaList.__init__( self, my_parent, page_key, media_results )
        
        HydrusGlobals.client_controller.sub( self, 'Archive', 'canvas_archive' )
        HydrusGlobals.client_controller.sub( self, 'Delete', 'canvas_delete' )
        HydrusGlobals.client_controller.sub( self, 'Inbox', 'canvas_inbox' )
        HydrusGlobals.client_controller.sub( self, 'ShowFirst', 'canvas_show_first' )
        HydrusGlobals.client_controller.sub( self, 'ShowLast', 'canvas_show_last' )
        HydrusGlobals.client_controller.sub( self, 'ShowNext', 'canvas_show_next' )
        HydrusGlobals.client_controller.sub( self, 'ShowPrevious', 'canvas_show_previous' )
        HydrusGlobals.client_controller.sub( self, 'Undelete', 'canvas_undelete' )
        
        self._hover_commands.SetNavigable( True )
        
    
    def Archive( self, canvas_key ):
        
        if self._canvas_key == canvas_key:
            
            self._Archive()
            
        
    
    def Delete( self, canvas_key ):
        
        if self._canvas_key == canvas_key:
            
            self._Delete()
            
        
    
    def EventArchive( self, event ):
        
        self._Archive()
        
    
    def EventDelete( self, event ):
        
        self._Delete()
        
    
    def EventNext( self, event ):
        
        self._ShowNext()
        
    
    def EventPrevious( self, event ):
        
        self._ShowPrevious()
        
    
    def Inbox( self, canvas_key ):
        
        if self._canvas_key == canvas_key:
            
            self._Inbox()
            
        
    
    def ShowFirst( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._ShowFirst()
            
        
    
    def ShowLast( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._ShowLast()
            
        
    
    def ShowNext( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._ShowNext()
            
        
    
    def ShowPrevious( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._ShowPrevious()
            
        
    
    def Undelete( self, canvas_key ):
        
        if canvas_key == self._canvas_key:
            
            self._Undelete()
            
        
    
class CanvasMediaListBrowser( CanvasMediaListNavigable ):
    
    def __init__( self, my_parent, page_key, media_results, first_hash ):
        
        CanvasMediaListNavigable.__init__( self, my_parent, page_key, media_results )
        
        self._timer_slideshow = wx.Timer( self, id = ID_TIMER_SLIDESHOW )
        self._timer_slideshow_interval = 0
        
        self.Bind( wx.EVT_TIMER, self.TIMEREventSlideshow, id = ID_TIMER_SLIDESHOW )
        
        self.Bind( wx.EVT_LEFT_DCLICK, self.EventClose )
        self.Bind( wx.EVT_MIDDLE_DOWN, self.EventClose )
        self.Bind( wx.EVT_MOUSEWHEEL, self.EventMouseWheel )
        self.Bind( wx.EVT_RIGHT_DOWN, self.EventShowMenu )
        
        self.Bind( wx.EVT_MENU, self.EventMenu )
        self.Bind( wx.EVT_CHAR_HOOK, self.EventCharHook )
        
        if first_hash is None:
            
            first_media = self._GetFirst()
            
        else:
            
            try:
                
                first_media = self._GetMedia( { first_hash } )[0]
                
            except:
                
                first_media = self._GetFirst()
                
            
        
        wx.CallAfter( self.SetMedia, first_media ) # don't set this until we have a size > (20, 20)!
        
        HydrusGlobals.client_controller.sub( self, 'AddMediaResults', 'add_media_results' )
        
    
    def _PausePlaySlideshow( self ):
        
        if self._timer_slideshow.IsRunning():
            
            self._timer_slideshow.Stop()
            
        elif self._timer_slideshow.GetInterval() > 0:
            
            self._timer_slideshow.Start()
            
        
    
    def _StartSlideshow( self, interval = None ):
        
        self._timer_slideshow.Stop()
        
        if interval is None:
            
            with ClientGUIDialogs.DialogTextEntry( self, 'Enter the interval, in seconds.', default = '15' ) as dlg:
                
                if dlg.ShowModal() == wx.ID_OK:
                    
                    try: interval = int( float( dlg.GetValue() ) * 1000 )
                    except: return
                    
                
            
        
        if interval > 0:
            
            self._timer_slideshow_interval = interval
            
            self._timer_slideshow.Start( self._timer_slideshow_interval, wx.TIMER_CONTINUOUS )
            
        
    
    def EventCharHook( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            ( modifier, key ) = ClientData.GetShortcutFromEvent( event )
            
            if modifier == wx.ACCEL_NORMAL and key in CC.DELETE_KEYS: self._Delete()
            elif modifier == wx.ACCEL_SHIFT and key in CC.DELETE_KEYS: self._Undelete()
            elif modifier == wx.ACCEL_NORMAL and key in ( wx.WXK_SPACE, wx.WXK_NUMPAD_SPACE ): wx.CallAfter( self._PausePlaySlideshow )
            elif modifier == wx.ACCEL_NORMAL and key in ( ord( '+' ), wx.WXK_ADD, wx.WXK_NUMPAD_ADD ): self._ZoomIn()
            elif modifier == wx.ACCEL_NORMAL and key in ( ord( '-' ), wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT ): self._ZoomOut()
            elif modifier == wx.ACCEL_NORMAL and key == ord( 'Z' ): self._ZoomSwitch()
            elif modifier == wx.ACCEL_NORMAL and key in ( wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_ESCAPE ): self._Close()
            elif modifier == wx.ACCEL_CTRL and key == ord( 'C' ):
                with wx.BusyCursor(): HydrusGlobals.client_controller.Write( 'copy_files', ( self._current_display_media.GetHash(), ) )
            else:
                
                key_dict = HC.options[ 'shortcuts' ][ modifier ]
                
                if key in key_dict:
                    
                    action = key_dict[ key ]
                    
                    self.ProcessEvent( wx.CommandEvent( commandType = wx.wxEVT_COMMAND_MENU_SELECTED, winid = ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( action ) ) )
                    
                else: event.Skip()
                
            
        
    
    def EventMenu( self, event ):
        
        # is None bit means this is prob from a keydown->menu event
        if event.GetEventObject() is None and self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            action = ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetAction( event.GetId() )
            
            if action is not None:
                
                ( command, data ) = action
                
                if command == 'archive': self._Archive()
                elif command == 'copy_bmp': self._CopyBMPToClipboard()
                elif command == 'copy_files':
                    with wx.BusyCursor(): HydrusGlobals.client_controller.Write( 'copy_files', ( self._current_display_media.GetHash(), ) )
                elif command == 'copy_hash': self._CopyHashToClipboard( data )
                elif command == 'copy_local_url': self._CopyLocalUrlToClipboard()
                elif command == 'copy_path': self._CopyPathToClipboard()
                elif command == 'delete': self._Delete( data )
                elif command == 'fullscreen_switch': self.GetParent().FullscreenSwitch()
                elif command == 'first': self._ShowFirst()
                elif command == 'last': self._ShowLast()
                elif command == 'previous': self._ShowPrevious()
                elif command == 'next': self._ShowNext()
                elif command == 'frame_back': self._media_container.GotoPreviousOrNextFrame( -1 )
                elif command == 'frame_next': self._media_container.GotoPreviousOrNextFrame( 1 )
                elif command == 'inbox': self._Inbox()
                elif command == 'manage_ratings': self._ManageRatings()
                elif command == 'manage_tags': wx.CallLater( 1, self._ManageTags )
                elif command == 'open_externally': self._OpenExternally()
                elif command in ( 'pan_up', 'pan_down', 'pan_left', 'pan_right' ):
                    
                    if command == 'pan_up': self._DoManualPan( 0, -1 )
                    elif command == 'pan_down': self._DoManualPan( 0, 1 )
                    elif command == 'pan_left': self._DoManualPan( -1, 0 )
                    elif command == 'pan_right': self._DoManualPan( 1, 0 )
                    
                elif command == 'remove': self._Remove()
                elif command == 'slideshow': wx.CallLater( 1, self._StartSlideshow, data )
                elif command == 'slideshow_pause_play': wx.CallLater( 1, self._PausePlaySlideshow )
                elif command == 'undelete': self._Undelete()
                elif command == 'zoom_in': self._ZoomIn()
                elif command == 'zoom_out': self._ZoomOut()
                elif command == 'zoom_switch': self._ZoomSwitch()
                else: event.Skip()
                
            
        
    
    def EventMouseWheel( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            if event.CmdDown():
                
                if event.GetWheelRotation() > 0: self._ZoomIn()
                else: self._ZoomOut()
                
            else:
                
                if event.GetWheelRotation() > 0: self._ShowPrevious()
                else: self._ShowNext()
                
            
        
    
    def EventShowMenu( self, event ):
        
        services = HydrusGlobals.client_controller.GetServicesManager().GetServices()
        
        local_ratings_services = [ service for service in services if service.GetServiceType() in ( HC.LOCAL_RATING_LIKE, HC.LOCAL_RATING_NUMERICAL ) ]
        
        i_can_post_ratings = len( local_ratings_services ) > 0
        
        self._last_drag_coordinates = None # to stop successive right-click drag warp bug
        
        locations_manager = self._current_display_media.GetLocationsManager()
        
        menu = wx.Menu()
        
        for line in self._current_display_media.GetPrettyInfoLines():
            
            menu.Append( CC.ID_NULL, line )
            
        
        menu.AppendSeparator()
        
        if self._IsZoomable():
            
            menu.Append( CC.ID_NULL, 'current zoom: ' + ClientData.ConvertZoomToPercentage( self._current_zoom ) )
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'zoom_in' ), 'zoom in' )
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'zoom_out' ), 'zoom out' )
            
            if self._current_display_media.GetMime() != HC.APPLICATION_FLASH:
                
                ( my_width, my_height ) = self.GetClientSize()
                
                ( media_width, media_height ) = self._current_display_media.GetResolution()
                
                if self._current_zoom == 1.0:
                    
                    if media_width > my_width or media_height > my_height: menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'zoom_switch' ), 'zoom fit' )
                    
                else: menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'zoom_switch' ), 'zoom full' )
                
            
            menu.AppendSeparator()
            
        
        if i_can_post_ratings:
            
            manage_menu = wx.Menu()
            
            manage_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'manage_tags' ), 'tags' )
            manage_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'manage_ratings' ), 'ratings' )
            
            menu.AppendMenu( CC.ID_NULL, 'manage', manage_menu )
            
        else:
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'manage_tags' ), 'manage tags' )
            
        
        menu.AppendSeparator()
        
        if self._current_display_media.HasInbox(): menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'archive' ), '&archive' )
        if self._current_display_media.HasArchive(): menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'inbox' ), 'return to &inbox' )
        
        menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'remove' ), '&remove' )
        
        if CC.LOCAL_FILE_SERVICE_KEY in locations_manager.GetCurrent():
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'delete', CC.LOCAL_FILE_SERVICE_KEY ), '&delete' )
            
        elif CC.TRASH_SERVICE_KEY in locations_manager.GetCurrent():
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'delete', CC.TRASH_SERVICE_KEY ), '&delete from trash now' )
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'undelete' ), '&undelete' )
            
        
        menu.AppendSeparator()
        
        menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'open_externally' ), '&open externally' )
        
        share_menu = wx.Menu()
        
        copy_menu = wx.Menu()
        
        copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_files' ), 'file' )
        
        copy_hash_menu = wx.Menu()
        
        copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'sha256' ) , 'sha256 (hydrus default)' )
        copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'md5' ) , 'md5' )
        copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'sha1' ) , 'sha1' )
        copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'sha512' ) , 'sha512' )
        
        copy_menu.AppendMenu( CC.ID_NULL, 'hash', copy_hash_menu )
        
        if self._current_display_media.GetMime() in HC.IMAGES and self._current_display_media.GetDuration() is None:
            
            copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_bmp' ), 'image' )
            
        
        copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_path' ), 'path' )
        
        if HC.options[ 'local_port' ] is not None:
            
            copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_local_url' ), 'local url' )
            
        
        share_menu.AppendMenu( CC.ID_NULL, 'copy', copy_menu )
        
        menu.AppendMenu( CC.ID_NULL, 'share', share_menu )
        
        menu.AppendSeparator()
        
        slideshow = wx.Menu()
        
        slideshow.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'slideshow', 1000 ), '1 second' )
        slideshow.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'slideshow', 5000 ), '5 seconds' )
        slideshow.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'slideshow', 10000 ), '10 seconds' )
        slideshow.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'slideshow', 30000 ), '30 seconds' )
        slideshow.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'slideshow', 60000 ), '60 seconds' )
        slideshow.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'slideshow', 80 ), 'william gibson' )
        slideshow.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'slideshow' ), 'custom interval' )
        
        menu.AppendMenu( CC.ID_NULL, 'start slideshow', slideshow )
        
        if self._timer_slideshow.IsRunning(): menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'slideshow_pause_play' ), 'stop slideshow' )
        
        menu.AppendSeparator()
        
        if self.GetParent().IsFullScreen():
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'fullscreen_switch' ), 'exit fullscreen' )
            
        else:
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'fullscreen_switch' ), 'go fullscreen' )
            
        
        if self._timer_slideshow.IsRunning():
            
            self._timer_slideshow.Stop()
            
            HydrusGlobals.client_controller.PopupMenu( self, menu )
            
            self._timer_slideshow.Start()
            
        else:
            
            HydrusGlobals.client_controller.PopupMenu( self, menu )
            
        
        event.Skip()
        
    
    def TIMEREventSlideshow( self, event ):
        
        try:
            
            if self._media_container is not None:
                
                if self._media_container.ReadyToSlideshow():
                    
                    self._ShowNext()
                    
                    self._timer_slideshow.Start( self._timer_slideshow_interval, wx.TIMER_CONTINUOUS )
                    
                else:
                    
                    self._timer_slideshow.Start( 250, wx.TIMER_CONTINUOUS )
                    
                
            
        except wx.PyDeadObjectError:
            
            self._timer_slideshow.Stop()
            
        except:
            
            self._timer_slideshow.Stop()
            
            raise
            
        
    
class CanvasMediaListCustomFilter( CanvasMediaListNavigable ):
    
    def __init__( self, parent, page_key, media_results, shortcuts ):
        
        CanvasMediaListNavigable.__init__( self, parent, page_key, media_results )
        
        self._shortcuts = shortcuts
        
        self.Bind( wx.EVT_LEFT_DCLICK, self.EventClose )
        self.Bind( wx.EVT_MIDDLE_DOWN, self.EventClose )
        self.Bind( wx.EVT_MOUSEWHEEL, self.EventMouseWheel )
        self.Bind( wx.EVT_RIGHT_DOWN, self.EventShowMenu )
        
        self.Bind( wx.EVT_MENU, self.EventMenu )
        
        self.Bind( wx.EVT_CHAR_HOOK, self.EventCharHook )
        
        wx.CallAfter( self.SetMedia, self._GetFirst() ) # don't set this until we have a size > (20, 20)!
        
        self._hover_commands.AddCommand( 'edit shortcuts', self.EventShortcuts )
        
        HydrusGlobals.client_controller.sub( self, 'AddMediaResults', 'add_media_results' )
        
    
    def _CopyLocalUrlToClipboard( self ):
        
        local_url = 'http://127.0.0.1:' + str( HC.options[ 'local_port' ] ) + '/file?hash=' + self._current_display_media.GetHash().encode( 'hex' )
        
        HydrusGlobals.client_controller.pub( 'clipboard', 'text', local_url )
        
    
    def _CopyPathToClipboard( self ):
        
        client_files_manager = HydrusGlobals.client_controller.GetClientFilesManager()
        
        path = client_files_manager.GetFilePath( self._current_display_media.GetHash(), self._current_display_media.GetMime() )
        
        HydrusGlobals.client_controller.pub( 'clipboard', 'text', path )
        
    
    def _Inbox( self ): HydrusGlobals.client_controller.Write( 'content_updates', { CC.LOCAL_FILE_SERVICE_KEY : [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_INBOX, ( self._current_display_media.GetHash(), ) ) ] } )
    
    def EventShortcuts( self, event ):
        
        with ClientGUIDialogs.DialogShortcuts( self ) as dlg:
            
            if dlg.ShowModal() == wx.ID_OK: self._shortcuts = dlg.GetShortcuts()
            
        
    
    def EventCharHook( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            ( modifier, key ) = ClientData.GetShortcutFromEvent( event )
            
            action = self._shortcuts.GetKeyboardAction( modifier, key )
            
            if action is not None:
                
                ( service_key, data ) = action
                
                if service_key is None:
                    
                    if data == 'archive': self._Archive()
                    elif data == 'delete': self._Delete()
                    elif data == 'frame_back': self._media_container.GotoPreviousOrNextFrame( -1 )
                    elif data == 'frame_next': self._media_container.GotoPreviousOrNextFrame( 1 )
                    elif data == 'fullscreen_switch': self.GetParent().FullscreenSwitch()
                    elif data == 'inbox': self._Inbox()
                    elif data == 'manage_ratings': self._ManageRatings()
                    elif data == 'manage_tags': wx.CallLater( 1, self._ManageTags )
                    elif data in ( 'pan_up', 'pan_down', 'pan_left', 'pan_right' ):
                        
                        if data == 'pan_up': self._DoManualPan( 0, -1 )
                        elif data == 'pan_down': self._DoManualPan( 0, 1 )
                        elif data == 'pan_left': self._DoManualPan( -1, 0 )
                        elif data == 'pan_right': self._DoManualPan( 1, 0 )
                        
                    elif data == 'first': self._ShowFirst()
                    elif data == 'last': self._ShowLast()
                    elif data == 'previous': self._ShowPrevious()
                    elif data == 'next': self._ShowNext()
                    
                else:
                    
                    service = HydrusGlobals.client_controller.GetServicesManager().GetService( service_key )
                    
                    service_type = service.GetServiceType()
                    
                    hashes = ( self._current_display_media.GetHash(), )
                    
                    if service_type in HC.TAG_SERVICES:
                        
                        tag = data
                        
                        tags_manager = self._current_display_media.GetTagsManager()
                        
                        current = tags_manager.GetCurrent()
                        pending = tags_manager.GetPending()
                        petitioned = tags_manager.GetPetitioned()
                        
                        if service_type == HC.LOCAL_TAG:
                            
                            tags = [ tag ]
                            
                            if tag in current: content_update_action = HC.CONTENT_UPDATE_DELETE
                            else:
                                
                                content_update_action = HC.CONTENT_UPDATE_ADD
                                
                                tag_parents_manager = HydrusGlobals.client_controller.GetManager( 'tag_parents' )
                                
                                parents = tag_parents_manager.GetParents( service_key, tag )
                                
                                tags.extend( parents )
                                
                            
                            rows = [ ( tag, hashes ) for tag in tags ]
                            
                        else:
                            
                            if tag in current:
                                
                                if tag in petitioned: edit_log = [ ( HC.CONTENT_UPDATE_RESCIND_PETITION, tag ) ]
                                else:
                                    
                                    message = 'Enter a reason for this tag to be removed. A janitor will review your petition.'
                                    
                                    with ClientGUIDialogs.DialogTextEntry( self, message ) as dlg:
                                        
                                        if dlg.ShowModal() == wx.ID_OK:
                                            
                                            content_update_action = HC.CONTENT_UPDATE_PETITION
                                            
                                            rows = [ ( dlg.GetValue(), tag, hashes ) ]
                                            
                                        else: return
                                        
                                    
                                
                            else:
                                
                                tags = [ tag ]
                                
                                if tag in pending: content_update_action = HC.CONTENT_UPDATE_RESCIND_PEND
                                else:
                                    
                                    content_update_action = HC.CONTENT_UPDATE_PEND
                                    
                                    tag_parents_manager = HydrusGlobals.client_controller.GetManager( 'tag_parents' )
                                    
                                    parents = tag_parents_manager.GetParents( service_key, tag )
                                    
                                    tags.extend( parents )
                                    
                                
                                rows = [ ( tag, hashes ) for tag in tags ]
                                
                            
                        
                        content_updates = [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_MAPPINGS, content_update_action, row ) for row in rows ]
                        
                    elif service_type in ( HC.LOCAL_RATING_LIKE, HC.LOCAL_RATING_NUMERICAL ):
                        
                        # maybe this needs to be more complicated, if action is, say, remove the rating?
                        # ratings needs a good look at anyway
                        
                        rating = data
                        
                        row = ( rating, hashes )
                        
                        content_updates = [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_RATINGS, HC.CONTENT_UPDATE_ADD, row ) ]
                        
                    
                    HydrusGlobals.client_controller.Write( 'content_updates', { service_key : content_updates } )
                    
                
            else:
                
                if modifier == wx.ACCEL_NORMAL and key in ( ord( '+' ), wx.WXK_ADD, wx.WXK_NUMPAD_ADD ): self._ZoomIn()
                elif modifier == wx.ACCEL_NORMAL and key in ( ord( '-' ), wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT ): self._ZoomOut()
                elif modifier == wx.ACCEL_NORMAL and key == ord( 'Z' ): self._ZoomSwitch()
                elif modifier == wx.ACCEL_NORMAL and key in ( wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_ESCAPE ): self._Close()
                elif modifier == wx.ACCEL_CTRL and key == ord( 'C' ):
                    with wx.BusyCursor(): HydrusGlobals.client_controller.Write( 'copy_files', ( self._current_display_media.GetHash(), ) )
                else:
                    
                    key_dict = HC.options[ 'shortcuts' ][ modifier ]
                    
                    if key in key_dict:
                        
                        action = key_dict[ key ]
                        
                        self.ProcessEvent( wx.CommandEvent( commandType = wx.wxEVT_COMMAND_MENU_SELECTED, winid = ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( action ) ) )
                        
                    else: event.Skip()
                    
                
            
        
    
    def EventMenu( self, event ):
        
        # is None bit means this is prob from a keydown->menu event
        if event.GetEventObject() is None and self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            action = ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetAction( event.GetId() )
            
            if action is not None:
                
                ( command, data ) = action
                
                if command == 'archive': self._Archive()
                elif command == 'copy_bmp': self._CopyBMPToClipboard()
                elif command == 'copy_files':
                    with wx.BusyCursor(): HydrusGlobals.client_controller.Write( 'copy_files', ( self._current_display_media.GetHash(), ) )
                elif command == 'copy_hash': self._CopyHashToClipboard( data )
                elif command == 'copy_local_url': self._CopyLocalUrlToClipboard()
                elif command == 'copy_path': self._CopyPathToClipboard()
                elif command == 'delete': self._Delete( data )
                elif command == 'fullscreen_switch': self.GetParent().FullscreenSwitch()
                elif command == 'first': self._ShowFirst()
                elif command == 'last': self._ShowLast()
                elif command == 'previous': self._ShowPrevious()
                elif command == 'next': self._ShowNext()
                elif command == 'frame_back': self._media_container.GotoPreviousOrNextFrame( -1 )
                elif command == 'frame_next': self._media_container.GotoPreviousOrNextFrame( 1 )
                elif command == 'inbox': self._Inbox()
                elif command == 'manage_ratings': self._ManageRatings()
                elif command == 'manage_tags': wx.CallLater( 1, self._ManageTags )
                elif command == 'open_externally': self._OpenExternally()
                elif command == 'remove': self._Remove()
                elif command == 'undelete': self._Undelete()
                elif command == 'zoom_in': self._ZoomIn()
                elif command == 'zoom_out': self._ZoomOut()
                elif command == 'zoom_switch': self._ZoomSwitch()
                else: event.Skip()
                
            
        
    
    def EventMouseWheel( self, event ):
        
        if self._HydrusShouldNotProcessInput(): event.Skip()
        else:
            
            if event.CmdDown():
                
                if event.GetWheelRotation() > 0: self._ZoomIn()
                else: self._ZoomOut()
                
            else:
                
                if event.GetWheelRotation() > 0: self._ShowPrevious()
                else: self._ShowNext()
                
            
        
    
    def EventShowMenu( self, event ):
        
        services = HydrusGlobals.client_controller.GetServicesManager().GetServices()
        
        local_ratings_services = [ service for service in services if service.GetServiceType() in ( HC.LOCAL_RATING_LIKE, HC.LOCAL_RATING_NUMERICAL ) ]
        
        i_can_post_ratings = len( local_ratings_services ) > 0
        
        locations_manager = self._current_display_media.GetLocationsManager()
        
        #
        
        self._last_drag_coordinates = None # to stop successive right-click drag warp bug
        
        menu = wx.Menu()
        
        for line in self._current_display_media.GetPrettyInfoLines():
            
            menu.Append( CC.ID_NULL, line )
            
        
        menu.AppendSeparator()
        
        if self._IsZoomable():
            
            menu.Append( CC.ID_NULL, 'current zoom: ' + ClientData.ConvertZoomToPercentage( self._current_zoom ) )
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'zoom_in' ), 'zoom in' )
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'zoom_out' ), 'zoom out' )
            
            #
            
            if self._current_display_media.GetMime() != HC.APPLICATION_FLASH:
                
                ( my_width, my_height ) = self.GetClientSize()
                
                ( media_width, media_height ) = self._current_display_media.GetResolution()
                
                if self._current_zoom == 1.0:
                    
                    if media_width > my_width or media_height > my_height: menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'zoom_switch' ), 'zoom fit' )
                    
                else: menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'zoom_switch' ), 'zoom full' )
                
            
            menu.AppendSeparator()
            
        
        if i_can_post_ratings:
            
            manage_menu = wx.Menu()
            
            manage_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'manage_tags' ), 'tags' )
            manage_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'manage_ratings' ), 'ratings' )
            
            menu.AppendMenu( CC.ID_NULL, 'manage', manage_menu )
            
        else:
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'manage_tags' ), 'manage tags' )
            
        
        menu.AppendSeparator()
        
        if self._current_display_media.HasInbox(): menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'archive' ), '&archive' )
        if self._current_display_media.HasArchive(): menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'inbox' ), 'return to &inbox' )
        
        menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'remove' ), '&remove' )
        
        if CC.LOCAL_FILE_SERVICE_KEY in locations_manager.GetCurrent():
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'delete', CC.LOCAL_FILE_SERVICE_KEY ), '&delete' )
            
        elif CC.TRASH_SERVICE_KEY in locations_manager.GetCurrent():
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'delete', CC.TRASH_SERVICE_KEY ), '&delete from trash now' )
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'undelete' ), '&undelete' )
            
        
        menu.AppendSeparator()
        
        menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'open_externally' ), '&open externally' )
        
        share_menu = wx.Menu()
        
        copy_menu = wx.Menu()
        
        copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_files' ), 'file' )
        
        copy_hash_menu = wx.Menu()
        
        copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'sha256' ) , 'sha256 (hydrus default)' )
        copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'md5' ) , 'md5' )
        copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'sha1' ) , 'sha1' )
        copy_hash_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_hash', 'sha512' ) , 'sha512' )
        
        copy_menu.AppendMenu( CC.ID_NULL, 'hash', copy_hash_menu )
        
        if self._current_display_media.GetMime() in HC.IMAGES and self._current_display_media.GetDuration() is None: copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_bmp' ), 'image' )
        copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_path' ), 'path' )
        copy_menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'copy_local_url' ), 'local url' )
        
        share_menu.AppendMenu( CC.ID_NULL, 'copy', copy_menu )
        
        menu.AppendMenu( CC.ID_NULL, 'share', share_menu )
        
        menu.AppendSeparator()
        
        if self.GetParent().IsFullScreen():
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'fullscreen_switch' ), 'exit fullscreen' )
            
        else:
            
            menu.Append( ClientCaches.MENU_EVENT_ID_TO_ACTION_CACHE.GetTemporaryId( 'fullscreen_switch' ), 'go fullscreen' )
            
        
        HydrusGlobals.client_controller.PopupMenu( self, menu )
        
        event.Skip()
        
    
class RatingsFilterFrameLike( CanvasMediaListFilter ):
    
    def __init__( self, my_parent, page_key, service_key, media_results ):
        
        CanvasMediaListFilter.__init__( self, my_parent, page_key, CC.LOCAL_FILE_SERVICE_KEY, media_results )
        
        self._rating_service_key = service_key
        self._service = HydrusGlobals.client_controller.GetServicesManager().GetService( service_key )
        
        self._hover_commands.SetNavigable( False )
        
    
    def _Close( self ):
        
        if not self._HydrusShouldNotProcessInput():
            
            if len( self._kept ) > 0 or len( self._deleted ) > 0:
                
                ( like, dislike ) = self._service.GetLikeDislike()
                
                with ClientGUIDialogs.DialogFinishFiltering( self, len( self._kept ), len( self._deleted ), keep = like, delete = dislike ) as dlg:
                    
                    modal = dlg.ShowModal()
                    
                    if modal == wx.ID_CANCEL:
                        
                        if self._current_media in self._kept: self._kept.remove( self._current_media )
                        if self._current_media in self._deleted: self._deleted.remove( self._current_media )
                        
                    else:
                        
                        if modal == wx.ID_YES:
                            
                            self._deleted_hashes = [ media.GetHash() for media in self._deleted ]
                            self._kept_hashes = [ media.GetHash() for media in self._kept ]
                            
                            content_updates = []
                            
                            content_updates.extend( [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_RATINGS, HC.CONTENT_UPDATE_ADD, ( 0.0, set( ( hash, ) ) ) ) for hash in self._deleted_hashes ] )
                            content_updates.extend( [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_RATINGS, HC.CONTENT_UPDATE_ADD, ( 1.0, set( ( hash, ) ) ) ) for hash in self._kept_hashes ] )
                            
                            HydrusGlobals.client_controller.Write( 'content_updates', { self._rating_service_key : content_updates } )
                            
                            self._kept = set()
                            self._deleted = set()
                            
                        
                        CanvasMediaList._Close( self )
                        
                    
                
            else: CanvasMediaList._Close( self )
            
        
    
class MediaContainer( wx.Window ):
    
    def __init__( self, parent, image_cache, media, initial_size, initial_position ):
        
        wx.Window.__init__( self, parent, size = initial_size, pos = initial_position )
        
        self._image_cache = image_cache
        self._media = media
        self._media_window = None
        self._embed_button = None
        self._animation_bar = None
        
        self._MakeMediaWindow()
        
        self._SizeAndPositionMediaWindow()
        
        self.Bind( wx.EVT_SIZE, self.EventResize )
        self.Bind( wx.EVT_MOUSE_EVENTS, self.EventPropagateMouse )
        self.Bind( wx.EVT_ERASE_BACKGROUND, self.EventEraseBackground )
        
    
    def _MakeMediaWindow( self, do_embed_button = True ):
        
        ( media_initial_size, media_initial_position ) = ( self.GetClientSize(), ( 0, 0 ) )
        
        action = HC.options[ 'mime_media_viewer_actions' ][ self._media.GetDisplayMedia().GetMime() ]
        
        if do_embed_button and action in ( CC.MEDIA_VIEWER_SHOW_BEHIND_EMBED, CC.MEDIA_VIEWER_SHOW_BEHIND_EMBED_PAUSED ):
            
            self._embed_button = EmbedButton( self, media_initial_size )
            self._embed_button.Bind( wx.EVT_LEFT_DOWN, self.EventEmbedButton )
            
            return
            
        elif self._embed_button is not None:
            
            self._embed_button.Hide()
            
        
        if action == CC.MEDIA_VIEWER_DO_NOT_SHOW:
            
            raise Exception( 'This media should not be shown in the media viewer!' )
            
        elif action == CC.MEDIA_VIEWER_SHOW_OPEN_EXTERNALLY_BUTTON:
            
            self._media_window = OpenExternallyButton( self, self._media )
            
        else:
            
            start_paused = action in ( CC.MEDIA_VIEWER_SHOW_AS_NORMAL_PAUSED, CC.MEDIA_VIEWER_SHOW_BEHIND_EMBED_PAUSED )
            
            if ShouldHaveAnimationBar( self._media ) or self._media.GetMime() == HC.APPLICATION_FLASH:
                
                if ShouldHaveAnimationBar( self._media ):
                    
                    ( x, y ) = media_initial_size
                    
                    media_initial_size = ( x, y - ANIMATED_SCANBAR_HEIGHT )
                    
                
                if self._media.GetMime() == HC.APPLICATION_FLASH:
                    
                    self._media_window = wx.lib.flashwin.FlashWindow( self, size = media_initial_size, pos = media_initial_position )
                    
                    client_files_manager = HydrusGlobals.client_controller.GetClientFilesManager()
                    
                    self._media_window.movie = client_files_manager.GetFilePath( self._media.GetHash(), HC.APPLICATION_FLASH )
                    
                else:
                    
                    self._media_window = Animation( self, self._media, media_initial_size, media_initial_position, start_paused )
                    
                
                if ShouldHaveAnimationBar( self._media ):
                    
                    self._animation_bar = AnimationBar( self, self._media, self._media_window )
                    
                    if self._media.GetMime() != HC.APPLICATION_FLASH: self._media_window.SetAnimationBar( self._animation_bar )
                    
                
            else:
                
                self._media_window = StaticImage( self, self._media, self._image_cache, media_initial_size, media_initial_position )
                
            
        
    
    def _SizeAndPositionMediaWindow( self ):
        
        ( my_width, my_height ) = self.GetClientSize()
        
        if self._media_window is None:
            
            self._embed_button.SetSize( ( my_width, my_height ) )
            
        else:
            
            ( media_width, media_height ) = ( my_width, my_height )
            
            if self._animation_bar is not None:
                
                media_height -= ANIMATED_SCANBAR_HEIGHT
                
                self._animation_bar.SetSize( ( my_width, ANIMATED_SCANBAR_HEIGHT ) )
                self._animation_bar.SetPosition( ( 0, my_height - ANIMATED_SCANBAR_HEIGHT ) )
                
            
            self._media_window.SetSize( ( media_width, media_height ) )
            self._media_window.SetPosition( ( 0, 0 ) )
            
        
    
    def BeginDrag( self ):
        
        self.GetParent().BeginDrag()
        
    
    def EventEmbedButton( self, event ):
        
        self._MakeMediaWindow( do_embed_button = False )
        
    
    def EventEraseBackground( self, event ): pass
    
    def EventPropagateMouse( self, event ):
        
        mime = self._media.GetMime()
        
        if mime in HC.IMAGES or mime in HC.VIDEO:
            
            screen_position = self.ClientToScreen( event.GetPosition() )
            ( x, y ) = self.GetParent().ScreenToClient( screen_position )
            
            event.SetX( x )
            event.SetY( y )
            
            event.ResumePropagation( 1 )
            event.Skip()
            
        
    
    def EventResize( self, event ):
        
        self._SizeAndPositionMediaWindow()
        
    
    def GotoPreviousOrNextFrame( self, direction ):
        
        if self._media_window is not None:
            
            if ShouldHaveAnimationBar( self._media ):
                
                current_frame_index = self._media_window.CurrentFrame()
                
                num_frames = self._media.GetNumFrames()
                
                if direction == 1:
                    
                    if current_frame_index == num_frames - 1: current_frame_index = 0
                    else: current_frame_index += 1
                    
                else:
                    
                    if current_frame_index == 0: current_frame_index = num_frames - 1
                    else: current_frame_index -= 1
                    
                
                self._media_window.GotoFrame( current_frame_index )
                self._animation_bar.GotoFrame( current_frame_index )
                
            
        
    
    def MouseIsNearAnimationBar( self ):
        
        if self._animation_bar is not None:
            
            ( x, y ) = self._animation_bar.GetScreenPosition()
            ( width, height ) = self._animation_bar.GetSize()
            
            ( mouse_x, mouse_y ) = wx.GetMousePosition()
            
            buffer_distance = 100
            
            if mouse_x >= x - buffer_distance and mouse_x <= x + width + buffer_distance and mouse_y >= y - buffer_distance and mouse_y <= y + height + buffer_distance:
                
                return True
                
            
        
        return False
        
    
    def Pause( self ):
        
        if isinstance( self._media_window, Animation ):
            
            self._media_window.Pause()
            
        
    
    def ReadyToSlideshow( self ):
        
        if isinstance( self._media_window, Animation ):
            
            if self._media_window.IsPlaying() and not self._media_window.HasPlayedOnceThrough():
                
                return False
                
            
        
        if isinstance( self._media_window, StaticImage ):
            
            if not self._media_window.IsRendered():
                
                return False
                
            
        
        return True
        
    
class EmbedButton( wx.Window ):
    
    def __init__( self, parent, size ):
        
        wx.Window.__init__( self, parent, size = size )
        
        self._dirty = True
        
        ( x, y ) = size
        
        self._canvas_bmp = wx.EmptyBitmap( x, y, 24 )
        
        self.Bind( wx.EVT_PAINT, self.EventPaint )
        self.Bind( wx.EVT_SIZE, self.EventResize )
        self.Bind( wx.EVT_ERASE_BACKGROUND, self.EventEraseBackground )
        
    
    def _Redraw( self, dc ):
        
        ( x, y ) = self.GetClientSize()
        
        background_brush = wx.Brush( wx.Colour( *HC.options[ 'gui_colours' ][ 'media_background' ] ) )
        
        dc.SetBackground( background_brush )
        
        dc.Clear() # gcdc doesn't support clear
        
        dc = wx.GCDC( dc )
        
        center_x = x / 2
        center_y = y / 2
        radius = min( center_x, center_y ) - 5
        
        dc.SetPen( wx.TRANSPARENT_PEN )
        
        dc.SetBrush( wx.Brush( wx.Colour( 235, 235, 235 ) ) )
        
        dc.DrawCircle( center_x, center_y, radius )
        
        dc.SetBrush( background_brush )
        
        m = ( 2 ** 0.5 ) / 2 # 45 degree angle
        
        half_radius = radius / 2
        
        angle_half_radius = m * half_radius
        
        points = []
        
        points.append( ( center_x - angle_half_radius, center_y - angle_half_radius ) )
        points.append( ( center_x + half_radius, center_y ) )
        points.append( ( center_x - angle_half_radius, center_y + angle_half_radius ) )
        
        dc.DrawPolygon( points )
        
        #
        
        dc.SetPen( wx.Pen( wx.Colour( 215, 215, 215 ) ) )
        
        dc.SetBrush( wx.TRANSPARENT_BRUSH )
        
        dc.DrawRectangle( 0, 0, x, y )
        
        self._dirty = False
        
    
    def EventEraseBackground( self, event ): pass
    
    def EventPaint( self, event ):
        
        dc = wx.BufferedPaintDC( self, self._canvas_bmp )
        
        if self._dirty:
            
            self._Redraw( dc )
            
        
    
    def EventResize( self, event ):
        
        ( my_width, my_height ) = self.GetClientSize()
        
        ( current_bmp_width, current_bmp_height ) = self._canvas_bmp.GetSize()
        
        if my_width != current_bmp_width or my_height != current_bmp_height:
            
            if my_width > 0 and my_height > 0:
                
                self._canvas_bmp = wx.EmptyBitmap( my_width, my_height, 24 )
                
                self._dirty = True
                
                self.Refresh()
                
            
        
    
class OpenExternallyButton( wx.Button ):
    
    def __init__( self, parent, media ):
        
        wx.Button.__init__( self, parent, label = 'open externally', size = OPEN_EXTERNALLY_BUTTON_SIZE )
        
        self.SetCursor( wx.StockCursor( wx.CURSOR_ARROW ) )
        
        self._media = media
        
        self.Bind( wx.EVT_BUTTON, self.EventButton )
        
    
    def EventButton( self, event ):
        
        hash = self._media.GetHash()
        mime = self._media.GetMime()
        
        client_files_manager = HydrusGlobals.client_controller.GetClientFilesManager()
        
        path = client_files_manager.GetFilePath( hash, mime )
        
        HydrusPaths.LaunchFile( path )
        
    
class StaticImage( wx.Window ):
    
    def __init__( self, parent, media, image_cache, initial_size, initial_position ):
        
        wx.Window.__init__( self, parent, size = initial_size, pos = initial_position )
        
        self._dirty = True
        
        self._media = media
        self._image_cache = image_cache
        self._image_container = self._image_cache.GetImage( self._media, initial_size )
        
        self._is_rendered = False
        
        ( initial_width, initial_height ) = initial_size
        
        self._canvas_bmp = wx.EmptyBitmap( initial_width, initial_height, 24 )
        
        self._timer_render_wait = wx.Timer( self, id = ID_TIMER_RENDER_WAIT )
        
        self.Bind( wx.EVT_PAINT, self.EventPaint )
        self.Bind( wx.EVT_SIZE, self.EventResize )
        self.Bind( wx.EVT_TIMER, self.TIMEREventRenderWait, id = ID_TIMER_RENDER_WAIT )
        self.Bind( wx.EVT_MOUSE_EVENTS, self.EventPropagateMouse )
        self.Bind( wx.EVT_ERASE_BACKGROUND, self.EventEraseBackground )
        
        if not self._image_container.IsRendered():
            
            self._timer_render_wait.Start( 16, wx.TIMER_CONTINUOUS )
            
        
    
    def _Redraw( self, dc ):
        
        dc.SetBackground( wx.Brush( wx.Colour( *HC.options[ 'gui_colours' ][ 'media_background' ] ) ) )
        
        dc.Clear()
        
        if self._image_container.IsRendered():
            
            hydrus_bitmap = self._image_container.GetHydrusBitmap()
            
            ( my_width, my_height ) = self._canvas_bmp.GetSize()
            
            ( frame_width, frame_height ) = hydrus_bitmap.GetSize()
            
            if frame_height != my_height:
                
                image = hydrus_bitmap.GetWxImage()
                
                image = image.Scale( my_width, my_height, wx.IMAGE_QUALITY_HIGH )
                
                wx_bitmap = wx.BitmapFromImage( image )
                
                wx.CallAfter( image.Destroy )
                
            else:
                
                wx_bitmap = hydrus_bitmap.GetWxBitmap()
                
            
            dc.DrawBitmap( wx_bitmap, 0, 0 )
            
            wx.CallAfter( wx_bitmap.Destroy )
            
            self._is_rendered = True
            
        
        self._dirty = False
        
    
    def _SetDirty( self ):
        
        self._dirty = True
        
        self.Refresh()
        
    
    def EventEraseBackground( self, event ):
        
        pass
        
    
    def EventPaint( self, event ):
        
        dc = wx.BufferedPaintDC( self, self._canvas_bmp )
        
        if self._dirty:
            
            self._Redraw( dc )
            
        
    
    def EventPropagateMouse( self, event ):
        
        screen_position = self.ClientToScreen( event.GetPosition() )
        ( x, y ) = self.GetParent().ScreenToClient( screen_position )
        
        event.SetX( x )
        event.SetY( y )
        
        event.ResumePropagation( 1 )
        event.Skip()
        
    
    def EventResize( self, event ):
        
        ( my_width, my_height ) = self.GetClientSize()
        
        ( current_bmp_width, current_bmp_height ) = self._canvas_bmp.GetSize()
        
        if my_width != current_bmp_width or my_height != current_bmp_height:
            
            if my_width > 0 and my_height > 0:
                
                ( image_width, image_height ) = self._image_container.GetSize()
                
                we_just_zoomed_in = my_width > image_width or my_height > image_height
                
                if we_just_zoomed_in and self._image_container.IsScaled():
                    
                    self._image_container = self._image_cache.GetImage( self._media )
                    
                
                wx.CallAfter( self._canvas_bmp.Destroy )
                
                self._canvas_bmp = wx.EmptyBitmap( my_width, my_height, 24 )
                
                self._SetDirty()
                
                if not self._image_container.IsRendered():
                    
                    self._timer_render_wait.Start( 16, wx.TIMER_CONTINUOUS )
                    
                
            
        
    
    def IsRendered( self ):
        
        return self._is_rendered
        
    
    def TIMEREventRenderWait( self, event ):
        
        try:
            
            if self._image_container.IsRendered():
                
                self._SetDirty()
                
                self._timer_render_wait.Stop()
                
            
        except wx.PyDeadObjectError:
            
            self._timer_render_wait.Stop()
            
        except:
            
            self._timer_render_wait.Stop()
            
            raise
            
        
    