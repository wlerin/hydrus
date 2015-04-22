import cProfile
import HydrusConstants as HC
import HydrusData
import HydrusExceptions
import HydrusGlobals
import os
import Queue
import sqlite3
import sys
import traceback
import time

class HydrusDB( object ):
    
    DB_NAME = 'hydrus'
    READ_WRITE_ACTIONS = []
    WRITE_SPECIAL_ACTIONS = []
    
    def __init__( self ):
        
        self._local_shutdown = False
        self._loop_finished = False
        
        self._db_path = HC.DB_DIR + os.path.sep + self.DB_NAME + '.db'
        
        self._jobs = Queue.PriorityQueue()
        self._pubsubs = []
        
        self._currently_doing_job = False
        
        if os.path.exists( self._db_path ):
            
            # open and close to clean up in case last session didn't close well
            
            self._InitDB()
            self._CloseDBCursor()
            
        
        self._InitDB()
        
        ( version, ) = self._c.execute( 'SELECT version FROM version;' ).fetchone()
        
        if version < HC.SOFTWARE_VERSION - 50: raise Exception( 'Your current version of hydrus ' + HydrusData.ToString( version ) + ' is too old for this version ' + HydrusData.ToString( HC.SOFTWARE_VERSION ) + ' to update. Please try updating with version ' + HydrusData.ToString( version + 45 ) + ' or earlier first.' )
        
        while version < HC.SOFTWARE_VERSION:
            
            time.sleep( 2 )
            
            try: self._c.execute( 'BEGIN IMMEDIATE' )
            except Exception as e:
                
                raise HydrusExceptions.DBAccessException( HydrusData.ToString( e ) )
                
            
            try:
                
                self._UpdateDB( version )
                
                self._c.execute( 'COMMIT' )
                
            except:
                
                self._c.execute( 'ROLLBACK' )
                
                raise Exception( 'Updating the ' + self.DB_NAME + ' db to version ' + HydrusData.ToString( version + 1 ) + ' caused this error:' + os.linesep + traceback.format_exc() )
                
            
            ( version, ) = self._c.execute( 'SELECT version FROM version;' ).fetchone()
            
        
        self._InitCaches()
        
        self._CloseDBCursor()
        
    
    def _CloseDBCursor( self ):
        
        self._c.close()
        self._db.close()
        
        del self._db
        del self._c
        
    
    def _CreateDB( self ):
        
        raise NotImplementedError()
        
    
    def _GetRowCount( self ):
        
        row_count = self._c.rowcount
        
        if row_count == -1: return 0
        else: return row_count
        
    
    def _GetSiteId( self, name ):
        
        result = self._c.execute( 'SELECT site_id FROM imageboard_sites WHERE name = ?;', ( name, ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT INTO imageboard_sites ( name ) VALUES ( ? );', ( name, ) )
            
            site_id = self._c.lastrowid
            
        else: ( site_id, ) = result
        
        return site_id
        
    
    def _InitCaches( self ):
        
        raise NotImplementedError()
        
    
    def _InitDB( self ):
        
        if not os.path.exists( self._db_path ): create_db = True
        else: create_db = False
        
        self._InitDBCursor()
        
        if create_db:
            
            self._CreateDB()
            
        
    
    def _InitDBCursor( self ):
        
        self._db = sqlite3.connect( self._db_path, isolation_level = None, detect_types = sqlite3.PARSE_DECLTYPES )
        
        self._db.create_function( 'hydrus_hamming', 2, HydrusData.GetHammingDistance )
        
        self._c = self._db.cursor()
        
        self._c.execute( 'PRAGMA cache_size = 10000;' )
        self._c.execute( 'PRAGMA foreign_keys = ON;' )
        
    
    def _ManageDBError( self, job, e ):
        
        raise NotImplementedError()
        
    
    def _ProcessJob( self, job ):
        
        HydrusGlobals.pubsub.pub( 'db_locked_status', 'db locked' )
        
        job_type = job.GetType()
        
        action = job.GetAction()
        
        args = job.GetArgs()
        
        kwargs = job.GetKWArgs()
        
        in_transaction = False
        
        try:
            
            if job_type == 'read': self._c.execute( 'BEGIN DEFERRED' )
            elif job_type in ( 'read_write', 'write' ): self._c.execute( 'BEGIN IMMEDIATE' )
            
            if job_type != 'write_special': in_transaction = True
            
            if job_type in ( 'read', 'read_write' ): result = self._Read( action, *args, **kwargs )
            elif job_type in ( 'write', 'write_special' ): result = self._Write( action, *args, **kwargs )
            
            if job_type != 'write_special': self._c.execute( 'COMMIT' )
            
            for ( topic, args, kwargs ) in self._pubsubs: HydrusGlobals.pubsub.pub( topic, *args, **kwargs )
            
            if job.IsSynchronous(): job.PutResult( result )
            
        except Exception as e:
            
            if in_transaction: self._c.execute( 'ROLLBACK' )
            
            self._ManageDBError( job, e )
            
        
        HydrusGlobals.pubsub.pub( 'db_locked_status', '' )
        
    
    def _Read( self, action, *args, **kwargs ):
        
        raise NotImplementedError()
        
    
    def _ReportStatus( self, text ):
        
        print( text )
        
    
    def _UpdateDB( self, version ):
        
        raise NotImplementedError()
        
    
    def _Write( self, action, *args, **kwargs ):
        
        raise NotImplementedError()
        
    
    def pub_after_commit( self, topic, *args, **kwargs ): self._pubsubs.append( ( topic, args, kwargs ) )
    
    def LoopIsFinished( self ): return self._loop_finished
    
    def MainLoop( self ):
        
        self._InitDBCursor() # have to reinitialise because the thread id has changed
        
        error_count = 0
        
        while not ( ( self._local_shutdown or HydrusGlobals.shutdown ) and self._jobs.empty() ):
            
            try:
                
                ( priority, job ) = self._jobs.get( timeout = 1 )
                
                self._currently_doing_job = True
                
                self._pubsubs = []
                
                try:
                    
                    if HydrusGlobals.db_profile_mode:
                        
                        HydrusData.ShowText( 'Profiling ' + job.GetType() + ' ' + job.GetAction() )
                        
                        profile = cProfile.Profile()
                        
                        profile.runctx( 'self._ProcessJob( job )', globals(), locals() )
                        
                        profile.print_stats( sort = 'tottime' )
                        
                    else:
                        
                        self._ProcessJob( job )
                        
                    
                    error_count = 0
                    
                except:
                    
                    error_count += 1
                    
                    if error_count > 5: raise
                    
                    self._jobs.put( ( priority, job ) ) # couldn't lock db; put job back on queue
                    
                    time.sleep( 5 )
                    
                
                self._currently_doing_job = False
                
            except Queue.Empty: pass # no jobs this second; let's see if we should shutdown
            
        
        self._CloseDBCursor()
        
        self._loop_finished = True
        
    
    def Read( self, action, priority, *args, **kwargs ):
        
        if action in self.READ_WRITE_ACTIONS: job_type = 'read_write'
        else: job_type = 'read'
        
        synchronous = True
        
        job = HydrusData.JobDatabase( action, job_type, synchronous, *args, **kwargs )
        
        if HydrusGlobals.shutdown: raise Exception( 'Application has shutdown!' )
        
        self._jobs.put( ( priority + 1, job ) ) # +1 so all writes of equal priority can clear out first
        
        if synchronous: return job.GetResult()
        
    
    def Shutdown( self ): self._local_shutdown = True
    
    def Write( self, action, priority, synchronous, *args, **kwargs ):
        
        if action in self.WRITE_SPECIAL_ACTIONS: job_type = 'write_special'
        else: job_type = 'write'
        
        job = HydrusData.JobDatabase( action, job_type, synchronous, *args, **kwargs )
        
        if HydrusGlobals.shutdown: raise Exception( 'Application has shutdown!' )
        
        self._jobs.put( ( priority, job ) )
        
        if synchronous: return job.GetResult()
        
    