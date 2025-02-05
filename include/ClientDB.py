import ClientData
import ClientDefaults
import ClientFiles
import ClientImporting
import ClientMedia
import ClientRatings
import ClientThreading
import collections
import hashlib
import httplib
import itertools
import json
import HydrusConstants as HC
import HydrusDB
import ClientDownloading
import ClientImageHandling
import HydrusEncryption
import HydrusExceptions
import HydrusFileHandling
import HydrusImageHandling
import HydrusNATPunch
import HydrusPaths
import HydrusSerialisable
import HydrusTagArchive
import HydrusTags
import HydrusThreading
import ClientConstants as CC
import lz4
import os
import Queue
import random
import shutil
import sqlite3
import stat
import sys
import threading
import time
import traceback
import wx
import yaml
import HydrusData
import ClientSearch
import HydrusGlobals

YAML_DUMP_ID_SINGLE = 0
YAML_DUMP_ID_REMOTE_BOORU = 1
YAML_DUMP_ID_FAVOURITE_CUSTOM_FILTER_ACTIONS = 2
YAML_DUMP_ID_GUI_SESSION = 3
YAML_DUMP_ID_IMAGEBOARD = 4
YAML_DUMP_ID_IMPORT_FOLDER = 5
YAML_DUMP_ID_EXPORT_FOLDER = 6
YAML_DUMP_ID_SUBSCRIPTION = 7
YAML_DUMP_ID_LOCAL_BOORU = 8
'''
class MessageDB( object ):
    
    def _AddContact( self, contact ):
        
        ( public_key, name, host, port ) = contact.GetInfo()
        
        contact_key = contact.GetContactKey()
        
        if public_key is not None: contact_key = sqlite3.Binary( contact_key )
        
        self._c.execute( 'INSERT OR IGNORE INTO contacts ( contact_key, public_key, name, host, port ) VALUES ( ?, ?, ?, ?, ? );', ( contact_key, public_key, name, host, port ) )
        
    
    def _AddMessage( self, transport_message, serverside_message_key = None, forced_status = None ):
        
        ( contact_from, contacts_to, message_key, conversation_key, timestamp, subject, body, files ) = transport_message.GetInfo()
        
        if contact_from is None or contact_from.GetName() == 'Anonymous':
            
            contact_id_from = 1
            
        else:
            
            contact_id_from = self._GetContactId( contact_from )
            
            # changes whatever they want to say their name and public key is to whatever we prefer it to be
            contact_from = self._GetContact( contact_id_from )
            
            public_key = contact_from.GetPublicKey()
            
            try: transport_message.VerifyIsFromCorrectPerson( public_key )
            except:
                
                HydrusData.ShowText( 'received a message that did not verify' )
                
                return
                
            
        
        conversation_id = self._GetConversationId( conversation_key, subject )
        
        message_id = self._GetMessageId( message_key )
        
        result = self._c.execute( 'SELECT 1 FROM messages WHERE message_id = ?;', ( message_id, ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT OR IGNORE INTO messages ( conversation_id, message_id, contact_id_from, timestamp ) VALUES ( ?, ?, ?, ? );', ( conversation_id, message_id, contact_id_from, timestamp ) )
            
            self._c.execute( 'INSERT OR IGNORE INTO message_bodies ( docid, body ) VALUES ( ?, ? );', ( message_id, body ) )
            
            attachment_hashes = []
            
            if len( files ) > 0:
                
                for file in files:
                    
                    ( os_file_handle, temp_path ) = HydrusPaths.GetTempPath()
                    
                    try:
                        
                        with open( temp_path, 'wb' ) as f: f.write( file )
                        
                        ( result, hash ) = self._ImportFile( temp_path, override_deleted = True ) # what if the file fails?
                        
                        attachment_hashes.append( hash )
                        
                    finally:
                        
                        HydrusPaths.CleanUpTempPath( os_file_handle, temp_path )
                        
                    
                
                hash_ids = self._GetHashIds( attachment_hashes )
                
                self._c.executemany( 'INSERT OR IGNORE INTO message_attachments ( message_id, hash_id ) VALUES ( ?, ? );', [ ( message_id, hash_id ) for hash_id in hash_ids ] )
                
            
            if forced_status is None: status = 'sent'
            else: status = forced_status
            
            status_id = self._GetStatusId( status )
            
            inboxable_contact_ids = { id for ( id, ) in self._c.execute( 'SELECT contact_id FROM message_depots;' ) }
            
            inbox = False
            
            for contact_to in contacts_to:
                
                contact_id_to = self._GetContactId( contact_to )
                
                if contact_id_to in inboxable_contact_ids:
                    
                    self._c.execute( 'INSERT OR IGNORE INTO message_inbox ( message_id ) VALUES ( ? );', ( message_id, ) )
                    
                    inbox = True
                    
                
                self._c.execute( 'INSERT OR IGNORE INTO message_destination_map ( message_id, contact_id_to, status_id ) VALUES ( ?, ?, ? );', ( message_id, contact_id_to, status_id ) )
                
            
            destinations = [ ( contact_to, status ) for contact_to in contacts_to ]
            
            message = ClientConstantsMessages.Message( message_key, contact_from, destinations, timestamp, body, attachment_hashes, inbox )
            
            self.pub_after_commit( 'new_message', conversation_key, message )
            
        
        if serverside_message_key is not None:
            
            serverside_message_id = self._GetMessageId( serverside_message_key )
            
            self._c.execute( 'DELETE FROM message_downloads WHERE message_id = ?;', ( serverside_message_id, ) )
            
        
    
    def _AddMessageInfoSince( self, service_key, serverside_message_keys, statuses, new_last_check ):
        
        # message_keys
        
        service_id = self._GetServiceId( service_key )
        
        serverside_message_ids = set( self._GetMessageIds( serverside_message_keys ) )
        
        self._c.executemany( 'INSERT OR IGNORE INTO message_downloads ( service_id, message_id ) VALUES ( ?, ? );', [ ( service_id, serverside_message_id ) for serverside_message_id in serverside_message_ids ] )
        
        # statuses
        
        message_keys_dict = {}
        statuses_dict = {}
        
        inserts = []
        
        for ( message_key, contact_key, status ) in statuses:
            
            if message_key in message_keys_dict: message_id = message_keys_dict[ message_key ]
            else:
                
                message_id = self._GetMessageId( message_key )
                
                message_keys_dict[ message_key ] = message_id
                
            
            if status in statuses_dict: status_id = statuses_dict[ status ]
            else:
                
                status_id = self._GetStatusId( status )
                
                statuses_dict[ status ] = status_id
                
            
            inserts.append( ( message_id, sqlite3.Binary( contact_key ), status_id ) )
            
        
        # replace is important here
        self._c.executemany( 'INSERT OR REPLACE INTO incoming_message_statuses ( message_id, contact_key, status_id ) VALUES ( ?, ?, ? );', inserts )
        
        # finally:
        
        self._c.execute( 'UPDATE message_depots SET last_check = ? WHERE service_id = ?;', ( new_last_check, service_id ) )
        
    
    def _ArchiveConversation( self, conversation_key ):
        
        conversation_id = self._GetMessageId( conversation_key )
        
        message_ids = [ message_id for ( message_id, ) in self._c.execute( 'SELECT message_id FROM messages WHERE conversation_id = ?;', ( conversation_id, ) ) ]
        
        self._c.execute( 'DELETE FROM message_inbox WHERE message_id IN ' + HydrusData.SplayListForDB( message_ids ) + ';' )
        
        self.pub_after_commit( 'archive_conversation_data', conversation_key )
        self.pub_after_commit( 'archive_conversation_gui', conversation_key )
        
        self._DoStatusNumInbox()
        
    
    def _AssociateContact( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        service = self._GetService( service_id )
        
        private_key = service.GetPrivateKey()
        
        public_key = HydrusEncryption.GetPublicKey( private_key )
        
        contact_key = hashlib.sha256( public_key ).digest()
        
        contact_id = self._GetContactId( service_id )
        
        self._c.execute( 'UPDATE contacts SET contact_key = ?, public_key = ? WHERE contact_id = ?;', ( sqlite3.Binary( contact_key ), public_key, contact_id ) )
        
    
    def _DeleteConversation( self, conversation_key ):
        
        conversation_id = self._GetMessageId( conversation_key )
        
        message_ids = [ message_id for ( message_id, ) in self._c.execute( 'SELECT message_id FROM messages WHERE conversation_id = ?;', ( conversation_id, ) ) ]
        
        splayed_message_ids = HydrusData.SplayListForDB( message_ids )
        
        self._c.execute( 'DELETE FROM message_keys WHERE message_id IN ' + splayed_message_ids + ';' )
        self._c.execute( 'DELETE FROM message_bodies WHERE docid IN ' + splayed_message_ids + ';' )
        self._c.execute( 'DELETE FROM conversation_subjects WHERE docid IN ' + splayed_message_ids + ';' )
        
        self.pub_after_commit( 'delete_conversation_data', conversation_key )
        self.pub_after_commit( 'delete_conversation_gui', conversation_key )
        
        self._DoStatusNumInbox()
        
    
    def _DeleteDraft( self, draft_key ):
        
        message_id = self._GetMessageId( draft_key )
        
        self._c.execute( 'DELETE FROM message_keys WHERE message_id = ?;', ( message_id, ) )
        self._c.execute( 'DELETE FROM message_bodies WHERE docid = ?;', ( message_id, ) )
        self._c.execute( 'DELETE FROM conversation_subjects WHERE docid = ?;', ( message_id, ) )
        
        self.pub_after_commit( 'delete_draft_data', draft_key )
        self.pub_after_commit( 'delete_draft_gui', draft_key )
        self.pub_after_commit( 'notify_check_messages' )
        
    
    def _DoMessageQuery( self, query_key, search_context ):
        
        identity = search_context.GetIdentity()
        
        name = identity.GetName()
        
        contact_id = self._GetContactId( identity )
        
        system_predicates = search_context.GetSystemPredicates()
        
        ( inbox, archive, draft, status, contact_from, contact_to, contact_started, min_timestamp, max_timestamp ) = system_predicates.GetInfo()
        
        if draft:
            
            draft_ids = [ message_id for ( message_id, ) in self._c.execute( 'SELECT message_id FROM messages, message_drafts USING ( message_id ) WHERE contact_id_from = ?;', ( contact_id, ) ) ]
            
            query_message_ids = draft_ids
            
        else:
            
            sql_predicates = [ '( contact_id_from = ' + str( contact_id ) + ' OR contact_id_to = ' + str( contact_id ) + ' )' ]
            
            if name != 'Anonymous':
                
                service = self._GetService( identity )
                
                if not service.ReceivesAnon(): sql_predicates.append( 'contact_id_from != 1' )
                
            
            if status is not None:
                
                if status == 'unread': status = 'sent'
                
                status_id = self._GetStatusId( status )
                
                sql_predicates.append( '( contact_id_to = ' + str( contact_id ) + ' AND status_id = ' + str( status_id ) + ')' )
                
            
            if contact_from is not None:
                
                contact_id_from = self._GetContactId( contact_from )
                
                sql_predicates.append( 'contact_id_from = ' + str( contact_id_from ) )
                
            
            if contact_to is not None:
                
                contact_id_to = self._GetContactId( contact_to )
                
                sql_predicates.append( 'contact_id_to = ' + str( contact_id_to ) )
                
            
            if contact_started is not None:
                
                contact_id_started = self._GetContactId( contact_started )
                
                sql_predicates.append( 'conversation_id = message_id AND contact_id_from = ' + str( contact_id_started ) )
                
            
            if min_timestamp is not None: sql_predicates.append( 'timestamp >= ' + str( min_timestamp ) )
            if max_timestamp is not None: sql_predicates.append( 'timestamp <= ' + str( max_timestamp ) )
            
            query_message_ids = { message_id for ( message_id, ) in self._c.execute( 'SELECT message_id FROM messages, message_destination_map USING ( message_id ) WHERE ' + ' AND '.join( sql_predicates ) + ';' ) }
            
            if inbox or archive:
                
                inbox_ids = [ message_id for ( message_id, ) in self._c.execute( 'SELECT message_id FROM message_inbox, message_destination_map USING ( message_id ) WHERE contact_id_to = ?;', ( contact_id, ) ) ]
                
                if inbox: query_message_ids.intersection_update( inbox_ids )
                elif archive: query_message_ids.difference_update( inbox_ids )
                
            
        
        for term in search_context.GetTermsToInclude():
            
            body_query_ids = [ message_id for ( message_id, ) in self._c.execute( 'SELECT docid FROM message_bodies WHERE body MATCH ?;', ( term, ) ) ]
            subject_query_ids = [ message_id for ( message_id, ) in self._c.execute( 'SELECT docid FROM conversation_subjects WHERE subject MATCH ?;', ( term, ) ) ]
            
            query_message_ids.intersection_update( body_query_ids + subject_query_ids )
            
        
        for term in search_context.GetTermsToExclude():
            
            body_query_ids = [ message_id for ( message_id, ) in self._c.execute( 'SELECT docid FROM message_bodies WHERE body MATCH ?;', ( term, ) ) ]
            subject_query_ids = [ message_id for ( message_id, ) in self._c.execute( 'SELECT docid FROM conversation_subjects WHERE subject MATCH ?;', ( term, ) ) ]
            
            query_message_ids.difference_update( body_query_ids + subject_query_ids )
            
        
        conversations = self._GetConversations( search_context, query_message_ids )
        
        self.pub_after_commit( 'message_query_done', query_key, conversations )
        
    
    def _DoStatusNumInbox( self ):
        
        convo_ids = { id for ( id, ) in self._c.execute( 'SELECT conversation_id FROM messages, message_inbox USING ( message_id );' ) }
        
        num_inbox = len( convo_ids )
        
        if num_inbox == 0: inbox_string = 'message inbox empty'
        else: inbox_string = str( num_inbox ) + ' in message inbox'
        
        self.pub_after_commit( 'inbox_status', inbox_string )
        
    
    def _DraftMessage( self, draft_message ):
        
        ( draft_key, conversation_key, subject, contact_from, contact_names_to, recipients_visible, body, attachment_hashes ) = draft_message.GetInfo()
        
        old_message_id = self._GetMessageId( draft_key )
        
        self._c.execute( 'DELETE FROM message_keys WHERE message_id = ?;', ( old_message_id, ) )
        self._c.execute( 'DELETE FROM message_bodies WHERE docid = ?;', ( old_message_id, ) )
        self._c.execute( 'DELETE FROM conversation_subjects WHERE docid = ?;', ( old_message_id, ) )
        
        message_id = self._GetMessageId( draft_key )
        
        conversation_id = self._GetConversationId( conversation_key, subject )
        
        contact_id_from = self._GetContactId( contact_from )
        
        self._c.execute( 'INSERT INTO messages ( conversation_id, message_id, contact_id_from, timestamp ) VALUES ( ?, ?, ?, ? );', ( conversation_id, message_id, contact_id_from, None ) )
        
        self._c.execute( 'INSERT INTO message_bodies ( docid, body ) VALUES ( ?, ? );', ( message_id, body ) )
        
        status_id = self._GetStatusId( 'draft' )
        
        contact_ids_to = [ self._GetContactId( contact_name_to ) for contact_name_to in contact_names_to ]
        
        self._c.executemany( 'INSERT INTO message_destination_map ( message_id, contact_id_to, status_id ) VALUES ( ?, ?, ? );', [ ( message_id, contact_id_to, status_id ) for contact_id_to in contact_ids_to ] )
        
        self._c.execute( 'INSERT INTO message_drafts ( message_id, recipients_visible ) VALUES ( ?, ? );', ( message_id, recipients_visible ) )
        
        hash_ids = self._GetHashIds( attachment_hashes )
        
        self._c.executemany( 'INSERT INTO message_attachments ( message_id, hash_id ) VALUES ( ?, ? );', [ ( message_id, hash_id ) for hash_id in hash_ids ] )
        
        self.pub_after_commit( 'draft_saved', draft_key, draft_message )
        
    
    def _FlushMessageStatuses( self ):
        
        incoming_message_statuses = HydrusData.BuildKeyToListDict( [ ( message_id, ( contact_key, status_id ) ) for ( message_id, contact_key, status_id ) in self._c.execute( 'SELECT message_id, contact_key, status_id FROM incoming_message_statuses, messages USING ( message_id );' ) ] )
        
        for ( message_id, status_infos ) in incoming_message_statuses.items():
            
            for ( contact_key, status_id ) in status_infos:
                
                try:
                    
                    contact_id_to = self._GetContactId( contact_key )
                    
                    self._c.execute( 'INSERT OR REPLACE INTO message_destination_map ( message_id, contact_id_to, status_id ) VALUES ( ?, ?, ? );', ( message_id, contact_id_to, status_id ) )
                    
                except: pass
                
            
            self._c.execute( 'DELETE FROM incoming_message_statuses WHERE message_id = ?;', ( message_id, ) )
            
            message_key = self._GetMessageKey( message_id )
            
            status_updates = [ ( contact_key, self._GetStatus( status_id ) ) for ( contact_key, status_id ) in status_infos ]
            
            self.pub_after_commit( 'message_statuses_data', message_key, status_updates )
            self.pub_after_commit( 'message_statuses_gui', message_key, status_updates )
            
        
    
    def _GetAutocompleteContacts( self, half_complete_name, name_to_exclude = None ):
        
        # expand this later to do groups as well
        
        names = [ name for ( name, ) in self._c.execute( 'SELECT name FROM contacts WHERE name LIKE ? AND name != ? AND public_key NOTNULL;', ( half_complete_name + '%', 'Anonymous' ) ) ]
        
        if name_to_exclude is not None: names = [ name for name in names if name != name_to_exclude ]
        
        return names
        
    
    def _GetContact( self, parameter ):
        
        if type( parameter ) == int: ( public_key, name, host, port ) = self._c.execute( 'SELECT public_key, name, host, port FROM contacts WHERE contact_id = ?;', ( parameter, ) ).fetchone()
        elif type( parameter ) in ( str, unicode ):
            try: ( public_key, name, host, port ) = self._c.execute( 'SELECT public_key, name, host, port FROM contacts WHERE contact_key = ?;', ( sqlite3.Binary( parameter ), ) ).fetchone()
            except: ( public_key, name, host, port ) = self._c.execute( 'SELECT public_key, name, host, port FROM contacts WHERE name = ?;', ( parameter, ) ).fetchone()
        
        return ClientConstantsMessages.Contact( public_key, name, host, port )
        
    
    def _GetContactId( self, parameter ):
        
        if type( parameter ) in ( str, unicode ): 
            
            if parameter == 'Anonymous': return 1
            
            try: ( contact_id, ) = self._c.execute( 'SELECT contact_id FROM contacts WHERE contact_key = ?;', ( sqlite3.Binary( parameter ), ) ).fetchone()
            except: ( contact_id, ) = self._c.execute( 'SELECT contact_id FROM contacts WHERE name = ?;', ( parameter, ) ).fetchone()
            
        elif type( parameter ) == int: ( contact_id, ) = self._c.execute( 'SELECT contact_id FROM contacts, message_depots USING ( contact_id ) WHERE service_id = ?;', ( parameter, ) ).fetchone()
        elif type( parameter ) == ClientConstantsMessages.Contact:
            
            contact_key = parameter.GetContactKey()
            
            name = parameter.GetName()
            
            if name == 'Anonymous': return 1
            
            if contact_key is not None:
                
                result = self._c.execute( 'SELECT contact_id FROM contacts WHERE contact_key = ?;', ( sqlite3.Binary( contact_key ), ) ).fetchone()
                
                if result is None:
                    
                    # we have a new contact from an outside source!
                    # let's generate a name that'll fit into the db
                    
                    while self._c.execute( 'SELECT 1 FROM contacts WHERE name = ?;', ( name, ) ).fetchone() is not None: name += str( random.randint( 0, 9 ) )
                    
                
            else:
                
                # one of our user-entered contacts that doesn't have a public key yet
                
                result = self._c.execute( 'SELECT contact_id FROM contacts WHERE name = ?;', ( name, ) ).fetchone()
                
            
            if result is None:
                
                public_key = parameter.GetPublicKey()
                ( host, port ) = parameter.GetAddress()
                
                if public_key is not None: contact_key = sqlite3.Binary( contact_key )
                
                self._c.execute( 'INSERT INTO contacts ( contact_key, public_key, name, host, port ) VALUES ( ?, ?, ?, ?, ? );', ( contact_key, public_key, name, host, port ) )
                
                contact_id = self._c.lastrowid
                
            else: ( contact_id, ) = result
            
        
        return contact_id
        
    
    def _GetContactIdsToContacts( self, contact_ids ): return { contact_id : ClientConstantsMessages.Contact( public_key, name, host, port ) for ( contact_id, public_key, name, host, port ) in self._c.execute( 'SELECT contact_id, public_key, name, host, port FROM contacts WHERE contact_id IN ' + HydrusData.SplayListForDB( contact_ids ) + ';' ) }
    
    def _GetContactNames( self ): return [ name for ( name, ) in self._c.execute( 'SELECT name FROM contacts;' ) ]
    
    def _GetConversations( self, search_context, query_message_ids ):
        
        system_predicates = search_context.GetSystemPredicates()
        
        conversation_ids = { conversation_id for ( conversation_id, ) in self._c.execute( 'SELECT conversation_id FROM messages WHERE message_id IN ' + HydrusData.SplayListForDB( query_message_ids ) + ';' ) }
        
        splayed_conversation_ids = HydrusData.SplayListForDB( conversation_ids )
        
        conversation_infos = self._c.execute( 'SELECT message_id, message_key, subject FROM message_keys, conversation_subjects ON message_id = conversation_subjects.docid WHERE message_id IN ' + splayed_conversation_ids + ';' ).fetchall()
        
        conversation_ids_to_message_infos = HydrusData.BuildKeyToListDict( [ ( conversation_id, ( message_id, contact_id_from, timestamp, body ) ) for ( conversation_id, message_id, contact_id_from, timestamp, body ) in self._c.execute( 'SELECT conversation_id, message_id, contact_id_from, timestamp, body FROM messages, message_bodies ON message_id = message_bodies.docid WHERE conversation_id IN ' + splayed_conversation_ids + ' ORDER BY timestamp ASC;' ) ] )
        
        message_ids = []
        contact_ids = set()
        
        for message_infos in conversation_ids_to_message_infos.values():
            
            message_ids.extend( [ message_id for ( message_id, contact_id_from, timestamp, body ) in message_infos ] )
            contact_ids.update( [ contact_id_from for ( message_id, contact_id_from, timestamp, body ) in message_infos ] )
            
        
        message_ids_to_message_keys = self._GetMessageIdsToMessageKeys( message_ids )
        
        splayed_message_ids = HydrusData.SplayListForDB( message_ids )
        
        message_ids_to_destination_ids = HydrusData.BuildKeyToListDict( [ ( message_id, ( contact_id_to, status_id ) ) for ( message_id, contact_id_to, status_id ) in self._c.execute( 'SELECT message_id, contact_id_to, status_id FROM message_destination_map WHERE message_id IN ' + splayed_message_ids + ';' ) ] )
        
        messages_ids_to_recipients_visible = { message_id : recipients_visible for ( message_id, recipients_visible ) in self._c.execute( 'SELECT message_id, recipients_visible FROM message_drafts;' ) }
        
        status_ids = set()
        
        for destination_ids in message_ids_to_destination_ids.values():
            
            contact_ids.update( [ contact_id_to for ( contact_id_to, status_id ) in destination_ids ] )
            status_ids.update( [ status_id for ( contact_id_to, status_id ) in destination_ids ] )
            
        
        contact_ids_to_contacts = self._GetContactIdsToContacts( contact_ids )
        status_ids_to_statuses = self._GetStatusIdsToStatuses( status_ids )
        
        message_ids_to_hash_ids = HydrusData.BuildKeyToListDict( self._c.execute( 'SELECT message_id, hash_id FROM message_attachments WHERE message_id IN ' + splayed_message_ids + ';' ).fetchall() )
        
        hash_ids = set()
        
        for sub_hash_ids in message_ids_to_hash_ids.values(): hash_ids.update( sub_hash_ids )
        
        hash_ids_to_hashes = self._GetHashIdsToHashes( hash_ids )
        
        identity = search_context.GetIdentity()
        
        inbox_ids = { message_id for ( message_id, ) in self._c.execute( 'SELECT message_id FROM message_inbox;' ) }
        
        conversations = []
        
        for ( conversation_id, conversation_key, subject ) in conversation_infos:
            
            messages = []
            drafts = []
            
            can_add = False
            
            for ( message_id, contact_id_from, timestamp, body ) in conversation_ids_to_message_infos[ conversation_id ]:
                
                message_key = message_ids_to_message_keys[ message_id ]
                
                contact_from = contact_ids_to_contacts[ contact_id_from ]
                
                attachment_hashes = [ hash_ids_to_hashes[ hash_id ] for hash_id in message_ids_to_hash_ids[ message_id ] ]
                
                if system_predicates.Ok( len( attachment_hashes ) ): can_add = True
                
                attachment_hashes.sort()
                
                destination_ids = message_ids_to_destination_ids[ message_id ]
                
                if message_id in messages_ids_to_recipients_visible:
                    
                    # this is a draft
                    
                    contact_names_to = [ contact_ids_to_contacts[ contact_id_to ].GetName() for ( contact_id_to, status_id ) in destination_ids ]
                    
                    recipients_visible = messages_ids_to_recipients_visible[ message_id ]
                    
                    drafts.append( ClientConstantsMessages.DraftMessage( message_key, conversation_key, subject, contact_from, contact_names_to, recipients_visible, body, attachment_hashes ) )
                    
                else:
                    
                    inbox = message_id in inbox_ids
                    
                    destinations = [ ( contact_ids_to_contacts[ contact_id_to ], status_ids_to_statuses[ status_id ] ) for ( contact_id_to, status_id ) in destination_ids ]
                    
                    messages.append( ClientConstantsMessages.Message( message_key, contact_from, destinations, timestamp, body, attachment_hashes, inbox ) )
                    
                
            
            if can_add: conversations.append( ClientConstantsMessages.Conversation( identity, conversation_key, subject, messages, drafts, search_context ) )
            
        
        return conversations
        
    
    def _GetConversationId( self, conversation_key, subject ):
        
        result = self._c.execute( 'SELECT message_id FROM message_keys, conversation_subjects ON message_id = conversation_subjects.docid WHERE message_key = ?;', ( sqlite3.Binary( conversation_key ), ) ).fetchone()
        
        if result is None:
            
            conversation_id = self._GetMessageId( conversation_key )
            
            self._c.execute( 'INSERT INTO conversation_subjects ( docid, subject ) VALUES ( ?, ? );', ( conversation_id, subject ) )
            
        else: ( conversation_id, ) = result
        
        return conversation_id
        
    
    def _GetIdentities( self ):
        
        my_identities = [ ClientConstantsMessages.Contact( public_key, name, host, port ) for ( public_key, name, host, port ) in self._c.execute( 'SELECT public_key, name, host, port FROM contacts, message_depots USING ( contact_id ) ORDER BY name ASC;' ) ]
        
        return my_identities + [ self._GetContact( 'Anonymous' ) ]
        
    
    def _GetIdentitiesAndContacts( self ):
        
        contacts_info = self._c.execute( 'SELECT contact_id, public_key, name, host, port FROM contacts ORDER BY name ASC;' ).fetchall()
        
        identity_ids = { contact_id for ( contact_id, ) in self._c.execute( 'SELECT contact_id FROM message_depots;' ) }
        
        identities = [ ClientConstantsMessages.Contact( public_key, name, host, port ) for ( contact_id, public_key, name, host, port ) in contacts_info if contact_id in identity_ids ]
        contacts = [ ClientConstantsMessages.Contact( public_key, name, host, port ) for ( contact_id, public_key, name, host, port ) in contacts_info if contact_id not in identity_ids and name != 'Anonymous' ]
        
        contact_contact_ids = [ contact_id for ( contact_id, public_key, name, host, port ) in contacts_info if contact_id not in identity_ids and name != 'Anonymous' ]
        
        deletable_names = { name for ( name, ) in self._c.execute( 'SELECT name FROM contacts WHERE contact_id IN ' + HydrusData.SplayListForDB( contact_contact_ids ) + ' AND NOT EXISTS ( SELECT 1 FROM message_destination_map WHERE contact_id_to = contact_id ) AND NOT EXISTS ( SELECT 1 FROM messages WHERE contact_id_from = contact_id );' ) }
        
        return ( identities, contacts, deletable_names )
        
    
    def _GetMessageId( self, message_key ):
        
        result = self._c.execute( 'SELECT message_id FROM message_keys WHERE message_key = ?;', ( sqlite3.Binary( message_key ), ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT INTO message_keys ( message_key ) VALUES ( ? );', ( sqlite3.Binary( message_key ), ) )
            
            message_id = self._c.lastrowid
            
        else: ( message_id, ) = result
        
        return message_id
        
    
    def _GetMessageIds( self, message_keys ):
        
        message_ids = []
        
        if type( message_keys ) == type( set() ): message_keys = list( message_keys )
        
        for i in range( 0, len( message_keys ), 250 ): # there is a limit on the number of parameterised variables in sqlite, so only do a few at a time
            
            message_keys_subset = message_keys[ i : i + 250 ]
            
            message_ids.extend( [ message_id for ( message_id, ) in self._c.execute( 'SELECT message_id FROM message_keys WHERE message_key IN (' + ','.join( '?' * len( message_keys_subset ) ) + ');', [ sqlite3.Binary( message_key ) for message_key in message_keys_subset ] ) ] )
            
        
        if len( message_keys ) > len( message_ids ):
            
            if len( set( message_keys ) ) > len( message_ids ):
                
                # must be some new messages the db has not seen before, so let's generate them as appropriate
                
                message_ids = self._GetMessageIds( message_keys )
                
            
        
        return message_ids
        
    
    def _GetMessageIdsToMessages( self, message_ids ): return { message_id : message for ( message_id, message ) in self._c.execute( 'SELECT message_id, message FROM messages WHERE message_id IN ' + HydrusData.SplayListForDB( message_ids ) + ';' ) }
    
    def _GetMessageIdsToMessageKeys( self, message_ids ): return { message_id : message_key for ( message_id, message_key ) in self._c.execute( 'SELECT message_id, message_key FROM message_keys WHERE message_id IN ' + HydrusData.SplayListForDB( message_ids ) + ';' ) }
    
    def _GetMessageKey( self, message_id ):
        
        result = self._c.execute( 'SELECT message_key FROM message_keys WHERE message_id = ?;', ( message_id, ) ).fetchone()
        
        if result is None: raise Exception( 'Message key error in database' )
        
        ( message_key, ) = result
        
        return message_key
        
    
    def _GetMessageKeysToDownload( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        message_keys = [ message_key for ( message_key, ) in self._c.execute( 'SELECT message_key FROM message_downloads, message_keys USING ( message_id ) WHERE service_id = ?;', ( service_id, ) ) ]
        
        return message_keys
        
    
    def _GetMessageSystemPredicates( self, identity ):
        
        name = identity.GetName()
        
        is_anon = name == 'Anonymous'
        
        additional_predicate = ''
        
        if name != 'Anonymous':
            
            service = self._GetService( identity )
            
            if not service.ReceivesAnon(): additional_predicate = 'contact_id_from != 1 AND '
            
        
        contact_id = self._GetContactId( name )
        
        unread_status_id = self._GetStatusId( 'sent' )
        
        #service_info = self._GetServiceInfoSpecific( service_id, service_type, { HC.SERVICE_INFO_NUM_CONVERSATIONS, HC.SERVICE_INFO_NUM_INBOX, HC.SERVICE_INFO_NUM_UNREAD, HC.SERVICE_INFO_NUM_DRAFTS } )
        
        ( num_conversations, ) = self._c.execute( 'SELECT COUNT( DISTINCT conversation_id ) FROM messages, message_destination_map USING ( message_id ) WHERE ' + additional_predicate + '( contact_id_from = ? OR contact_id_to = ? );', ( contact_id, contact_id ) ).fetchone()
        ( num_inbox, ) = self._c.execute( 'SELECT COUNT( DISTINCT conversation_id ) FROM message_destination_map, ( messages, message_inbox USING ( message_id ) ) USING ( message_id ) WHERE ' + additional_predicate + 'contact_id_to = ?;', ( contact_id, ) ).fetchone()
        ( num_drafts, ) = self._c.execute( 'SELECT COUNT( DISTINCT conversation_id ) FROM messages, message_drafts USING ( message_id ) WHERE contact_id_from = ?;', ( contact_id, ) ).fetchone()
        ( num_unread, ) = self._c.execute( 'SELECT COUNT( DISTINCT conversation_id ) FROM messages, message_destination_map USING ( message_id ) WHERE ' + additional_predicate + 'contact_id_to = ? AND status_id = ?;', ( contact_id, unread_status_id ) ).fetchone()
        
        predicates = []
        
        # anon has no inbox, no received mail; only sent mail
        
        predicates.append( ( u'system:everything', num_conversations ) )
        if not is_anon:
            predicates.append( ( u'system:inbox', num_inbox ) )
            predicates.append( ( u'system:archive', num_conversations - num_inbox ) )
            predicates.append( ( u'system:unread', num_unread ) )
        predicates.append( ( u'system:drafts', num_drafts ) )
        if not is_anon:
            predicates.append( ( u'system:started_by', None ) )
            predicates.append( ( u'system:from', None ) )
        predicates.append( ( u'system:to', None ) )
        predicates.append( ( u'system:age', None ) )
        predicates.append( ( u'system:numattachments', None ) )
        # we can add more later
        
        return predicates
        
    
    def _GetMessagesToSend( self ):
        
        status_id = self._GetStatusId( 'pending' )
        
        message_id_to_contact_ids = HydrusData.BuildKeyToListDict( self._c.execute( 'SELECT message_id, contact_id_to FROM message_destination_map WHERE status_id = ?;', ( status_id, ) ) )
        
        messages_to_send = [ ( self._GetMessageKey( message_id ), [ self._GetContact( contact_id_to ) for contact_id_to in contact_ids_to ] ) for ( message_id, contact_ids_to ) in message_id_to_contact_ids.items() ]
        
        return messages_to_send
        
    
    def _GetStatus( self, status_id ):
        
        result = self._c.execute( 'SELECT status FROM statuses WHERE status_id = ?;', ( status_id, ) ).fetchone()
        
        if result is None: raise Exception( 'Status error in database' )
        
        ( status, ) = result
        
        return status
        
    
    def _GetStatusId( self, status ):
        
        result = self._c.execute( 'SELECT status_id FROM statuses WHERE status = ?;', ( status, ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT INTO statuses ( status ) VALUES ( ? );', ( status, ) )
            
            status_id = self._c.lastrowid
            
        else: ( status_id, ) = result
        
        return status_id
        
    
    def _GetStatusIdsToStatuses( self, status_ids ): return { status_id : status for ( status_id, status ) in self._c.execute( 'SELECT status_id, status FROM statuses WHERE status_id IN ' + HydrusData.SplayListForDB( status_ids ) + ';' ) }
    
    def _GetTransportMessage( self, message_key ):
        
        message_id = self._GetMessageId( message_key )
        
        ( conversation_id, contact_id_from, timestamp ) = self._c.execute( 'SELECT conversation_id, contact_id_from, timestamp FROM messages WHERE message_id = ?;', ( message_id, ) ).fetchone()
        
        contact_ids_to = [ contact_id_to for ( contact_id_to, ) in self._c.execute( 'SELECT contact_id_to FROM message_destination_map WHERE message_id = ?;', ( message_id, ) ) ]
        
        ( subject, ) = self._c.execute( 'SELECT subject FROM conversation_subjects WHERE docid = ?;', ( conversation_id, ) ).fetchone()
        
        ( body, ) = self._c.execute( 'SELECT body FROM message_bodies WHERE docid = ?;', ( message_id, ) ).fetchone()
        
        attachment_hashes = [ hash for ( hash, ) in self._c.execute( 'SELECT hash FROM message_attachments, hashes USING ( hash_id ) WHERE message_id = ?;', ( message_id, ) ) ]
        
        attachment_hashes.sort()
        
        files = []
        
        client_files_manager = self._controller.GetClientFilesManager()
        
        for hash in attachment_hashes:
            
            path = client_files_manager.GetFilePath( hash )
            
            with open( path, 'rb' ) as f: file = f.read()
            
            files.append( file )
            
        
        conversation_key = self._GetMessageKey( conversation_id )
        
        contact_from = self._GetContact( contact_id_from )
        
        contacts_to = [ self._GetContact( contact_id_to ) for contact_id_to in contact_ids_to ]
        
        if contact_from.GetName() == 'Anonymous':
            
            contact_from = None
            message_depot = None
            private_key = None
            
        else:
            
            message_depot = self._GetService( contact_from )
            private_key = message_depot.GetPrivateKey()
            
        
        if conversation_key == message_key: conversation_key = None
        
        message = HydrusMessageHandling.Message( conversation_key, contact_from, contacts_to, subject, body, timestamp, files = files, private_key = private_key )
        
        return message
        
    
    def _GetTransportMessagesFromDraft( self, draft_message ):
        
        ( draft_key, conversation_key, subject, contact_from, contact_names_to, recipients_visible, body, attachment_hashes ) = draft_message.GetInfo()
        
        ( xml, html ) = yaml.safe_load( body )
        
        body = html
        
        files = []
        
        client_files_manager = self._controller.GetClientFilesManager()
        
        for hash in attachment_hashes:
            
            path = client_files_manager.GetFilePath( hash )
            
            with open( path, 'rb' ) as f: file = f.read()
            
            files.append( file )
            
        
        contact_id_from = self._GetContactId( contact_from )
        
        if contact_from.GetName() == 'Anonymous':
            
            contact_from = None
            message_depot = None
            private_key = None
            
        else:
            
            message_depot = self._GetService( contact_from )
            private_key = message_depot.GetPrivateKey()
            
        
        timestamp = HydrusData.GetNow()
        
        contacts_to = [ self._GetContact( contact_name_to ) for contact_name_to in contact_names_to ]
        
        if conversation_key == draft_key: conversation_key = None
        
        if recipients_visible: messages = [ HydrusMessageHandling.Message( conversation_key, contact_from, contacts_to, subject, body, timestamp, files = files, private_key = private_key ) ]
        else: messages = [ HydrusMessageHandling.Message( conversation_key, contact_from, [ contact_to ], subject, body, timestamp, files = files, private_key = private_key ) for contact_to in contacts_to ]
        
        return messages
        
    
    def _InboxConversation( self, conversation_key ):
        
        conversation_id = self._GetMessageId( conversation_key )
        
        inserts = self._c.execute( 'SELECT message_id FROM messages WHERE conversation_id = ?;', ( conversation_id, ) ).fetchall()
        
        self._c.executemany( 'INSERT OR IGNORE INTO message_inbox ( message_id ) VALUES ( ? );', inserts )
        
        self.pub_after_commit( 'inbox_conversation_data', conversation_key )
        self.pub_after_commit( 'inbox_conversation_gui', conversation_key )
        
        self._DoStatusNumInbox()
        
    
    def _UpdateContacts( self, edit_log ):
        
        for ( action, details ) in edit_log:
            
            if action == HC.ADD:
                
                contact = details
                
                self._AddContact( contact )
                
            elif action == HC.DELETE:
                
                name = details
                
                result = self._c.execute( 'SELECT 1 FROM contacts WHERE name = ? AND NOT EXISTS ( SELECT 1 FROM message_destination_map WHERE contact_id_to = contact_id ) AND NOT EXISTS ( SELECT 1 FROM messages WHERE contact_id_from = contact_id );', ( name, ) ).fetchone()
                
                if result is not None: self._c.execute( 'DELETE FROM contacts WHERE name = ?;', ( name, ) )
                
            elif action == HC.EDIT:
                
                ( old_name, contact ) = details
                
                try:
                    
                    contact_id = self._GetContactId( old_name )
                    
                    ( public_key, name, host, port ) = contact.GetInfo()
                    
                    contact_key = contact.GetContactKey()
                    
                    if public_key is not None: contact_key = sqlite3.Binary( contact_key )
                    
                    self._c.execute( 'UPDATE contacts SET contact_key = ?, public_key = ?, name = ?, host = ?, port = ? WHERE contact_id = ?;', ( contact_key, public_key, name, host, port, contact_id ) )
                    
                except: pass
                
            
        
        self.pub_after_commit( 'notify_new_contacts' )
        
    
    def _UpdateMessageStatuses( self, message_key, status_updates ):
        
        message_id = self._GetMessageId( message_key )
        
        updates = []
        
        for ( contact_key, status ) in status_updates:
            
            contact_id = self._GetContactId( contact_key )
            status_id = self._GetStatusId( status )
            
            updates.append( ( contact_id, status_id ) )
            
        
        self._c.executemany( 'UPDATE message_destination_map SET status_id = ? WHERE contact_id_to = ? AND message_id = ?;', [ ( status_id, contact_id, message_id ) for ( contact_id, status_id ) in updates ] )
        
        self.pub_after_commit( 'message_statuses_data', message_key, status_updates )
        self.pub_after_commit( 'message_statuses_gui', message_key, status_updates )
        self.pub_after_commit( 'notify_check_messages' )
        
    '''

def GenerateCombinedFilesMappingsCacheTableName( service_id ):
    
    return 'external_caches.combined_files_ac_cache_' + str( service_id )
    
def GenerateMappingsTableNames( service_id ):
    
    suffix = str( service_id )
    
    current_mappings_table_name = 'external_mappings.current_mappings_' + suffix
    
    deleted_mappings_table_name = 'external_mappings.deleted_mappings_' + suffix
    
    pending_mappings_table_name = 'external_mappings.pending_mappings_' + suffix
    
    petitioned_mappings_table_name = 'external_mappings.petitioned_mappings_' + suffix
    
    return ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name )
    
def GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id ):
    
    suffix = str( file_service_id ) + '_' + str( tag_service_id )
    
    files_table_name = 'external_caches.specific_files_cache_' + suffix
    
    current_mappings_table_name = 'external_caches.specific_current_mappings_cache_' + suffix
    
    pending_mappings_table_name = 'external_caches.specific_pending_mappings_cache_' + suffix
    
    ac_cache_table_name = 'external_caches.specific_ac_cache_' + suffix
    
    return ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name )
    
class DB( HydrusDB.HydrusDB ):
    
    READ_WRITE_ACTIONS = [ 'service_info', 'system_predicates' ]
    
    def _AddFilesInfo( self, rows, overwrite = False ):
        
        if overwrite:
            
            insert_phrase = 'REPLACE INTO'
            
        else:
            
            insert_phrase = 'INSERT OR IGNORE INTO'
            
        
        # hash_id, size, mime, width, height, duration, num_frames, num_words
        self._c.executemany( insert_phrase + ' files_info VALUES ( ?, ?, ?, ?, ?, ?, ?, ? );', rows )
        
    
    def _AddFiles( self, service_id, rows ):
        
        hash_ids = { row[0] for row in rows }
        
        existing_hash_ids = { hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM current_files WHERE service_id = ? AND hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';', ( service_id, ) ) }
        
        valid_hash_ids = hash_ids.difference( existing_hash_ids )
        
        if len( valid_hash_ids ) > 0:
            
            self._c.executemany( 'INSERT OR IGNORE INTO current_files VALUES ( ?, ?, ? );', ( ( service_id, hash_id, timestamp ) for ( hash_id, timestamp ) in rows if hash_id in valid_hash_ids ) )
            
            splayed_valid_hash_ids = HydrusData.SplayListForDB( valid_hash_ids )
            
            self._c.execute( 'DELETE FROM deleted_files WHERE service_id = ? AND hash_id IN ' + splayed_valid_hash_ids + ';', ( service_id, ) )
            
            num_deleted = self._GetRowCount()
            
            info = self._c.execute( 'SELECT size, mime FROM files_info WHERE hash_id IN ' + splayed_valid_hash_ids + ';' ).fetchall()
            
            num_files = len( valid_hash_ids )
            delta_size = sum( ( size for ( size, mime ) in info ) )
            num_thumbnails = sum( ( 1 for ( size, mime ) in info if mime in HC.MIMES_WITH_THUMBNAILS ) )
            num_inbox = len( valid_hash_ids.intersection( self._inbox_hash_ids ) )
            
            service_info_updates = []
            
            service_info_updates.append( ( -num_deleted, service_id, HC.SERVICE_INFO_NUM_DELETED_FILES ) )
            service_info_updates.append( ( delta_size, service_id, HC.SERVICE_INFO_TOTAL_SIZE ) )
            service_info_updates.append( ( num_files, service_id, HC.SERVICE_INFO_NUM_FILES ) )
            service_info_updates.append( ( num_thumbnails, service_id, HC.SERVICE_INFO_NUM_THUMBNAILS ) )
            service_info_updates.append( ( num_inbox, service_id, HC.SERVICE_INFO_NUM_INBOX ) )
            
            self._c.executemany( 'UPDATE service_info SET info = info + ? WHERE service_id = ? AND info_type = ?;', service_info_updates )
            
            self._c.execute( 'DELETE FROM file_transfers WHERE service_id = ? AND hash_id IN ' + splayed_valid_hash_ids + ';', ( service_id, ) )
            
            if num_thumbnails > 0:
                
                self._c.execute( 'DELETE FROM service_info WHERE service_id = ? AND info_type = ?;', ( service_id, HC.SERVICE_INFO_NUM_THUMBNAILS_LOCAL ) )
                
            
            if service_id == self._local_file_service_id:
                
                self._DeleteFiles( self._trash_service_id, valid_hash_ids, files_being_undeleted = True )
                
            
            if service_id == self._trash_service_id:
                
                now = HydrusData.GetNow()
                
                self._c.executemany( 'INSERT OR IGNORE INTO file_trash ( hash_id, timestamp ) VALUES ( ?, ? );', ( ( hash_id, now ) for hash_id in valid_hash_ids ) )
                
            
            service = self._GetService( service_id )
            
            service_type = service.GetServiceType()
            
            if service_type in ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ):
                
                tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
                
                for tag_service_id in tag_service_ids:
                    
                    self._CacheSpecificMappingsAddFiles( service_id, tag_service_id, valid_hash_ids )
                    
                
            
        
    
    def _AddHydrusSession( self, service_key, session_key, expires ):
        
        service_id = self._GetServiceId( service_key )
        
        self._c.execute( 'REPLACE INTO hydrus_sessions ( service_id, session_key, expiry ) VALUES ( ?, ?, ? );', ( service_id, sqlite3.Binary( session_key ), expires ) )
        
    
    def _AddService( self, service_key, service_type, name, info ):
        
        if service_type in HC.LOCAL_SERVICES:
            
            if service_type == HC.LOCAL_BOORU:
                
                current_time_struct = time.gmtime()
                
                ( current_year, current_month ) = ( current_time_struct.tm_year, current_time_struct.tm_mon )
                
                if 'used_monthly_data' not in info: info[ 'used_monthly_data' ] = 0
                if 'max_monthly_data' not in info: info[ 'max_monthly_data' ] = None
                if 'used_monthly_requests' not in info: info[ 'used_monthly_requests' ] = 0
                if 'current_data_month' not in info: info[ 'current_data_month' ] = ( current_year, current_month )
                if 'port' not in info: info[ 'port' ] = None
                if 'upnp' not in info: info[ 'upnp' ] = None
                
            
        
        if service_type in HC.REMOTE_SERVICES:
            
            if 'last_error' not in info: info[ 'last_error' ] = 0
            
        
        if service_type in HC.RESTRICTED_SERVICES:
            
            if 'account' not in info:
                
                account = HydrusData.GetUnknownAccount()
                
                account.MakeStale()
                
                info[ 'account' ] = account
                
                self.pub_after_commit( 'permissions_are_stale' )
                
            
        
        if service_type in HC.TAG_SERVICES:
            
            if 'tag_archive_sync' not in info: info[ 'tag_archive_sync' ] = {}
            
        
        if service_type in HC.REPOSITORIES:
            
            update_dir = ClientFiles.GetExpectedUpdateDir( service_key )
            
            if not os.path.exists( update_dir ):
                
                os.makedirs( update_dir )
                
            
            if 'first_timestamp' not in info:
                
                info[ 'first_timestamp' ] = None
                
            
            if 'next_download_timestamp' not in info:
                
                info[ 'next_download_timestamp' ] = 0
                
            
            if 'next_processing_timestamp' not in info:

                info[ 'next_processing_timestamp' ] = 0
                
            
            info[ 'paused' ] = False
            
        
        result = self._c.execute( 'SELECT 1 FROM services WHERE name = ?;', ( name, ) ).fetchone()
        
        while result is not None:
            
            name += str( random.randint( 0, 9 ) )
            
            result = self._c.execute( 'SELECT 1 FROM services WHERE name = ?;', ( name, ) ).fetchone()
            
        
        self._c.execute( 'INSERT INTO services ( service_key, service_type, name, info ) VALUES ( ?, ?, ?, ? );', ( sqlite3.Binary( service_key ), service_type, name, info ) )
        
        service_id = self._c.lastrowid
        
        if service_type in HC.TAG_SERVICES:
            
            ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
            
            current_mappings_table_simple_name = current_mappings_table_name.split( '.' )[1]
            deleted_mappings_table_simple_name = deleted_mappings_table_name.split( '.' )[1]
            pending_mappings_table_simple_name = pending_mappings_table_name.split( '.' )[1]
            petitioned_mappings_table_simple_name = petitioned_mappings_table_name.split( '.' )[1]
            
            self._c.execute( 'CREATE TABLE IF NOT EXISTS ' + current_mappings_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( namespace_id, tag_id, hash_id ) ) WITHOUT ROWID;' )
            self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + current_mappings_table_name + '_tag_id_index ON ' + current_mappings_table_simple_name + ' ( tag_id );' )
            self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + current_mappings_table_name + '_hash_id_index ON ' + current_mappings_table_simple_name + ' ( hash_id );' )
            
            self._c.execute( 'CREATE TABLE IF NOT EXISTS ' + deleted_mappings_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( namespace_id, tag_id, hash_id ) ) WITHOUT ROWID;' )
            self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + deleted_mappings_table_name + '_hash_id_index ON ' + deleted_mappings_table_simple_name + ' ( hash_id );' )
            
            self._c.execute( 'CREATE TABLE IF NOT EXISTS ' + pending_mappings_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( namespace_id, tag_id, hash_id ) ) WITHOUT ROWID;' )
            self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + pending_mappings_table_name + '_tag_id_index ON ' + pending_mappings_table_simple_name + ' ( tag_id );' )
            self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + pending_mappings_table_name + '_hash_id_index ON ' + pending_mappings_table_simple_name + ' ( hash_id );' )
            
            self._c.execute( 'CREATE TABLE IF NOT EXISTS ' + petitioned_mappings_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, reason_id INTEGER, PRIMARY KEY( namespace_id, tag_id, hash_id, reason_id ) ) WITHOUT ROWID;' )
            self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + petitioned_mappings_table_name + '_hash_id_index ON ' + petitioned_mappings_table_simple_name + ' ( hash_id );' )
            
            #
            
            self._CacheCombinedFilesMappingsGenerate( service_id )
            
            file_service_ids = self._GetServiceIds( ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ) )
            
            for file_service_id in file_service_ids:
                
                self._CacheSpecificMappingsGenerate( file_service_id, service_id )
                
            
        
        if service_type in ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ):
            
            tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
            
            for tag_service_id in tag_service_ids:
                
                self._CacheSpecificMappingsGenerate( service_id, tag_service_id )
                
            
        
    
    def _AddThumbnails( self, thumbnails ):
        
        for ( hash, thumbnail ) in thumbnails:
            
            thumbnail_path = ClientFiles.GetExpectedThumbnailPath( hash, True )
            
            with open( thumbnail_path, 'wb' ) as f:
                
                f.write( thumbnail )
                
            
            try:
                
                phash = ClientImageHandling.GeneratePerceptualHash( thumbnail_path )
                
                hash_id = self._GetHashId( hash )
                
                self._c.execute( 'INSERT OR REPLACE INTO perceptual_hashes ( hash_id, phash ) VALUES ( ?, ? );', ( hash_id, sqlite3.Binary( phash ) ) )
                
            except:
                
                pass
                
            
        
        self._c.execute( 'DELETE FROM service_info WHERE info_type = ?;', ( HC.SERVICE_INFO_NUM_THUMBNAILS_LOCAL, ) )
        
        hashes = { hash for ( hash, thumbnail ) in thumbnails }
        
        self.pub_after_commit( 'new_thumbnails', hashes )
        
    
    def _AddWebSession( self, name, cookies, expires ):
        
        self._c.execute( 'REPLACE INTO web_sessions ( name, cookies, expiry ) VALUES ( ?, ?, ? );', ( name, cookies, expires ) )
        
    
    def _Analyze( self, stop_time = None, only_when_idle = False, force_reanalyze = False ):
        
        stale_time_delta = 14 * 86400
        
        existing_names_to_timestamps = dict( self._c.execute( 'SELECT name, timestamp FROM analyze_timestamps;' ).fetchall() )
        
        db_names = [ name for ( index, name, path ) in self._c.execute( 'PRAGMA database_list;' ) if name not in ( 'mem', 'temp' ) ]
        
        all_names = set()
        
        for db_name in db_names:
            
            all_names.update( ( name for ( name, ) in self._c.execute( 'SELECT name FROM ' + db_name + '.sqlite_master;' ) ) )
            
        
        if force_reanalyze:
            
            names_to_analyze = list( all_names )
            
        else:
            
            names_to_analyze = [ name for name in all_names if name not in existing_names_to_timestamps or HydrusData.TimeHasPassed( existing_names_to_timestamps[ name ] + stale_time_delta ) ]
            
        
        if len( names_to_analyze ) > 0:
            
            job_key = ClientThreading.JobKey()
            
            job_key.SetVariable( 'popup_title', 'database maintenance - analyzing' )
            
            self._controller.pub( 'message', job_key )
            
            random.shuffle( names_to_analyze )
            
            for name in names_to_analyze:
                
                self._controller.pub( 'splash_set_status_text', 'analyzing ' + name )
                job_key.SetVariable( 'popup_text_1', 'analyzing ' + name )
                
                started = HydrusData.GetNowPrecise()
                
                self._c.execute( 'ANALYZE ' + name + ';' )
                
                self._c.execute( 'DELETE FROM analyze_timestamps WHERE name = ?;', ( name, ) )
                
                self._c.execute( 'INSERT OR IGNORE INTO analyze_timestamps ( name, timestamp ) VALUES ( ?, ? );', ( name, HydrusData.GetNow() ) )
                
                time_took = HydrusData.GetNowPrecise() - started
                
                if time_took > 1:
                    
                    HydrusData.Print( 'Analyzed ' + name + ' in ' + HydrusData.ConvertTimeDeltaToPrettyString( time_took ) )
                    
                
                p1 = stop_time is not None and HydrusData.TimeHasPassed( stop_time )
                p2 = only_when_idle and not self._controller.CurrentlyIdle()
                
                if p1 or p2:
                    
                    break
                    
                
            
            self._c.execute( 'ANALYZE sqlite_master;' ) # this reloads the current stats into the query planner
            
            job_key.SetVariable( 'popup_text_1', 'done!' )
            
            HydrusData.Print( job_key.ToString() )
            
            wx.CallLater( 1000 * 30, job_key.Delete )
            
        
    
    def _ArchiveFiles( self, hash_ids ):
        
        valid_hash_ids = [ hash_id for hash_id in hash_ids if hash_id in self._inbox_hash_ids ]
        
        if len( valid_hash_ids ) > 0:
            
            splayed_hash_ids = HydrusData.SplayListForDB( valid_hash_ids )
            
            self._c.execute( 'DELETE FROM file_inbox WHERE hash_id IN ' + splayed_hash_ids + ';' )
            
            updates = self._c.execute( 'SELECT service_id, COUNT( * ) FROM current_files WHERE hash_id IN ' + splayed_hash_ids + ' GROUP BY service_id;' ).fetchall()
            
            self._c.executemany( 'UPDATE service_info SET info = info - ? WHERE service_id = ? AND info_type = ?;', [ ( count, service_id, HC.SERVICE_INFO_NUM_INBOX ) for ( service_id, count ) in updates ] )
            
            self._inbox_hash_ids.difference_update( valid_hash_ids )
            
        
    
    def _Backup( self, path ):
        
        client_files_locations = self._GetClientFilesLocations()
        
        for location in client_files_locations.values():
            
            if not location.startswith( HC.CLIENT_FILES_DIR ):
                
                HydrusData.ShowText( 'Some of your files are stored outside of ' + HC.CLIENT_FILES_DIR + '. These files will not be backed up--please do this manually, yourself.' )
                
                break
                
            
        
        job_key = ClientThreading.JobKey( cancellable = True )
        
        job_key.SetVariable( 'popup_title', 'backing up db' )
        
        self._controller.pub( 'message', job_key )
        
        job_key.SetVariable( 'popup_text_1', 'closing db' )
        
        self._c.execute( 'COMMIT;' )
        
        self._CloseDBCursor()
        
        try:
            
            if not os.path.exists( path ):
                
                os.makedirs( path )
                
            
            for filename in self._db_filenames.values():
                
                job_key.SetVariable( 'popup_text_1', 'copying ' + filename )
                
                source = os.path.join( self._db_dir, filename )
                dest = os.path.join( path, filename )
                
                if not HydrusPaths.PathsHaveSameSizeAndDate( source, dest ):
                    
                    shutil.copy2( source, dest )
                    
                
            
            job_key.SetVariable( 'popup_text_1', 'copying archives directory' )
            
            HydrusPaths.MirrorTree( HC.CLIENT_ARCHIVES_DIR, os.path.join( path, 'client_archives' ) ) 
            
            job_key.SetVariable( 'popup_text_1', 'copying files directory' )
            
            HydrusPaths.MirrorTree( HC.CLIENT_FILES_DIR, os.path.join( path, 'client_files' ) )
            
            job_key.SetVariable( 'popup_text_1', 'copying thumbnails directory' )
            
            HydrusPaths.MirrorTree( HC.CLIENT_THUMBNAILS_DIR, os.path.join( path, 'client_thumbnails' ) )
            
            job_key.SetVariable( 'popup_text_1', 'copying updates directory' )
            
            HydrusPaths.MirrorTree( HC.CLIENT_UPDATES_DIR, os.path.join( path, 'client_updates' ) )
            
        finally:
            
            self._InitDBCursor()
            
            self._c.execute( 'BEGIN IMMEDIATE;' )
            
        
        job_key.SetVariable( 'popup_text_1', 'done!' )
        
        job_key.Finish()
        
    
    def _CacheCombinedFilesMappingsDrop( self, service_id ):
        
        ac_cache_table_name = GenerateCombinedFilesMappingsCacheTableName( service_id )
        
        self._c.execute( 'DROP TABLE ' + ac_cache_table_name + ';' )
        
    
    def _CacheCombinedFilesMappingsGenerate( self, service_id ):
        
        ac_cache_table_name = GenerateCombinedFilesMappingsCacheTableName( service_id )
        
        self._c.execute( 'CREATE TABLE ' + ac_cache_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, current_count INTEGER, pending_count INTEGER, PRIMARY KEY( namespace_id, tag_id ) ) WITHOUT ROWID;' )
        
        #
        
        ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
        
        current_mappings_exist = self._c.execute( 'SELECT 1 FROM ' + current_mappings_table_name + ' LIMIT 1;' ).fetchone() is not None
        pending_mappings_exist = self._c.execute( 'SELECT 1 FROM ' + pending_mappings_table_name + ' LIMIT 1;' ).fetchone() is not None
        
        if current_mappings_exist or pending_mappings_exist:
            
            all_known_ids = self._c.execute( 'SELECT namespace_id, tag_id FROM existing_tags;' ).fetchall()
            
            for group_of_ids in HydrusData.SplitListIntoChunks( all_known_ids, 10000 ):
                
                current_counter = collections.Counter()
                
                if current_mappings_exist:
                    
                    for ( namespace_id, tag_id ) in group_of_ids:
                        
                        result = self._c.execute( 'SELECT COUNT( * ) FROM ' + current_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ?;', ( namespace_id, tag_id ) ).fetchone()
                        
                        if result is not None:
                            
                            ( count, ) = result
                            
                            if count > 0:
                                
                                current_counter[ ( namespace_id, tag_id ) ] = count
                                
                            
                        
                    
                
                #
                
                pending_counter = collections.Counter()
                
                if pending_mappings_exist:
                    
                    for ( namespace_id, tag_id ) in group_of_ids:
                        
                        result = self._c.execute( 'SELECT COUNT( * ) FROM ' + pending_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ?;', ( namespace_id, tag_id ) ).fetchone()
                        
                        if result is not None:
                            
                            ( count, ) = result
                            
                            if count > 0:
                                
                                pending_counter[ ( namespace_id, tag_id ) ] = count
                                
                            
                        
                    
                
                all_ids_seen = set( current_counter.keys() )
                all_ids_seen.update( pending_counter.keys() )
                
                count_ids = [ ( namespace_id, tag_id, current_counter[ ( namespace_id, tag_id ) ], pending_counter[ ( namespace_id, tag_id ) ] ) for ( namespace_id, tag_id ) in all_ids_seen ]
                
                if len( count_ids ) > 0:
                    
                    self._CacheCombinedFilesMappingsUpdate( service_id, count_ids )
                    
                
            
        
    
    def _CacheCombinedFilesMappingsGetAutocompleteCounts( self, service_id, namespace_ids_to_tag_ids ):
        
        ac_cache_table_name = GenerateCombinedFilesMappingsCacheTableName( service_id )
        
        results = []
        
        for ( namespace_id, tag_ids ) in namespace_ids_to_tag_ids.items():
            
            results.extend( ( ( namespace_id, tag_id, current_count, pending_count ) for ( tag_id, current_count, pending_count ) in self._c.execute( 'SELECT tag_id, current_count, pending_count FROM ' + ac_cache_table_name + ' WHERE namespace_id = ? AND tag_id IN ' + HydrusData.SplayListForDB( tag_ids ) + ';', ( namespace_id, ) ) ) )
            
        
        return results
        
    
    def _CacheCombinedFilesMappingsUpdate( self, service_id, count_ids ):
        
        ac_cache_table_name = GenerateCombinedFilesMappingsCacheTableName( service_id )
        
        self._c.executemany( 'INSERT OR IGNORE INTO ' + ac_cache_table_name + ' ( namespace_id, tag_id, current_count, pending_count ) VALUES ( ?, ?, ?, ? );', ( ( namespace_id, tag_id, 0, 0 ) for ( namespace_id, tag_id, current_delta, pending_delta ) in count_ids ) )
        
        self._c.executemany( 'UPDATE ' + ac_cache_table_name + ' SET current_count = current_count + ?, pending_count = pending_count + ? WHERE namespace_id = ? AND tag_id = ?;', ( ( current_delta, pending_delta, namespace_id, tag_id ) for ( namespace_id, tag_id, current_delta, pending_delta ) in count_ids ) )
        
        self._c.executemany( 'DELETE FROM ' + ac_cache_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND current_count = ? AND pending_count = ?;', ( ( namespace_id, tag_id, 0, 0 ) for ( namespace_id, tag_id, current_delta, pending_delta ) in count_ids ) )
        
    
    def _CacheSpecificMappingsAddFiles( self, file_service_id, tag_service_id, hash_ids ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        self._c.executemany( 'INSERT OR IGNORE INTO ' + files_table_name + ' VALUES ( ? );', ( ( hash_id, ) for hash_id in hash_ids ) )
        
        ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( tag_service_id )
        
        ac_cache_changes = []
        
        for group_of_hash_ids in HydrusData.SplitListIntoChunks( hash_ids, 100 ):
            
            splayed_group_of_hash_ids = HydrusData.SplayListForDB( group_of_hash_ids )
            
            current_mapping_ids_raw = self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM ' + current_mappings_table_name + ' WHERE hash_id IN ' + splayed_group_of_hash_ids + ';' ).fetchall()
            
            current_mapping_ids_dict = HydrusData.BuildKeyToSetDict( [ ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in current_mapping_ids_raw ] )
            
            pending_mapping_ids_raw = self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM ' + pending_mappings_table_name + ' WHERE hash_id IN ' + splayed_group_of_hash_ids + ';' ).fetchall()
            
            pending_mapping_ids_dict = HydrusData.BuildKeyToSetDict( [ ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in pending_mapping_ids_raw ] )
            
            all_ids_seen = set( current_mapping_ids_dict.keys() )
            all_ids_seen.update( pending_mapping_ids_dict.keys() )
            
            for ( namespace_id, tag_id ) in all_ids_seen:
                
                current_hash_ids = current_mapping_ids_dict[ ( namespace_id, tag_id ) ]
                
                num_current = len( current_hash_ids )
                
                if num_current > 0:
                    
                    self._c.executemany( 'INSERT OR IGNORE INTO ' + current_mappings_table_name + ' ( hash_id, namespace_id, tag_id ) VALUES ( ?, ?, ? );', ( ( hash_id, namespace_id, tag_id ) for hash_id in current_hash_ids ) )
                    
                
                pending_hash_ids = pending_mapping_ids_dict[ ( namespace_id, tag_id ) ]
                
                num_pending = len( pending_hash_ids )
                
                if num_pending > 0:
                    
                    self._c.executemany( 'INSERT OR IGNORE INTO ' + pending_mappings_table_name + ' ( hash_id, namespace_id, tag_id ) VALUES ( ?, ?, ? );', ( ( hash_id, namespace_id, tag_id ) for hash_id in pending_hash_ids ) )
                    
                
                if num_current > 0 or num_pending > 0:
                    
                    ac_cache_changes.append( ( namespace_id, tag_id, num_current, num_pending ) )
                    
                
            
        
        if len( ac_cache_changes ) > 0:
            
            self._c.executemany( 'INSERT OR IGNORE INTO ' + ac_cache_table_name + ' ( namespace_id, tag_id, current_count, pending_count ) VALUES ( ?, ?, ?, ? );', ( ( namespace_id, tag_id, 0, 0 ) for ( namespace_id, tag_id, num_current, num_pending ) in ac_cache_changes ) )
            
            self._c.executemany( 'UPDATE ' + ac_cache_table_name + ' SET current_count = current_count + ?, pending_count = pending_count + ? WHERE namespace_id = ? AND tag_id = ?;', ( ( num_current, num_pending, namespace_id, tag_id ) for ( namespace_id, tag_id, num_current, num_pending ) in ac_cache_changes ) )
            
        
    
    def _CacheSpecificMappingsAddMappings( self, file_service_id, tag_service_id, mappings_ids ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        for ( namespace_id, tag_id, hash_ids ) in mappings_ids:
            
            hash_ids = self._CacheSpecificMappingsFilterHashIds( file_service_id, tag_service_id, hash_ids )
            
            if len( hash_ids ) > 0:
                
                self._c.executemany( 'DELETE FROM ' + pending_mappings_table_name + ' WHERE hash_id = ? AND namespace_id = ? AND tag_id = ?;', ( ( hash_id, namespace_id, tag_id ) for hash_id in hash_ids ) )
                
                num_pending_rescinded = self._GetRowCount()
                
                #
                
                self._c.executemany( 'INSERT OR IGNORE INTO ' + current_mappings_table_name + ' ( hash_id, namespace_id, tag_id ) VALUES ( ?, ?, ? );', ( ( hash_id, namespace_id, tag_id ) for hash_id in hash_ids ) )
                
                num_added = self._GetRowCount()
                
                if num_pending_rescinded > 0:
                    
                    self._c.execute( 'UPDATE ' + ac_cache_table_name + ' SET current_count = current_count + ?, pending_count = pending_count - ? WHERE namespace_id = ? AND tag_id = ?;', ( num_added, num_pending_rescinded, namespace_id, tag_id ) )
                    
                elif num_added > 0:
                    
                    self._c.execute( 'INSERT OR IGNORE INTO ' + ac_cache_table_name + ' ( namespace_id, tag_id, current_count, pending_count ) VALUES ( ?, ?, ?, ? );', ( namespace_id, tag_id, 0, 0 ) )
                    
                    self._c.execute( 'UPDATE ' + ac_cache_table_name + ' SET current_count = current_count + ? WHERE namespace_id = ? AND tag_id = ?;', ( num_added, namespace_id, tag_id ) )
                    
                
            
        
    
    def _CacheSpecificMappingsDrop( self, file_service_id, tag_service_id ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        self._c.execute( 'DROP TABLE ' + files_table_name + ';' )
        
        self._c.execute( 'DROP TABLE ' + current_mappings_table_name + ';' )
        
        self._c.execute( 'DROP TABLE ' + pending_mappings_table_name + ';' )
        
        self._c.execute( 'DROP TABLE ' + ac_cache_table_name + ';' )
        
    
    def _CacheSpecificMappingsDeleteFiles( self, file_service_id, tag_service_id, hash_ids ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        self._c.executemany( 'DELETE FROM ' + files_table_name + ' WHERE hash_id = ?;', ( ( hash_id, ) for hash_id in hash_ids ) )
        
        ac_cache_changes = []
        
        for group_of_hash_ids in HydrusData.SplitListIntoChunks( hash_ids, 100 ):
            
            splayed_group_of_hash_ids = HydrusData.SplayListForDB( group_of_hash_ids )
            
            current_mapping_ids_raw = self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM ' + current_mappings_table_name + ' WHERE hash_id IN ' + splayed_group_of_hash_ids + ';' ).fetchall()
            
            current_mapping_ids_dict = HydrusData.BuildKeyToSetDict( [ ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in current_mapping_ids_raw ] )
            
            pending_mapping_ids_raw = self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM ' + pending_mappings_table_name + ' WHERE hash_id IN ' + splayed_group_of_hash_ids + ';' ).fetchall()
            
            pending_mapping_ids_dict = HydrusData.BuildKeyToSetDict( [ ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in pending_mapping_ids_raw ] )
            
            all_ids_seen = set( current_mapping_ids_dict.keys() )
            all_ids_seen.update( pending_mapping_ids_dict.keys() )
            
            for ( namespace_id, tag_id ) in all_ids_seen:
                
                current_hash_ids = current_mapping_ids_dict[ ( namespace_id, tag_id ) ]
                
                num_current = len( current_hash_ids )
                
                if num_current > 0:
                    
                    self._c.executemany( 'DELETE FROM ' + current_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND hash_id = ?;', ( ( namespace_id, tag_id, hash_id ) for hash_id in current_hash_ids ) )
                    
                
                pending_hash_ids = pending_mapping_ids_dict[ ( namespace_id, tag_id ) ]
                
                num_pending = len( pending_hash_ids )
                
                if num_pending > 0:
                    
                    self._c.executemany( 'DELETE FROM ' + pending_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND hash_id = ?;', ( ( namespace_id, tag_id, hash_id ) for hash_id in pending_hash_ids ) )
                    
                
                ac_cache_changes.append( ( namespace_id, tag_id, num_current, num_pending ) )
                
            
        
        if len( ac_cache_changes ) > 0:
            
            self._c.executemany( 'UPDATE ' + ac_cache_table_name + ' SET current_count = current_count - ?, pending_count = pending_count - ? WHERE namespace_id = ? AND tag_id = ?;', ( ( num_current, num_pending, namespace_id, tag_id ) for ( namespace_id, tag_id, num_current, num_pending ) in ac_cache_changes ) )
            
            self._c.executemany( 'DELETE FROM ' + ac_cache_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND current_count = ? AND pending_count = ?;', ( ( namespace_id, tag_id, 0, 0 ) for ( namespace_id, tag_id, num_current, num_pending ) in ac_cache_changes ) )
            
        
    
    def _CacheSpecificMappingsDeleteMappings( self, file_service_id, tag_service_id, mappings_ids ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        for ( namespace_id, tag_id, hash_ids ) in mappings_ids:
            
            hash_ids = self._CacheSpecificMappingsFilterHashIds( file_service_id, tag_service_id, hash_ids )
            
            if len( hash_ids ) > 0:
                
                self._c.executemany( 'DELETE FROM ' + current_mappings_table_name + ' WHERE hash_id = ? AND namespace_id = ? AND tag_id = ?;', ( ( hash_id, namespace_id, tag_id ) for hash_id in hash_ids ) )
                
                num_deleted = self._GetRowCount()
                
                if num_deleted > 0:
                    
                    self._c.execute( 'UPDATE ' + ac_cache_table_name + ' SET current_count = current_count - ? WHERE namespace_id = ? AND tag_id = ?;', ( num_deleted, namespace_id, tag_id ) )
                    
                    self._c.execute( 'DELETE FROM ' + ac_cache_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND current_count = ? AND pending_count = ?;', ( namespace_id, tag_id, 0, 0 ) )
                    
                
            
        
    
    def _CacheSpecificMappingsFilterHashIds( self, file_service_id, tag_service_id, hash_ids ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        return [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM ' + files_table_name + ' WHERE hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';' ) ]
        
    
    def _CacheSpecificMappingsGenerate( self, file_service_id, tag_service_id ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        self._c.execute( 'CREATE TABLE ' + files_table_name + ' ( hash_id INTEGER PRIMARY KEY );' )
        
        self._c.execute( 'CREATE TABLE ' + current_mappings_table_name + ' ( hash_id INTEGER, namespace_id INTEGER, tag_id INTEGER, PRIMARY KEY( hash_id, namespace_id, tag_id ) ) WITHOUT ROWID;' )
        
        self._c.execute( 'CREATE TABLE ' + pending_mappings_table_name + ' ( hash_id INTEGER, namespace_id INTEGER, tag_id INTEGER, PRIMARY KEY( hash_id, namespace_id, tag_id ) ) WITHOUT ROWID;' )
        
        self._c.execute( 'CREATE TABLE ' + ac_cache_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, current_count INTEGER, pending_count INTEGER, PRIMARY KEY( namespace_id, tag_id ) ) WITHOUT ROWID;' )
        
        #
        
        hash_ids = [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM current_files WHERE service_id = ?;', ( file_service_id, ) ) ]
        
        if len( hash_ids ) > 0:
            
            self._CacheSpecificMappingsAddFiles( file_service_id, tag_service_id, hash_ids )
            
        
    
    def _CacheSpecificMappingsGetAutocompleteCounts( self, file_service_id, tag_service_id, namespace_ids_to_tag_ids ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        results = []
        
        for ( namespace_id, tag_ids ) in namespace_ids_to_tag_ids.items():
            
            results.extend( ( ( namespace_id, tag_id, current_count, pending_count ) for ( tag_id, current_count, pending_count ) in self._c.execute( 'SELECT tag_id, current_count, pending_count FROM ' + ac_cache_table_name + ' WHERE namespace_id = ? AND tag_id IN ' + HydrusData.SplayListForDB( tag_ids ) + ';', ( namespace_id, ) ) ) )
            
        
        return results
        
    
    def _CacheSpecificMappingsPendMappings( self, file_service_id, tag_service_id, mappings_ids ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        for ( namespace_id, tag_id, hash_ids ) in mappings_ids:
            
            hash_ids = self._CacheSpecificMappingsFilterHashIds( file_service_id, tag_service_id, hash_ids )
            
            if len( hash_ids ) > 0:
                
                self._c.executemany( 'INSERT OR IGNORE INTO ' + pending_mappings_table_name + ' ( hash_id, namespace_id, tag_id ) VALUES ( ?, ?, ? );', ( ( hash_id, namespace_id, tag_id ) for hash_id in hash_ids ) )
                
                num_added = self._GetRowCount()
                
                if num_added > 0:
                    
                    self._c.execute( 'INSERT OR IGNORE INTO ' + ac_cache_table_name + ' ( namespace_id, tag_id, current_count, pending_count ) VALUES ( ?, ?, ?, ? );', ( namespace_id, tag_id, 0, 0 ) )
                    
                    self._c.execute( 'UPDATE ' + ac_cache_table_name + ' SET pending_count = pending_count + ? WHERE namespace_id = ? AND tag_id = ?;', ( num_added, namespace_id, tag_id ) )
                    
                
                
            
        
    
    def _CacheSpecificMappingsRescindPendingMappings( self, file_service_id, tag_service_id, mappings_ids ):
        
        ( files_table_name, current_mappings_table_name, pending_mappings_table_name, ac_cache_table_name ) = GenerateSpecificMappingsCacheTableNames( file_service_id, tag_service_id )
        
        for ( namespace_id, tag_id, hash_ids ) in mappings_ids:
            
            hash_ids = self._CacheSpecificMappingsFilterHashIds( file_service_id, tag_service_id, hash_ids )
            
            if len( hash_ids ) > 0:
                
                self._c.executemany( 'DELETE FROM ' + pending_mappings_table_name + ' WHERE hash_id = ? AND namespace_id = ? AND tag_id = ?;', ( ( hash_id, namespace_id, tag_id ) for hash_id in hash_ids ) )
                
                num_deleted = self._GetRowCount()
                
                if num_deleted > 0:
                    
                    self._c.execute( 'UPDATE ' + ac_cache_table_name + ' SET pending_count = pending_count - ? WHERE namespace_id = ? AND tag_id = ?;', ( num_deleted, namespace_id, tag_id ) )
                    
                    self._c.execute( 'DELETE FROM ' + ac_cache_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND current_count = ? AND pending_count = ?;', ( namespace_id, tag_id, 0, 0 ) )
                    
                
            
        
    
    def _CheckDBIntegrity( self ):
        
        prefix_string = 'checking db integrity: '
        
        job_key = ClientThreading.JobKey( cancellable = True )
        
        job_key.SetVariable( 'popup_title', prefix_string + 'preparing' )
        
        self._controller.pub( 'message', job_key )
        
        num_errors = 0
        
        job_key.SetVariable( 'popup_title', prefix_string + 'running' )
        job_key.SetVariable( 'popup_text_1', 'errors found so far: ' + HydrusData.ConvertIntToPrettyString( num_errors ) )
        
        for ( text, ) in self._c.execute( 'PRAGMA integrity_check;' ):
            
            ( i_paused, should_quit ) = job_key.WaitIfNeeded()
            
            if should_quit:
                
                job_key.SetVariable( 'popup_title', prefix_string + 'cancelled' )
                job_key.SetVariable( 'popup_text_1', 'errors found: ' + HydrusData.ConvertIntToPrettyString( num_errors ) )
                
                return
                
            
            if text != 'ok':
                
                if num_errors == 0:
                    
                    HydrusData.Print( 'During a db integrity check, these errors were discovered:' )
                    
                
                HydrusData.Print( text )
                
                num_errors += 1
                
            
            job_key.SetVariable( 'popup_text_1', 'errors found so far: ' + HydrusData.ConvertIntToPrettyString( num_errors ) )
            
        
        job_key.SetVariable( 'popup_title', prefix_string + 'completed' )
        job_key.SetVariable( 'popup_text_1', 'errors found: ' + HydrusData.ConvertIntToPrettyString( num_errors ) )
        
        HydrusData.Print( job_key.ToString() )
        
        job_key.Finish()
        
    
    def _CheckFileIntegrity( self, mode, move_location = None ):
        
        prefix_string = 'checking file integrity: '
        
        job_key = ClientThreading.JobKey( cancellable = True )
        
        job_key.SetVariable( 'popup_text_1', prefix_string + 'preparing' )
        
        self._controller.pub( 'message', job_key )
        
        info = self._c.execute( 'SELECT hash_id, mime FROM current_files, files_info USING ( hash_id ) WHERE service_id IN ( ?, ? );', ( self._local_file_service_id, self._trash_service_id ) ).fetchall()
        
        missing_count = 0
        deletee_hash_ids = []
        
        client_files_manager = self._controller.GetClientFilesManager()
        
        for ( i, ( hash_id, mime ) ) in enumerate( info ):
            
            ( i_paused, should_quit ) = job_key.WaitIfNeeded()
            
            if should_quit:
                
                return
                
            
            job_key.SetVariable( 'popup_text_1', prefix_string + HydrusData.ConvertValueRangeToPrettyString( i, len( info ) ) )
            job_key.SetVariable( 'popup_gauge_1', ( i, len( info ) ) )
            
            hash = self._GetHash( hash_id )
            
            try:
                
                path = client_files_manager.GetFilePath( hash, mime )
                
            except HydrusExceptions.FileMissingException:
                
                print( 'Could not find the file at ' + client_files_manager.GetExpectedFilePath( hash, mime ) + '!' )
                
                deletee_hash_ids.append( hash_id )
                
                missing_count += 1
                
                continue
                
            
            if mode == 'thorough':
                
                actual_hash = HydrusFileHandling.GetHashFromPath( path )
                
                if actual_hash != hash:
                    
                    deletee_hash_ids.append( hash_id )
                    
                    if move_location is not None:
                        
                        move_filename = 'believed ' + hash.encode( 'hex' ) + ' actually ' + actual_hash.encode( 'hex' ) + HC.mime_ext_lookup[ mime ]
                        
                        move_path = os.path.join( move_location, move_filename )
                        
                        shutil.move( path, move_path )
                        
                    
                
            
        
        job_key.DeleteVariable( 'popup_gauge_1' )
        job_key.SetVariable( 'popup_text_1', prefix_string + 'deleting the incorrect records' )
        
        self._DeleteFiles( self._local_file_service_id, deletee_hash_ids )
        self._DeleteFiles( self._trash_service_id, deletee_hash_ids )
        
        final_text = 'done! '
        
        if len( deletee_hash_ids ) == 0:
            
            final_text += 'all files ok!'
            
        else:
            
            final_text += HydrusData.ConvertIntToPrettyString( missing_count ) + ' files were missing!'
            
            if mode == 'thorough':
                
                final_text += ' ' + HydrusData.ConvertIntToPrettyString( len( deletee_hash_ids ) - missing_count ) + ' files were incorrect and thus '
                
                if move_location is None:
                    
                    final_text += 'deleted!'
                    
                else:
                    
                    final_text += 'moved!'
                    
                
            
        
        job_key.SetVariable( 'popup_text_1', prefix_string + final_text )
        
        HydrusData.Print( job_key.ToString() )
        
        job_key.Finish()
        
    
    def _CleanUpCaches( self ):
        
        self._subscriptions_cache = {}
        self._service_cache = {}
        
        self._tag_archives = {}
        
    
    def _ClearOrphans( self, move_location = None ):
        
        job_key = ClientThreading.JobKey( cancellable = True )
        
        job_key.SetVariable( 'popup_title', 'clearing orphans' )
        job_key.SetVariable( 'popup_text_1', 'preparing' )
        
        self._controller.pub( 'message', job_key )
        
        orphan_paths = []
        orphan_thumbnails = []
        
        client_files_manager = self._controller.GetClientFilesManager()
        
        for ( i, path ) in enumerate( client_files_manager.IterateAllFilePaths() ):
            
            ( i_paused, should_quit ) = job_key.WaitIfNeeded()
            
            if should_quit:
                
                return
                
            
            if i % 100 == 0:
                
                status = 'reviewed ' + HydrusData.ConvertIntToPrettyString( i ) + ' files, found ' + HydrusData.ConvertIntToPrettyString( len( orphan_paths ) ) + ' orphans'
                
                job_key.SetVariable( 'popup_text_1', status )
                
            
            try:
                
                is_an_orphan = False
                
                ( directory, filename ) = os.path.split( path )
                
                if '.' in filename:
                    
                    ( should_be_a_hex_hash, ext ) = filename.split( '.', 1 )
                    
                    hash = should_be_a_hex_hash.decode( 'hex' )
                    
                    if self._HashExists( hash ):
                        
                        hash_id = self._GetHashId( hash )
                        
                        result = self._c.execute( 'SELECT 1 FROM current_files WHERE service_id IN ( ?, ? ) AND hash_id = ?;', ( self._local_file_service_id, self._trash_service_id, hash_id ) ).fetchone()
                        
                        if result is None:
                            
                            is_an_orphan = True
                            
                        
                    else:
                        
                        is_an_orphan = True
                        
                    
                else:
                    
                    is_an_orphan = True
                    
                
            except:
                
                is_an_orphan = True
                
            
            if is_an_orphan:
                
                orphan_paths.append( path )
                
            
        
        time.sleep( 2 )
        
        for ( i, path ) in enumerate( ClientFiles.IterateAllThumbnailPaths() ):
            
            ( i_paused, should_quit ) = job_key.WaitIfNeeded()
            
            if should_quit:
                
                return
                
            
            if i % 100 == 0:
                
                status = 'reviewed ' + HydrusData.ConvertIntToPrettyString( i ) + ' thumbnails, found ' + HydrusData.ConvertIntToPrettyString( len( orphan_thumbnails ) ) + ' orphans'
                
                job_key.SetVariable( 'popup_text_1', status )
                
            
            try:
                
                is_an_orphan = False
                
                ( directory, filename ) = os.path.split( path )
                
                if filename.endswith( '_resized' ):
                    
                    should_be_a_hex_hash = filename.replace( '_resized', '' )
                    
                else:
                    
                    should_be_a_hex_hash = filename
                    
                
                hash = should_be_a_hex_hash.decode( 'hex' )
                
                if self._HashExists( hash ):
                    
                    hash_id = self._GetHashId( hash )
                    
                    result = self._c.execute( 'SELECT 1 FROM current_files WHERE hash_id = ?;', ( hash_id, ) ).fetchone()
                    
                    if result is None:
                        
                        is_an_orphan = True
                        
                    
                else:
                    
                    is_an_orphan = True
                    
                
            except:
                
                is_an_orphan = True
                
            
            if is_an_orphan:
                
                orphan_thumbnails.append( path )
                
            
        
        time.sleep( 2 )
        
        if len( orphan_paths ) > 0:
            
            if move_location is None:
                
                status = 'found ' + HydrusData.ConvertIntToPrettyString( len( orphan_paths ) ) + ' orphans, now deleting'
                
                job_key.SetVariable( 'popup_text_1', status )
                
                time.sleep( 5 )
                
                for path in orphan_paths:
                    
                    ( i_paused, should_quit ) = job_key.WaitIfNeeded()
                    
                    if should_quit:
                        
                        return
                        
                    
                    HydrusData.Print( 'Deleting the orphan ' + path )
                    
                    status = 'deleting orphan files: ' + HydrusData.ConvertValueRangeToPrettyString( i + 1, len( orphan_paths ) )
                    
                    job_key.SetVariable( 'popup_text_1', status )
                    
                    HydrusPaths.DeletePath( path )
                    
                
            else:
                
                status = 'found ' + HydrusData.ConvertIntToPrettyString( len( orphan_paths ) ) + ' orphans, now moving to ' + move_location
                
                job_key.SetVariable( 'popup_text_1', status )
                
                time.sleep( 5 )
                
                for path in orphan_paths:
                    
                    ( i_paused, should_quit ) = job_key.WaitIfNeeded()
                    
                    if should_quit:
                        
                        return
                        
                    
                    ( source_dir, filename ) = os.path.split( path )
                    
                    dest = os.path.join( move_location, filename )
                    
                    dest = HydrusPaths.AppendPathUntilNoConflicts( dest )
                    
                    HydrusData.Print( 'Moving the orphan ' + path + ' to ' + dest )
                    
                    status = 'moving orphan files: ' + HydrusData.ConvertValueRangeToPrettyString( i + 1, len( orphan_paths ) )
                    
                    job_key.SetVariable( 'popup_text_1', status )
                    
                    shutil.move( path, dest )
                    
                
            
        
        if len( orphan_thumbnails ) > 0:
            
            status = 'found ' + HydrusData.ConvertIntToPrettyString( len( orphan_thumbnails ) ) + ' orphan thumbnails, now deleting'
            
            job_key.SetVariable( 'popup_text_1', status )
            
            time.sleep( 5 )
            
            for ( i, path ) in enumerate( orphan_thumbnails ):
                
                ( i_paused, should_quit ) = job_key.WaitIfNeeded()
                
                if should_quit:
                    
                    return
                    
                
                status = 'deleting orphan thumbnails: ' + HydrusData.ConvertValueRangeToPrettyString( i + 1, len( orphan_thumbnails ) )
                
                job_key.SetVariable( 'popup_text_1', status )
                
                HydrusData.Print( 'Deleting the orphan ' + path )
                
                HydrusPaths.DeletePath( path )
                
            
        
        if len( orphan_paths ) == 0 and len( orphan_thumbnails ) == 0:
            
            final_text = 'no orphans found!'
            
        else:
            
            final_text = HydrusData.ConvertIntToPrettyString( len( orphan_paths ) ) + ' orphan files and ' + HydrusData.ConvertIntToPrettyString( len( orphan_thumbnails ) ) + ' orphan thumbnails cleared!'
            
        
        job_key.SetVariable( 'popup_text_1', final_text )
        
        HydrusData.Print( job_key.ToString() )
        
        job_key.Finish()
        
    
    def _CopyFiles( self, hashes ):
        
        client_files_manager = self._controller.GetClientFilesManager()
        
        if len( hashes ) > 0:
            
            error_messages = set()
            
            paths = []
            
            for hash in hashes:
                
                try:
                    
                    path = client_files_manager.GetFilePath( hash )
                    
                    paths.append( path )
                    
                except Exception as e:
                    
                    error_messages.add( HydrusData.ToUnicode( e ) )
                    
                
            
            self.pub_after_commit( 'clipboard', 'paths', paths )
            
            if len( error_messages ) > 0:
                
                raise Exception( 'Some of the file copies failed with the following error message(s):' + os.linesep + os.linesep.join( error_messages ) )
                
            
        
    
    def _CreateDB( self ):
        
        HydrusGlobals.is_first_start = True
        
        if not os.path.exists( HC.CLIENT_ARCHIVES_DIR ): os.makedirs( HC.CLIENT_ARCHIVES_DIR )
        if not os.path.exists( HC.CLIENT_FILES_DIR ): os.makedirs( HC.CLIENT_FILES_DIR )
        if not os.path.exists( HC.CLIENT_THUMBNAILS_DIR ): os.makedirs( HC.CLIENT_THUMBNAILS_DIR )
        if not os.path.exists( HC.CLIENT_UPDATES_DIR ): os.makedirs( HC.CLIENT_UPDATES_DIR )
        
        for prefix in HydrusData.IterateHexPrefixes():
            
            dir = os.path.join( HC.CLIENT_THUMBNAILS_DIR, prefix )
            
            if not os.path.exists( dir ): os.makedirs( dir )
            
        
        HydrusDB.SetupDBCreatePragma( self._c, no_wal = self._no_wal )
        
        try: self._c.execute( 'BEGIN IMMEDIATE;' )
        except Exception as e:
            
            raise HydrusExceptions.DBAccessException( HydrusData.ToUnicode( e ) )
            
        
        self._c.execute( 'CREATE TABLE services ( service_id INTEGER PRIMARY KEY AUTOINCREMENT, service_key BLOB_BYTES, service_type INTEGER, name TEXT, info TEXT_YAML );' )
        self._c.execute( 'CREATE UNIQUE INDEX services_service_key_index ON services ( service_key );' )
        
        # main
        
        self._c.execute( 'CREATE TABLE analyze_timestamps ( name TEXT, timestamp INTEGER );' )
        
        self._c.execute( 'CREATE TABLE client_files_locations ( prefix TEXT, location TEXT );' )
        
        self._c.execute( 'CREATE TABLE contacts ( contact_id INTEGER PRIMARY KEY, contact_key BLOB_BYTES, public_key TEXT, name TEXT, host TEXT, port INTEGER );' )
        self._c.execute( 'CREATE UNIQUE INDEX contacts_contact_key_index ON contacts ( contact_key );' )
        self._c.execute( 'CREATE UNIQUE INDEX contacts_name_index ON contacts ( name );' )
        
        self._c.execute( 'CREATE VIRTUAL TABLE conversation_subjects USING fts4( subject );' )
        
        self._c.execute( 'CREATE TABLE current_files ( service_id INTEGER REFERENCES services ON DELETE CASCADE, hash_id INTEGER, timestamp INTEGER, PRIMARY KEY( service_id, hash_id ) );' )
        self._c.execute( 'CREATE INDEX current_files_timestamp ON current_files ( timestamp );' )
        
        self._c.execute( 'CREATE TABLE deleted_files ( service_id INTEGER REFERENCES services ON DELETE CASCADE, hash_id INTEGER, PRIMARY KEY( service_id, hash_id ) );' )
        
        self._c.execute( 'CREATE TABLE existing_tags ( namespace_id INTEGER, tag_id INTEGER, PRIMARY KEY( namespace_id, tag_id ) );' )
        self._c.execute( 'CREATE INDEX existing_tags_tag_id_index ON existing_tags ( tag_id );' )
        
        self._c.execute( 'CREATE TABLE file_inbox ( hash_id INTEGER PRIMARY KEY );' )
        
        self._c.execute( 'CREATE TABLE files_info ( hash_id INTEGER PRIMARY KEY, size INTEGER, mime INTEGER, width INTEGER, height INTEGER, duration INTEGER, num_frames INTEGER, num_words INTEGER );' )
        self._c.execute( 'CREATE INDEX files_info_size ON files_info ( size );' )
        self._c.execute( 'CREATE INDEX files_info_mime ON files_info ( mime );' )
        self._c.execute( 'CREATE INDEX files_info_width ON files_info ( width );' )
        self._c.execute( 'CREATE INDEX files_info_height ON files_info ( height );' )
        self._c.execute( 'CREATE INDEX files_info_duration ON files_info ( duration );' )
        self._c.execute( 'CREATE INDEX files_info_num_frames ON files_info ( num_frames );' )
        
        self._c.execute( 'CREATE TABLE file_transfers ( service_id INTEGER REFERENCES services ON DELETE CASCADE, hash_id INTEGER, PRIMARY KEY( service_id, hash_id ) );' )
        self._c.execute( 'CREATE INDEX file_transfers_hash_id ON file_transfers ( hash_id );' )
        
        self._c.execute( 'CREATE TABLE file_trash ( hash_id INTEGER PRIMARY KEY, timestamp INTEGER );' )
        self._c.execute( 'CREATE INDEX file_trash_timestamp ON file_trash ( timestamp );' )
        
        self._c.execute( 'CREATE TABLE file_petitions ( service_id INTEGER, hash_id INTEGER, reason_id INTEGER, PRIMARY KEY( service_id, hash_id, reason_id ) );' )
        self._c.execute( 'CREATE INDEX file_petitions_hash_id_index ON file_petitions ( hash_id );' )
        
        self._c.execute( 'CREATE TABLE hydrus_sessions ( service_id INTEGER PRIMARY KEY REFERENCES services ON DELETE CASCADE, session_key BLOB_BYTES, expiry INTEGER );' )
        
        self._c.execute( 'CREATE TABLE json_dict ( name TEXT PRIMARY KEY, dump BLOB_BYTES );' )
        self._c.execute( 'CREATE TABLE json_dumps ( dump_type INTEGER PRIMARY KEY, version INTEGER, dump BLOB_BYTES );' )
        self._c.execute( 'CREATE TABLE json_dumps_named ( dump_type INTEGER, dump_name TEXT, version INTEGER, dump BLOB_BYTES, PRIMARY KEY ( dump_type, dump_name ) );' )
        
        self._c.execute( 'CREATE TABLE local_hashes ( hash_id INTEGER PRIMARY KEY, md5 BLOB_BYTES, sha1 BLOB_BYTES, sha512 BLOB_BYTES );' )
        self._c.execute( 'CREATE INDEX local_hashes_md5_index ON local_hashes ( md5 );' )
        self._c.execute( 'CREATE INDEX local_hashes_sha1_index ON local_hashes ( sha1 );' )
        self._c.execute( 'CREATE INDEX local_hashes_sha512_index ON local_hashes ( sha512 );' )
        
        self._c.execute( 'CREATE TABLE local_ratings ( service_id INTEGER REFERENCES services ON DELETE CASCADE, hash_id INTEGER, rating REAL, PRIMARY KEY( service_id, hash_id ) );' )
        self._c.execute( 'CREATE INDEX local_ratings_hash_id_index ON local_ratings ( hash_id );' )
        self._c.execute( 'CREATE INDEX local_ratings_rating_index ON local_ratings ( rating );' )
        
        self._c.execute( 'CREATE TABLE message_attachments ( message_id INTEGER PRIMARY KEY REFERENCES message_keys ON DELETE CASCADE, hash_id INTEGER );' )
        
        self._c.execute( 'CREATE TABLE message_depots ( service_id INTEGER PRIMARY KEY REFERENCES services ON DELETE CASCADE, contact_id INTEGER, last_check INTEGER, check_period INTEGER, private_key TEXT, receive_anon INTEGER_BOOLEAN );' )
        self._c.execute( 'CREATE UNIQUE INDEX message_depots_contact_id_index ON message_depots ( contact_id );' )
        
        self._c.execute( 'CREATE TABLE message_destination_map ( message_id INTEGER REFERENCES message_keys ON DELETE CASCADE, contact_id_to INTEGER, status_id INTEGER, PRIMARY KEY ( message_id, contact_id_to ) );' )
        self._c.execute( 'CREATE INDEX message_destination_map_contact_id_to_index ON message_destination_map ( contact_id_to );' )
        self._c.execute( 'CREATE INDEX message_destination_map_status_id_index ON message_destination_map ( status_id );' )
        
        self._c.execute( 'CREATE TABLE message_downloads ( service_id INTEGER REFERENCES services ON DELETE CASCADE, message_id INTEGER REFERENCES message_keys ON DELETE CASCADE );' )
        self._c.execute( 'CREATE INDEX message_downloads_service_id_index ON message_downloads ( service_id );' )
        
        self._c.execute( 'CREATE TABLE message_drafts ( message_id INTEGER REFERENCES message_keys ON DELETE CASCADE, recipients_visible INTEGER_BOOLEAN );' )
        
        self._c.execute( 'CREATE TABLE message_inbox ( message_id INTEGER PRIMARY KEY REFERENCES message_keys ON DELETE CASCADE );' )
        
        self._c.execute( 'CREATE TABLE message_keys ( message_id INTEGER PRIMARY KEY, message_key BLOB_BYTES );' )
        self._c.execute( 'CREATE INDEX message_keys_message_key_index ON message_keys ( message_key );' )
        
        self._c.execute( 'CREATE VIRTUAL TABLE message_bodies USING fts4( body );' )
        
        self._c.execute( 'CREATE TABLE incoming_message_statuses ( message_id INTEGER REFERENCES message_keys ON DELETE CASCADE, contact_key BLOB_BYTES, status_id INTEGER, PRIMARY KEY ( message_id, contact_key ) );' )
        
        self._c.execute( 'CREATE TABLE messages ( conversation_id INTEGER REFERENCES message_keys ( message_id ) ON DELETE CASCADE, message_id INTEGER REFERENCES message_keys ON DELETE CASCADE, contact_id_from INTEGER, timestamp INTEGER, PRIMARY KEY( conversation_id, message_id ) );' )
        self._c.execute( 'CREATE UNIQUE INDEX messages_message_id_index ON messages ( message_id );' )
        self._c.execute( 'CREATE INDEX messages_contact_id_from_index ON messages ( contact_id_from );' )
        self._c.execute( 'CREATE INDEX messages_timestamp_index ON messages ( timestamp );' )
        
        self._c.execute( 'CREATE TABLE news ( service_id INTEGER REFERENCES services ON DELETE CASCADE, post TEXT, timestamp INTEGER );' )
        
        self._c.execute( 'CREATE TABLE options ( options TEXT_YAML );', )
        
        self._c.execute( 'CREATE TABLE perceptual_hashes ( hash_id INTEGER PRIMARY KEY, phash BLOB_BYTES );' )
        
        self._c.execute( 'CREATE TABLE remote_ratings ( service_id INTEGER REFERENCES services ON DELETE CASCADE, hash_id INTEGER, count INTEGER, rating REAL, score REAL, PRIMARY KEY( service_id, hash_id ) );' )
        self._c.execute( 'CREATE INDEX remote_ratings_hash_id_index ON remote_ratings ( hash_id );' )
        self._c.execute( 'CREATE INDEX remote_ratings_rating_index ON remote_ratings ( rating );' )
        self._c.execute( 'CREATE INDEX remote_ratings_score_index ON remote_ratings ( score );' )
        
        self._c.execute( 'CREATE TABLE service_filenames ( service_id INTEGER REFERENCES services ON DELETE CASCADE, hash_id INTEGER, filename TEXT, PRIMARY KEY( service_id, hash_id ) );' )
        self._c.execute( 'CREATE TABLE service_directories ( service_id INTEGER REFERENCES services ON DELETE CASCADE, directory_id INTEGER, num_files INTEGER, total_size INTEGER, PRIMARY KEY( service_id, directory_id ) );' )
        self._c.execute( 'CREATE TABLE service_directory_file_map ( service_id INTEGER REFERENCES services ON DELETE CASCADE, directory_id INTEGER, hash_id INTEGER, PRIMARY KEY( service_id, directory_id, hash_id ) );' )
        
        self._c.execute( 'CREATE TABLE service_info ( service_id INTEGER REFERENCES services ON DELETE CASCADE, info_type INTEGER, info INTEGER, PRIMARY KEY ( service_id, info_type ) );' )
        
        self._c.execute( 'CREATE TABLE statuses ( status_id INTEGER PRIMARY KEY, status TEXT );' )
        self._c.execute( 'CREATE UNIQUE INDEX statuses_status_index ON statuses ( status );' )
        
        self._c.execute( 'CREATE TABLE tag_censorship ( service_id INTEGER PRIMARY KEY REFERENCES services ON DELETE CASCADE, blacklist INTEGER_BOOLEAN, tags TEXT_YAML );' )
        
        self._c.execute( 'CREATE TABLE tag_parents ( service_id INTEGER REFERENCES services ON DELETE CASCADE, child_namespace_id INTEGER, child_tag_id INTEGER, parent_namespace_id INTEGER, parent_tag_id INTEGER, status INTEGER, PRIMARY KEY ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, status ) );' )
        self._c.execute( 'CREATE INDEX tag_parents_service_id_status_index ON tag_parents ( service_id, status );' )
        self._c.execute( 'CREATE INDEX tag_parents_status_index ON tag_parents ( status );' )
        
        self._c.execute( 'CREATE TABLE tag_parent_petitions ( service_id INTEGER REFERENCES services ON DELETE CASCADE, child_namespace_id INTEGER, child_tag_id INTEGER, parent_namespace_id INTEGER, parent_tag_id INTEGER, status INTEGER, reason_id INTEGER, PRIMARY KEY ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, status ) );' )
        
        self._c.execute( 'CREATE TABLE tag_siblings ( service_id INTEGER REFERENCES services ON DELETE CASCADE, old_namespace_id INTEGER, old_tag_id INTEGER, new_namespace_id INTEGER, new_tag_id INTEGER, status INTEGER, PRIMARY KEY ( service_id, old_namespace_id, old_tag_id, status ) );' )
        self._c.execute( 'CREATE INDEX tag_siblings_service_id_status_index ON tag_siblings ( service_id, status );' )
        self._c.execute( 'CREATE INDEX tag_siblings_status_index ON tag_siblings ( status );' )
        
        self._c.execute( 'CREATE TABLE tag_sibling_petitions ( service_id INTEGER REFERENCES services ON DELETE CASCADE, old_namespace_id INTEGER, old_tag_id INTEGER, new_namespace_id INTEGER, new_tag_id INTEGER, status INTEGER, reason_id INTEGER, PRIMARY KEY ( service_id, old_namespace_id, old_tag_id, status ) );' )
        
        self._c.execute( 'CREATE TABLE urls ( url TEXT PRIMARY KEY, hash_id INTEGER );' )
        self._c.execute( 'CREATE INDEX urls_hash_id ON urls ( hash_id );' )
        
        self._c.execute( 'CREATE TABLE vacuum_timestamps ( name TEXT, timestamp INTEGER );' )
        
        self._c.execute( 'CREATE TABLE version ( version INTEGER );' )
        
        self._c.execute( 'CREATE TABLE web_sessions ( name TEXT PRIMARY KEY, cookies TEXT_YAML, expiry INTEGER );' )
        
        self._c.execute( 'CREATE TABLE yaml_dumps ( dump_type INTEGER, dump_name TEXT, dump TEXT_YAML, PRIMARY KEY ( dump_type, dump_name ) );' )
        
        # master
        
        self._c.execute( 'CREATE TABLE IF NOT EXISTS external_master.hashes ( hash_id INTEGER PRIMARY KEY, hash BLOB_BYTES UNIQUE );' )
        
        self._c.execute( 'CREATE TABLE IF NOT EXISTS external_master.namespaces ( namespace_id INTEGER PRIMARY KEY, namespace TEXT UNIQUE );' )
        
        self._c.execute( 'CREATE TABLE IF NOT EXISTS external_master.tags ( tag_id INTEGER PRIMARY KEY, tag TEXT UNIQUE );' )
        
        self._c.execute( 'CREATE VIRTUAL TABLE IF NOT EXISTS external_master.tags_fts4 USING fts4( tag );' )
        
        self._c.execute( 'CREATE TABLE IF NOT EXISTS external_master.texts ( text_id INTEGER PRIMARY KEY, text TEXT UNIQUE );' )
        
        # inserts
        
        location = HydrusPaths.ConvertAbsPathToPortablePath( HC.CLIENT_FILES_DIR )
        
        for prefix in HydrusData.IterateHexPrefixes():
            
            self._c.execute( 'INSERT INTO client_files_locations ( prefix, location ) VALUES ( ?, ? );', ( prefix, location ) )
            
        
        init_service_info = []
        
        init_service_info.append( ( CC.LOCAL_FILE_SERVICE_KEY, HC.LOCAL_FILE, CC.LOCAL_FILE_SERVICE_KEY ) )
        init_service_info.append( ( CC.TRASH_SERVICE_KEY, HC.LOCAL_FILE, CC.TRASH_SERVICE_KEY ) )
        init_service_info.append( ( CC.LOCAL_TAG_SERVICE_KEY, HC.LOCAL_TAG, CC.LOCAL_TAG_SERVICE_KEY ) )
        init_service_info.append( ( CC.COMBINED_FILE_SERVICE_KEY, HC.COMBINED_FILE, CC.COMBINED_FILE_SERVICE_KEY ) )
        init_service_info.append( ( CC.COMBINED_TAG_SERVICE_KEY, HC.COMBINED_TAG, CC.COMBINED_TAG_SERVICE_KEY ) )
        init_service_info.append( ( CC.LOCAL_BOORU_SERVICE_KEY, HC.LOCAL_BOORU, CC.LOCAL_BOORU_SERVICE_KEY ) )
        
        self._combined_files_ac_caches = {}
        
        for ( service_key, service_type, name ) in init_service_info:
            
            info = {}
            
            self._AddService( service_key, service_type, name, info )
            
        
        self._c.executemany( 'INSERT INTO yaml_dumps VALUES ( ?, ?, ? );', ( ( YAML_DUMP_ID_REMOTE_BOORU, name, booru ) for ( name, booru ) in ClientDefaults.GetDefaultBoorus().items() ) )
        
        self._c.executemany( 'INSERT INTO yaml_dumps VALUES ( ?, ?, ? );', ( ( YAML_DUMP_ID_IMAGEBOARD, name, imageboards ) for ( name, imageboards ) in ClientDefaults.GetDefaultImageboards() ) )
        
        new_options = ClientData.ClientOptions()
        
        self._SetJSONDump( new_options )
        
        self._c.execute( 'INSERT INTO namespaces ( namespace_id, namespace ) VALUES ( ?, ? );', ( 1, '' ) )
        
        self._c.execute( 'INSERT INTO version ( version ) VALUES ( ? );', ( HC.SOFTWARE_VERSION, ) )
        
        self._c.execute( 'COMMIT;' )
        
    
    def _DeleteFiles( self, service_id, hash_ids, files_being_undeleted = False ):
        
        splayed_hash_ids = HydrusData.SplayListForDB( hash_ids )
        
        rows = self._c.execute( 'SELECT hash_id, timestamp FROM current_files WHERE service_id = ? AND hash_id IN ' + splayed_hash_ids + ';', ( service_id, ) ).fetchall()
        
        valid_hash_ids = { row[ 0 ] for row in rows }
        
        if len( valid_hash_ids ) > 0:
            
            splayed_valid_hash_ids = HydrusData.SplayListForDB( valid_hash_ids )
            
            info = self._c.execute( 'SELECT size, mime FROM files_info WHERE hash_id IN ' + splayed_hash_ids + ';' ).fetchall()
            
            num_files = len( valid_hash_ids )
            delta_size = sum( ( size for ( size, mime ) in info ) )
            num_thumbnails = sum( ( 1 for ( size, mime ) in info if mime in HC.MIMES_WITH_THUMBNAILS ) )
            num_inbox = len( valid_hash_ids.intersection( self._inbox_hash_ids ) )
            
            service_info_updates = []
            
            service_info_updates.append( ( -delta_size, service_id, HC.SERVICE_INFO_TOTAL_SIZE ) )
            service_info_updates.append( ( -num_files, service_id, HC.SERVICE_INFO_NUM_FILES ) )
            service_info_updates.append( ( -num_thumbnails, service_id, HC.SERVICE_INFO_NUM_THUMBNAILS ) )
            service_info_updates.append( ( -num_inbox, service_id, HC.SERVICE_INFO_NUM_INBOX ) )
            
            if not files_being_undeleted:
                
                # an undelete moves from trash to local, which shouldn't be remembered as a delete from the trash service
                
                service_info_updates.append( ( num_files, service_id, HC.SERVICE_INFO_NUM_DELETED_FILES ) )
                
                self._c.executemany( 'INSERT OR IGNORE INTO deleted_files ( service_id, hash_id ) VALUES ( ?, ? );', [ ( service_id, hash_id ) for hash_id in hash_ids ] )
                
            
            self._c.executemany( 'UPDATE service_info SET info = info + ? WHERE service_id = ? AND info_type = ?;', service_info_updates )
            
            if num_thumbnails > 0:
                
                self._c.execute( 'DELETE FROM service_info WHERE service_id = ? AND info_type = ' + str( HC.SERVICE_INFO_NUM_THUMBNAILS_LOCAL ) + ';', ( service_id, ) )
                
            
            self._c.execute( 'DELETE FROM current_files WHERE service_id = ? AND hash_id IN ' + splayed_hash_ids + ';', ( service_id, ) )
            self._c.execute( 'DELETE FROM file_petitions WHERE service_id = ? AND hash_id IN ' + splayed_hash_ids + ';', ( service_id, ) )
            
            if service_id == self._local_file_service_id:
                
                self._AddFiles( self._trash_service_id, rows )
                
            
            if service_id == self._trash_service_id:
                
                self._c.execute( 'DELETE FROM file_trash WHERE hash_id IN ' + splayed_hash_ids + ';' )
                
                if not files_being_undeleted:
                    
                    self._ArchiveFiles( hash_ids )
                    
                    self._DeletePhysicalFiles( hash_ids )
                    
                
            
            service = self._GetService( service_id )
            
            service_type = service.GetServiceType()
            
            if service_type in ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ):
                
                tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
                
                for tag_service_id in tag_service_ids:
                    
                    self._CacheSpecificMappingsDeleteFiles( service_id, tag_service_id, valid_hash_ids )
                    
                
            
            self.pub_after_commit( 'notify_new_pending' )
            
        
    
    def _DeleteHydrusSessionKey( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        self._c.execute( 'DELETE FROM hydrus_sessions WHERE service_id = ?;', ( service_id, ) )
        
    
    def _DeleteJSONDump( self, dump_type ):
        
        self._c.execute( 'DELETE FROM json_dumps WHERE dump_type = ?;', ( dump_type, ) )
        
    
    def _DeleteJSONDumpNamed( self, dump_type, dump_name = None ):
        
        if dump_name is None:
            
            self._c.execute( 'DELETE FROM json_dumps_named WHERE dump_type = ?;', ( dump_type, ) )
            
        else:
            
            self._c.execute( 'DELETE FROM json_dumps_named WHERE dump_type = ? AND dump_name = ?;', ( dump_type, dump_name ) )
            
        
    
    def _DeletePending( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        service = self._GetService( service_id )
        
        if service.GetServiceType() == HC.TAG_REPOSITORY:
            
            ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
            
            pending_rescinded_mappings_ids = HydrusData.BuildKeyToListDict( [ ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM ' + pending_mappings_table_name + ';' ) ] )
            
            pending_rescinded_mappings_ids = [ ( namespace_id, tag_id, hash_ids ) for ( ( namespace_id, tag_id ), hash_ids ) in pending_rescinded_mappings_ids.items() ]
            
            petitioned_rescinded_mappings_ids = HydrusData.BuildKeyToListDict( [ ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM ' + petitioned_mappings_table_name + ';' ) ] )
            
            petitioned_rescinded_mappings_ids = [ ( namespace_id, tag_id, hash_ids ) for ( ( namespace_id, tag_id ), hash_ids ) in petitioned_rescinded_mappings_ids.items() ]
            
            self._UpdateMappings( service_id, pending_rescinded_mappings_ids = pending_rescinded_mappings_ids, petitioned_rescinded_mappings_ids = petitioned_rescinded_mappings_ids )
            
            self._c.execute( 'DELETE FROM tag_sibling_petitions WHERE service_id = ?;', ( service_id, ) )
            self._c.execute( 'DELETE FROM tag_parent_petitions WHERE service_id = ?;', ( service_id, ) )
            
        elif service.GetServiceType() in ( HC.FILE_REPOSITORY, HC.IPFS ):
            
            self._c.execute( 'DELETE FROM file_transfers WHERE service_id = ?;', ( service_id, ) )
            self._c.execute( 'DELETE FROM file_petitions WHERE service_id = ?;', ( service_id, ) )
            
        
        self.pub_after_commit( 'notify_new_pending' )
        self.pub_after_commit( 'notify_new_siblings' )
        self.pub_after_commit( 'notify_new_parents' )
        
        self.pub_service_updates_after_commit( { service_key : [ HydrusData.ServiceUpdate( HC.SERVICE_UPDATE_DELETE_PENDING ) ] } )
        
    
    def _DeletePhysicalFiles( self, hash_ids ):
        
        def DeletePaths( paths ):
            
            time.sleep( 5 )
            
            for path in paths:
                
                try:
                    
                    ClientData.DeletePath( path )
                    
                except OSError:
                    
                    HydrusData.Print( 'In trying to delete the orphan ' + path + ', this error was encountered:' )
                    HydrusData.Print( traceback.format_exc() )
                    
                except Exception as e:
                    
                    HydrusData.ShowException( e )
                    
                
            
        
        hash_ids = set( hash_ids )
        
        deletee_paths = set()
        
        potentially_pending_upload_hash_ids = { hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM file_transfers;', ) }
        
        deletable_file_hash_ids = hash_ids.difference( potentially_pending_upload_hash_ids )
        
        if len( deletable_file_hash_ids ) > 0:
            
            file_hashes = self._GetHashes( deletable_file_hash_ids )
            
            client_files_manager = self._controller.GetClientFilesManager()
            
            for hash in file_hashes:
                
                try:
                    
                    path = client_files_manager.GetFilePath( hash )
                    
                except HydrusExceptions.FileMissingException:
                    
                    continue
                    
                
                deletee_paths.add( path )
                
            
        
        useful_thumbnail_hash_ids = { hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM current_files WHERE service_id != ? AND hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';', ( self._trash_service_id, ) ) }
        
        deletable_thumbnail_hash_ids = hash_ids.difference( useful_thumbnail_hash_ids )
        
        if len( deletable_thumbnail_hash_ids ) > 0:
            
            thumbnail_hashes = self._GetHashes( deletable_thumbnail_hash_ids )
            
            for hash in thumbnail_hashes:
                
                path = ClientFiles.GetExpectedThumbnailPath( hash, True )
                resized_path = ClientFiles.GetExpectedThumbnailPath( hash, False )
                
                if os.path.exists( path ):
                    
                    deletee_paths.add( path )
                    
                
                if os.path.exists( resized_path ):
                    
                    deletee_paths.add( resized_path )
                    
                
            
            self._c.execute( 'DELETE from perceptual_hashes WHERE hash_id IN ' + HydrusData.SplayListForDB( deletable_thumbnail_hash_ids ) + ';' )
            
        
        self._controller.CallToThread( DeletePaths, deletee_paths )
        
    
    def _DeleteService( self, service_id, delete_update_dir = True ):
        
        service = self._GetService( service_id )
        
        service_key = service.GetServiceKey()
        service_type = service.GetServiceType()
        
        self._c.execute( 'DELETE FROM services WHERE service_id = ?;', ( service_id, ) )
        
        if service_type in HC.TAG_SERVICES:
            
            ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
            
            self._c.execute( 'DROP TABLE ' + current_mappings_table_name + ';' )
            self._c.execute( 'DROP TABLE ' + deleted_mappings_table_name + ';' )
            self._c.execute( 'DROP TABLE ' + pending_mappings_table_name + ';' )
            self._c.execute( 'DROP TABLE ' + petitioned_mappings_table_name + ';' )
            
            #
            
            self._CacheCombinedFilesMappingsDrop( service_id )
            
            file_service_ids = self._GetServiceIds( ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ) )
            
            for file_service_id in file_service_ids:
                
                self._CacheSpecificMappingsDrop( file_service_id, service_id )
                
            
        
        if service_type in ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ):
            
            tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
            
            for tag_service_id in tag_service_ids:
                
                self._CacheSpecificMappingsDrop( service_id, tag_service_id )
                
            
        
        if service_id in self._service_cache:
            
            del self._service_cache[ service_id ]
            
        
        if delete_update_dir:
            
            update_dir = ClientFiles.GetExpectedUpdateDir( service_key )
            
            if os.path.exists( update_dir ):
                
                ClientData.DeletePath( update_dir )
                
            
        
        service_update = HydrusData.ServiceUpdate( HC.SERVICE_UPDATE_RESET )
        
        service_keys_to_service_updates = { service_key : [ service_update ] }
        
        self.pub_service_updates_after_commit( service_keys_to_service_updates )
        
    
    def _DeleteServiceDirectory( self, service_id, dirname ):
        
        directory_id = self._GetTextId( dirname )
        
        self._c.execute( 'DELETE FROM service_directories WHERE service_id = ? AND directory_id = ?;', ( service_id, directory_id ) )
        self._c.execute( 'DELETE FROM service_directory_file_map WHERE service_id = ? AND directory_id = ?;', ( service_id, directory_id ) )
        
    
    def _DeleteServiceInfo( self ):
        
        self._c.execute( 'DELETE FROM service_info;' )
        
        self.pub_after_commit( 'notify_new_pending' )
        
    
    def _DeleteYAMLDump( self, dump_type, dump_name = None ):
        
        if dump_name is None: self._c.execute( 'DELETE FROM yaml_dumps WHERE dump_type = ?;', ( dump_type, ) )
        else:
            
            if dump_type == YAML_DUMP_ID_SUBSCRIPTION and dump_name in self._subscriptions_cache: del self._subscriptions_cache[ dump_name ]
            
            if dump_type == YAML_DUMP_ID_LOCAL_BOORU: dump_name = dump_name.encode( 'hex' )
            
            self._c.execute( 'DELETE FROM yaml_dumps WHERE dump_type = ? AND dump_name = ?;', ( dump_type, dump_name ) )
            
        
        if dump_type == YAML_DUMP_ID_LOCAL_BOORU:
            
            service_id = self._GetServiceId( CC.LOCAL_BOORU_SERVICE_KEY )
            
            self._c.execute( 'DELETE FROM service_info WHERE service_id = ? AND info_type = ?;', ( service_id, HC.SERVICE_INFO_NUM_SHARES ) )
            
            self._controller.pub( 'refresh_local_booru_shares' )
            
        
    
    def _ExportToTagArchive( self, path, service_key, hash_type, hashes = None ):
        
        # This could nicely take a whitelist or a blacklist for namespace filtering
        
        prefix_string = 'exporting to tag archive: '
        
        job_key = ClientThreading.JobKey( cancellable = True )
        
        job_key.SetVariable( 'popup_text_1', prefix_string + 'preparing' )
        
        self._controller.pub( 'message', job_key )
        
        service_id = self._GetServiceId( service_key )
        
        ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
        
        hta_exists = os.path.exists( path )
        
        hta = HydrusTagArchive.HydrusTagArchive( path )
        
        if hta_exists and hta.GetHashType() != hash_type:
            
            raise Exception( 'This tag archive does not use the expected hash type, so it cannot be exported to!' )
            
        
        if hashes is None:
            
            include_current = True
            include_pending = False
            
            hash_ids = self._GetHashIdsThatHaveTags( service_key, include_current, include_pending )
            
        else:
            
            hash_ids = self._GetHashIds( hashes )
            
        
        hta.BeginBigJob()
        
        for ( i, hash_id ) in enumerate( hash_ids ):
            
            ( i_paused, should_quit ) = job_key.WaitIfNeeded()
            
            if should_quit:
                
                return
                
            
            if i % 100 == 0:
                
                job_key.SetVariable( 'popup_text_1', prefix_string + HydrusData.ConvertValueRangeToPrettyString( i, len( hash_ids ) ) )
                job_key.SetVariable( 'popup_gauge_1', ( i, len( hash_ids ) ) )
                
            
            if hash_type == HydrusTagArchive.HASH_TYPE_SHA256: archive_hash = self._GetHash( hash_id )
            else:
                
                if hash_type == HydrusTagArchive.HASH_TYPE_MD5: h = 'md5'
                elif hash_type == HydrusTagArchive.HASH_TYPE_SHA1: h = 'sha1'
                elif hash_type == HydrusTagArchive.HASH_TYPE_SHA512: h = 'sha512'
                
                result = self._c.execute( 'SELECT ' + h + ' FROM local_hashes WHERE hash_id = ?;', ( hash_id, ) ).fetchone()
                
                if result is None: continue
                
                ( archive_hash, ) = result
                
            
            tags = { HydrusTags.CombineTag( namespace, tag ) for ( namespace, tag ) in self._c.execute( 'SELECT namespace, tag FROM namespaces, ( tags, ' + current_mappings_table_name + ' USING ( tag_id ) ) USING ( namespace_id ) WHERE hash_id = ?;', ( hash_id, ) ) }
            
            hta.AddMappings( archive_hash, tags )
            
        
        job_key.DeleteVariable( 'popup_gauge_1' )
        job_key.SetVariable( 'popup_text_1', prefix_string + 'committing the change and vacuuming the archive' )
        
        hta.CommitBigJob()
        
        job_key.SetVariable( 'popup_text_1', prefix_string + 'done!' )
        
        HydrusData.Print( job_key.ToString() )
        
        job_key.Finish()
        
    
    def _FilterHashes( self, hashes, file_service_key ):
        
        if file_service_key == CC.COMBINED_FILE_SERVICE_KEY:
            
            return hashes
            
        
        service_id = self._GetServiceId( file_service_key )
        
        hashes_result = []
        
        for hash in hashes:
            
            if not self._HashExists( hash ):
                
                continue
                
            
            hash_id = self._GetHashId( hash )
            
            result = self._c.execute( 'SELECT 1 FROM current_files WHERE service_id = ?;', ( service_id, ) ).fetchone()
            
            if result is not None:
                
                hashes_result.append( hash )
                
            
        
        return hashes_result
        
    
    def _GetAutocompleteCounts( self, tag_service_id, file_service_id, namespace_id_tag_ids, there_was_a_namespace, add_namespaceless ):
        
        namespace_ids_to_tag_ids = HydrusData.BuildKeyToListDict( namespace_id_tag_ids )
        
        if tag_service_id == self._combined_tag_service_id:
            
            search_tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
            
        else:
            
            search_tag_service_ids = [ tag_service_id ]
            
        
        cache_results = []
        
        if file_service_id == self._combined_file_service_id:
            
            cache_results.extend( self._CacheCombinedFilesMappingsGetAutocompleteCounts( tag_service_id, namespace_ids_to_tag_ids ) )
            
        else:
            
            for search_tag_service_id in search_tag_service_ids:
                
                cache_results.extend( self._CacheSpecificMappingsGetAutocompleteCounts( file_service_id, search_tag_service_id, namespace_ids_to_tag_ids ) )
                
            
        
        #
        
        current_ids_to_count = collections.Counter()
        pending_ids_to_count = collections.Counter()
        
        if not there_was_a_namespace and add_namespaceless:
            
            added_namespaceless_current_ids_to_count = collections.Counter()
            added_namespaceless_pending_ids_to_count = collections.Counter()
            tag_ids_to_incidence_count = collections.Counter()
            
        
        for ( namespace_id, tag_id, current_count, pending_count ) in cache_results:
            
            current_ids_to_count[ ( namespace_id, tag_id ) ] += current_count
            pending_ids_to_count[ ( namespace_id, tag_id ) ] += pending_count
            
            # prepare to add any namespaced counts to the namespaceless count
            
            if not there_was_a_namespace and add_namespaceless and ( current_count > 0 or pending_count > 0 ):
                
                tag_ids_to_incidence_count[ tag_id ] += 1
                
                if namespace_id != 1:
                    
                    added_namespaceless_current_ids_to_count[ tag_id ] += current_count
                    added_namespaceless_pending_ids_to_count[ tag_id ] += pending_count
                    
                
            
        
        # any instances of namespaceless counts that are just copies of a single namespaced count are not useful
        # e.g. 'series:evangelion (300)' is not benefitted by adding 'evangelion (300)'
        # so do not add them
        
        if not there_was_a_namespace and add_namespaceless:
            
            for ( tag_id, incidence ) in tag_ids_to_incidence_count.items():
                
                if incidence > 1:
                    
                    current_ids_to_count[ ( 1, tag_id ) ] += added_namespaceless_current_ids_to_count[ tag_id ]
                    pending_ids_to_count[ ( 1, tag_id ) ] += added_namespaceless_pending_ids_to_count[ tag_id ]
                    
                
            
        
        return ( current_ids_to_count, pending_ids_to_count )
        
    
    def _GetAutocompleteNamespaceIdTagIds( self, search_text, exact_match ):
        
        if exact_match:
            
            if not self._TagExists( search_text ):
                
                return set()
                
            
            ( namespace_id, tag_id ) = self._GetNamespaceIdTagId( search_text )
            
            if ':' in search_text:
                
                predicates_phrase = 'namespace_id = ' + str( namespace_id ) + ' AND tag_id = ' + str( tag_id )
                
            else:
                
                predicates_phrase = 'tag_id = ' + str( tag_id )
                
            
        else:
            
            normal_characters = set( 'abcdefghijklmnopqrstuvwxyz0123456789' )
            
            search_text_can_be_matched = True
            
            for character in search_text:
                
                if character not in normal_characters:
                    
                    search_text_can_be_matched = False
                    
                    break
                    
                
            
            def GetPossibleTagIds( half_complete_tag ):
                
                # the issue is that the tokenizer for fts4 doesn't like weird characters
                # a search for '[s' actually only does 's'
                # so, let's do the old and slower LIKE instead of MATCH in weird cases
                
                # note that queries with '*' are also passed to LIKE, because MATCH only supports appended wildcards 'gun*', and not complex stuff like '*gun*'
                
                if search_text_can_be_matched:
                    
                    return [ tag_id for ( tag_id, ) in self._c.execute( 'SELECT docid FROM tags_fts4 WHERE tag MATCH ?;', ( '"' + half_complete_tag + '*"', ) ) ]
                    
                else:
                    
                    possible_tag_ids_half_complete_tag = half_complete_tag
                    
                    if '*' in possible_tag_ids_half_complete_tag:
                        
                        possible_tag_ids_half_complete_tag = possible_tag_ids_half_complete_tag.replace( '*', '%' )
                        
                    else:
                        
                        possible_tag_ids_half_complete_tag += '%'
                        
                    
                    return [ tag_id for ( tag_id, ) in self._c.execute( 'SELECT tag_id FROM tags WHERE tag LIKE ? OR tag LIKE ?;', ( possible_tag_ids_half_complete_tag, '% ' + possible_tag_ids_half_complete_tag ) ) ]
                    
                
            
            if ':' in search_text:
                
                ( namespace, half_complete_tag ) = search_text.split( ':', 1 )
                
                if half_complete_tag == '':
                    
                    return set()
                    
                else:
                    
                    if '*' in namespace:
                        
                        wildcard_namespace = namespace.replace( '*', '%' )
                
                        possible_namespace_ids = [ namespace_id for ( namespace_id, ) in self._c.execute( 'SELECT namespace_id FROM namespaces WHERE namespace LIKE ?;', ( wildcard_namespace, ) ) ]
                        
                        predicates_phrase_1 = 'namespace_id IN ' + HydrusData.SplayListForDB( possible_namespace_ids )
                        
                    else:
                        
                        result = self._c.execute( 'SELECT namespace_id FROM namespaces WHERE namespace = ?;', ( namespace, ) ).fetchone()
                        
                        if result is None:
                            
                            return set()
                            
                        else:
                            
                            ( namespace_id, ) = result
                            
                            predicates_phrase_1 = 'namespace_id = ' + str( namespace_id )
                            
                        
                    
                    possible_tag_ids = GetPossibleTagIds( half_complete_tag )
                    
                    predicates_phrase = predicates_phrase_1 + ' AND tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids )
                    
                
            else:
                
                possible_tag_ids = GetPossibleTagIds( search_text )
                
                predicates_phrase = 'tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids )
                
            
        
        namespace_id_tag_ids = { namespace_id_tag_id for namespace_id_tag_id in self._c.execute( 'SELECT namespace_id, tag_id FROM existing_tags WHERE ' + predicates_phrase + ';' ) }
        
        # now fetch siblings, add to namespace_id_tag_ids set
        
        siblings_manager = self._controller.GetManager( 'tag_siblings' )
        
        all_associated_sibling_tags = siblings_manager.GetAutocompleteSiblings( search_text, exact_match )
        
        for sibling_tag in all_associated_sibling_tags:
            
            try: ( namespace_id, tag_id ) = self._GetNamespaceIdTagId( sibling_tag )
            except HydrusExceptions.SizeException: continue
            
            namespace_id_tag_ids.add( ( namespace_id, tag_id ) )
            
        
        return namespace_id_tag_ids
        
    
    def _GetAutocompletePredicates( self, tag_service_key = CC.COMBINED_TAG_SERVICE_KEY, file_service_key = CC.COMBINED_FILE_SERVICE_KEY, search_text = '', exact_match = False, include_current = True, include_pending = True, add_namespaceless = False ):
        
        namespace_id_tag_ids = self._GetAutocompleteNamespaceIdTagIds( search_text, exact_match )
        
        tag_service_id = self._GetServiceId( tag_service_key )
        file_service_id = self._GetServiceId( file_service_key )
        
        there_was_a_namespace = ':' in search_text
        
        ( current_ids_to_count, pending_ids_to_count ) = self._GetAutocompleteCounts( tag_service_id, file_service_id, namespace_id_tag_ids, there_was_a_namespace, add_namespaceless )
        
        #
        
        ids_to_do = set()
        
        if include_current: ids_to_do.update( ( id for ( id, count ) in current_ids_to_count.items() if count > 0 ) )
        if include_pending: ids_to_do.update( ( id for ( id, count ) in pending_ids_to_count.items() if count > 0 ) )
        
        ids_to_tags = { ( namespace_id, tag_id ) : self._GetNamespaceTag( namespace_id, tag_id ) for ( namespace_id, tag_id ) in ids_to_do }
        
        tag_info = [ ( ids_to_tags[ id ], current_ids_to_count[ id ], pending_ids_to_count[ id ] ) for id in ids_to_do ]
        
        tags_to_do = { tag for ( tag, current_count, pending_count ) in tag_info }
        
        tag_censorship_manager = self._controller.GetManager( 'tag_censorship' )
        
        filtered_tags = tag_censorship_manager.FilterTags( tag_service_key, tags_to_do )
        
        predicates = [ ClientSearch.Predicate( HC.PREDICATE_TYPE_TAG, tag, counts = { HC.CURRENT : current_count, HC.PENDING : pending_count } ) for ( tag, current_count, pending_count ) in tag_info if tag in filtered_tags ]
        
        return predicates
        
    
    def _GetClientFilesLocations( self ):
        
        result = { prefix : HydrusPaths.ConvertPortablePathToAbsPath( location ) for ( prefix, location ) in self._c.execute( 'SELECT prefix, location FROM client_files_locations;' ) }
        
        return result
        
    
    def _GetDirectoryHashes( self, service_key, dirname ):
        
        service_id = self._GetServiceId( service_key )
        directory_id = self._GetTextId( dirname )
        
        hash_ids = [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM service_directory_file_map WHERE service_id = ? AND directory_id = ?;', ( service_id, directory_id ) ) ]
        
        hashes = self._GetHashes( hash_ids )
        
        return hashes
        
    
    def _GetDirectoryInfo( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        incomplete_info = self._c.execute( 'SELECT directory_id, num_files, total_size FROM service_directories WHERE service_id = ?;', ( service_id, ) ).fetchall()
        
        info = [ ( self._GetText( directory_id ), num_files, total_size ) for ( directory_id, num_files, total_size ) in incomplete_info ]
        
        return info
        
    
    def _GetDownloads( self ): return { hash for ( hash, ) in self._c.execute( 'SELECT hash FROM file_transfers, hashes USING ( hash_id ) WHERE service_id = ?;', ( self._local_file_service_id, ) ) }
    
    def _GetFileHashes( self, given_hashes, given_hash_type, desired_hash_type ):
        
        if given_hash_type == 'sha256':
            
            hash_ids = self._GetHashIds( given_hashes )
            
        else:
            
            hash_ids = []
            
            for given_hash in given_hashes:
                
                if given_hash is None:
                    
                    continue
                    
                
                result = self._c.execute( 'SELECT hash_id FROM local_hashes WHERE ' + given_hash_type + ' = ?;', ( sqlite3.Binary( given_hash ), ) ).fetchone()
                
                if result is not None:
                    
                    ( hash_id, ) = result
                    
                    hash_ids.append( hash_id )
                    
                
            
        
        if desired_hash_type == 'sha256':
            
            desired_hashes = self._GetHashes( hash_ids )
            
        else:
            
            desired_hashes = [ desired_hash for ( desired_hash, ) in self._c.execute( 'SELECT ' + desired_hash_type + ' FROM local_hashes WHERE hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';' ) ]
            
        
        return desired_hashes
        
    
    def _GetFileSystemPredicates( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        service = self._GetService( service_id )
        
        service_type = service.GetServiceType()
        
        predicates = []
        
        if service_type in ( HC.COMBINED_FILE, HC.COMBINED_TAG ): predicates.extend( [ ClientSearch.Predicate( predicate_type, None ) for predicate_type in [ HC.PREDICATE_TYPE_SYSTEM_EVERYTHING, HC.PREDICATE_TYPE_SYSTEM_UNTAGGED, HC.PREDICATE_TYPE_SYSTEM_NUM_TAGS, HC.PREDICATE_TYPE_SYSTEM_LIMIT, HC.PREDICATE_TYPE_SYSTEM_HASH ] ] )
        elif service_type in HC.TAG_SERVICES:
            
            service_info = self._GetServiceInfoSpecific( service_id, service_type, { HC.SERVICE_INFO_NUM_FILES } )
            
            num_everything = service_info[ HC.SERVICE_INFO_NUM_FILES ]
            
            predicates.append( ClientSearch.Predicate( HC.PREDICATE_TYPE_SYSTEM_EVERYTHING, None, counts = { HC.CURRENT : num_everything } ) )
            
            predicates.extend( [ ClientSearch.Predicate( predicate_type, None ) for predicate_type in [ HC.PREDICATE_TYPE_SYSTEM_UNTAGGED, HC.PREDICATE_TYPE_SYSTEM_NUM_TAGS, HC.PREDICATE_TYPE_SYSTEM_LIMIT, HC.PREDICATE_TYPE_SYSTEM_HASH ] ] )
            
        elif service_type in ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ):
            
            service_info = self._GetServiceInfoSpecific( service_id, service_type, { HC.SERVICE_INFO_NUM_FILES, HC.SERVICE_INFO_NUM_INBOX } )
            
            num_everything = service_info[ HC.SERVICE_INFO_NUM_FILES ]
            num_inbox = service_info[ HC.SERVICE_INFO_NUM_INBOX ]
            num_archive = num_everything - num_inbox
            
            if service_type == HC.FILE_REPOSITORY:
                
                ( num_local, ) = self._c.execute( 'SELECT COUNT( * ) FROM current_files AS remote_current_files, current_files USING ( hash_id ) WHERE remote_current_files.service_id = ? AND current_files.service_id = ?;', ( service_id, self._local_file_service_id ) ).fetchone()
                
                num_not_local = num_everything - num_local
                
                num_archive = num_local - num_inbox
                
            
            predicates.append( ClientSearch.Predicate( HC.PREDICATE_TYPE_SYSTEM_EVERYTHING, None, counts = { HC.CURRENT : num_everything } ) )
            
            show_inbox_and_archive = True
            
            new_options = self._controller.GetNewOptions()
            
            if new_options.GetBoolean( 'filter_inbox_and_archive_predicates' ) and ( num_inbox == 0 or num_archive == 0 ):
                
                show_inbox_and_archive = False
                
            
            if show_inbox_and_archive:
                
                predicates.append( ClientSearch.Predicate( HC.PREDICATE_TYPE_SYSTEM_INBOX, None, counts = { HC.CURRENT : num_inbox } ) )
                predicates.append( ClientSearch.Predicate( HC.PREDICATE_TYPE_SYSTEM_ARCHIVE, None, counts = { HC.CURRENT : num_archive } ) )
                
            
            if service_type == HC.FILE_REPOSITORY:
                
                predicates.append( ClientSearch.Predicate( HC.PREDICATE_TYPE_SYSTEM_LOCAL, None, counts = { HC.CURRENT : num_local } ) )
                predicates.append( ClientSearch.Predicate( HC.PREDICATE_TYPE_SYSTEM_NOT_LOCAL, None, counts = { HC.CURRENT : num_not_local } ) )
                
            
            predicates.extend( [ ClientSearch.Predicate( predicate_type, None ) for predicate_type in [ HC.PREDICATE_TYPE_SYSTEM_UNTAGGED, HC.PREDICATE_TYPE_SYSTEM_NUM_TAGS, HC.PREDICATE_TYPE_SYSTEM_LIMIT, HC.PREDICATE_TYPE_SYSTEM_SIZE, HC.PREDICATE_TYPE_SYSTEM_AGE, HC.PREDICATE_TYPE_SYSTEM_HASH, HC.PREDICATE_TYPE_SYSTEM_DIMENSIONS, HC.PREDICATE_TYPE_SYSTEM_DURATION, HC.PREDICATE_TYPE_SYSTEM_NUM_WORDS, HC.PREDICATE_TYPE_SYSTEM_MIME ] ] )
            
            ratings_service_ids = self._GetServiceIds( HC.RATINGS_SERVICES )
            
            if len( ratings_service_ids ) > 0: predicates.append( ClientSearch.Predicate( HC.PREDICATE_TYPE_SYSTEM_RATING, None ) )
            
            predicates.extend( [ ClientSearch.Predicate( predicate_type, None ) for predicate_type in [ HC.PREDICATE_TYPE_SYSTEM_SIMILAR_TO, HC.PREDICATE_TYPE_SYSTEM_FILE_SERVICE ] ] )
            
        
        return predicates
        
    
    def _GetHash( self, hash_id ):
        
        result = self._c.execute( 'SELECT hash FROM hashes WHERE hash_id = ?;', ( hash_id, ) ).fetchone()
        
        if result is None:
            
            raise HydrusExceptions.DataMissing( 'File hash error in database' )
            
        
        ( hash, ) = result
        
        return hash
        
    
    def _GetHashes( self, hash_ids ): return [ hash for ( hash, ) in self._c.execute( 'SELECT hash FROM hashes WHERE hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';' ) ]
    
    def _GetHashId( self, hash ):
        
        result = self._c.execute( 'SELECT hash_id FROM hashes WHERE hash = ?;', ( sqlite3.Binary( hash ), ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT INTO hashes ( hash ) VALUES ( ? );', ( sqlite3.Binary( hash ), ) )
            
            hash_id = self._c.lastrowid
            
        else: ( hash_id, ) = result
        
        return hash_id
        
    
    def _GetHashIds( self, hashes ):
        
        hash_ids = set()
        hashes_not_in_db = set()
        
        for hash in hashes:
            
            if hash is None:
                
                continue
                
            
            result = self._c.execute( 'SELECT hash_id FROM hashes WHERE hash = ?;', ( sqlite3.Binary( hash ), ) ).fetchone()
            
            if result is None:
                
                hashes_not_in_db.add( hash )
                
            else:
                
                ( hash_id, ) = result
                
                hash_ids.add( hash_id )
                
            
        
        if len( hashes_not_in_db ) > 0:
            
            self._c.executemany( 'INSERT INTO hashes ( hash ) VALUES( ? );', ( ( sqlite3.Binary( hash ), ) for hash in hashes_not_in_db ) )
            
            for hash in hashes_not_in_db:
                
                ( hash_id, ) = self._c.execute( 'SELECT hash_id FROM hashes WHERE hash = ?;', ( sqlite3.Binary( hash ), ) ).fetchone()
                
                hash_ids.add( hash_id )
                
            
        
        return hash_ids
        
    
    def _GetHashIdsFromNamespace( self, file_service_key, tag_service_key, namespace, include_current_tags, include_pending_tags ):
        
        file_service_id = self._GetServiceId( file_service_key )
        tag_service_id = self._GetServiceId( tag_service_key )
        namespace_id = self._GetNamespaceId( namespace )
        
        current_selects = []
        pending_selects = []
        
        if tag_service_key == CC.COMBINED_TAG_SERVICE_KEY:
            
            search_tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
            
        else:
            
            search_tag_service_ids = [ tag_service_id ]
            
        
        for search_tag_service_id in search_tag_service_ids:
            
            ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( search_tag_service_id )
            
            if file_service_key == CC.COMBINED_FILE_SERVICE_KEY:
                
                current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ' WHERE namespace_id = ' + str( namespace_id ) + ';' )
                pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ' WHERE namespace_id = ' + str( namespace_id ) + ';' )
                
            else:
                
                current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND namespace_id = ' + str( namespace_id ) + ';' )
                pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND namespace_id = ' + str( namespace_id ) + ';' )
                
            
        
        hash_ids = set()
        
        if include_current_tags:
            
            for current_select in current_selects:
                
                hash_ids.update( ( id for ( id, ) in self._c.execute( current_select ) ) )
                
            
        
        if include_pending_tags:
            
            for pending_select in pending_selects:
                
                hash_ids.update( ( id for ( id, ) in self._c.execute( pending_select ) ) )
                
            
        
        return hash_ids
        
    
    def _GetHashIdsFromQuery( self, search_context ):
        
        self._controller.ResetIdleTimer()
        
        system_predicates = search_context.GetSystemPredicates()
        
        file_service_key = search_context.GetFileServiceKey()
        tag_service_key = search_context.GetTagServiceKey()
        
        file_service_id = self._GetServiceId( file_service_key )
        tag_service_id = self._GetServiceId( tag_service_key )
        
        file_service = self._GetService( file_service_id )
        tag_service = self._GetService( tag_service_id )
        
        file_service_type = file_service.GetServiceType()
        tag_service_type = tag_service.GetServiceType()
        
        tags_to_include = search_context.GetTagsToInclude()
        tags_to_exclude = search_context.GetTagsToExclude()
        
        namespaces_to_include = search_context.GetNamespacesToInclude()
        namespaces_to_exclude = search_context.GetNamespacesToExclude()
        
        wildcards_to_include = search_context.GetWildcardsToInclude()
        wildcards_to_exclude = search_context.GetWildcardsToExclude()
        
        include_current_tags = search_context.IncludeCurrentTags()
        include_pending_tags = search_context.IncludePendingTags()
        
        #
        
        files_info_predicates = []
        
        simple_preds = system_predicates.GetSimpleInfo()
        
        if 'min_size' in simple_preds: files_info_predicates.append( 'size > ' + str( simple_preds[ 'min_size' ] ) )
        if 'size' in simple_preds: files_info_predicates.append( 'size = ' + str( simple_preds[ 'size' ] ) )
        if 'max_size' in simple_preds: files_info_predicates.append( 'size < ' + str( simple_preds[ 'max_size' ] ) )
        
        if 'mimes' in simple_preds:
            
            mimes = simple_preds[ 'mimes' ]
            
            if len( mimes ) == 1:
                
                ( mime, ) = mimes
                
                files_info_predicates.append( 'mime = ' + str( mime ) )
                
            else: files_info_predicates.append( 'mime IN ' + HydrusData.SplayListForDB( mimes ) )
            
        
        if file_service_key != CC.COMBINED_FILE_SERVICE_KEY:
            
            if 'min_timestamp' in simple_preds: files_info_predicates.append( 'timestamp >= ' + str( simple_preds[ 'min_timestamp' ] ) )
            if 'max_timestamp' in simple_preds: files_info_predicates.append( 'timestamp <= ' + str( simple_preds[ 'max_timestamp' ] ) )
            
        
        if 'min_width' in simple_preds: files_info_predicates.append( 'width > ' + str( simple_preds[ 'min_width' ] ) )
        if 'width' in simple_preds: files_info_predicates.append( 'width = ' + str( simple_preds[ 'width' ] ) )
        if 'max_width' in simple_preds: files_info_predicates.append( 'width < ' + str( simple_preds[ 'max_width' ] ) )
        
        if 'min_height' in simple_preds: files_info_predicates.append( 'height > ' + str( simple_preds[ 'min_height' ] ) )
        if 'height' in simple_preds: files_info_predicates.append( 'height = ' + str( simple_preds[ 'height' ] ) )
        if 'max_height' in simple_preds: files_info_predicates.append( 'height < ' + str( simple_preds[ 'max_height' ] ) )
        
        if 'min_num_pixels' in simple_preds: files_info_predicates.append( 'width * height > ' + str( simple_preds[ 'min_num_pixels' ] ) )
        if 'num_pixels' in simple_preds: files_info_predicates.append( 'width * height = ' + str( simple_preds[ 'num_pixels' ] ) )
        if 'max_num_pixels' in simple_preds: files_info_predicates.append( 'width * height < ' + str( simple_preds[ 'max_num_pixels' ] ) )
        
        if 'min_ratio' in simple_preds:
            
            ( ratio_width, ratio_height ) = simple_preds[ 'min_ratio' ]
            
            files_info_predicates.append( '( width * 1.0 ) / height > ' + str( float( ratio_width ) ) + ' / ' + str( ratio_height ) )
            
        if 'ratio' in simple_preds:
            
            ( ratio_width, ratio_height ) = simple_preds[ 'ratio' ]
            
            files_info_predicates.append( '( width * 1.0 ) / height = ' + str( float( ratio_width ) ) + ' / ' + str( ratio_height ) )
            
        if 'max_ratio' in simple_preds:
            
            ( ratio_width, ratio_height ) = simple_preds[ 'max_ratio' ]
            
            files_info_predicates.append( '( width * 1.0 ) / height < ' + str( float( ratio_width ) ) + ' / ' + str( ratio_height ) )
            
        
        if 'min_num_words' in simple_preds: files_info_predicates.append( 'num_words > ' + str( simple_preds[ 'min_num_words' ] ) )
        if 'num_words' in simple_preds:
            
            num_words = simple_preds[ 'num_words' ]
            
            if num_words == 0: files_info_predicates.append( '( num_words IS NULL OR num_words = 0 )' )
            else: files_info_predicates.append( 'num_words = ' + str( num_words ) )
            
        if 'max_num_words' in simple_preds:
            
            max_num_words = simple_preds[ 'max_num_words' ]
            
            if max_num_words == 0: files_info_predicates.append( 'num_words < ' + str( max_num_words ) )
            else: files_info_predicates.append( '( num_words < ' + str( max_num_words ) + ' OR num_words IS NULL )' )
            
        
        if 'min_duration' in simple_preds: files_info_predicates.append( 'duration > ' + str( simple_preds[ 'min_duration' ] ) )
        if 'duration' in simple_preds:
            
            duration = simple_preds[ 'duration' ]
            
            if duration == 0: files_info_predicates.append( '( duration IS NULL OR duration = 0 )' )
            else: files_info_predicates.append( 'duration = ' + str( duration ) )
            
        if 'max_duration' in simple_preds:
            
            max_duration = simple_preds[ 'max_duration' ]
            
            if max_duration == 0: files_info_predicates.append( 'duration < ' + str( max_duration ) )
            else: files_info_predicates.append( '( duration < ' + str( max_duration ) + ' OR duration IS NULL )' )
            
        
        if len( tags_to_include ) > 0 or len( namespaces_to_include ) > 0 or len( wildcards_to_include ) > 0:
            
            query_hash_ids = None
            
            if len( tags_to_include ) > 0:
                
                query_hash_ids = HydrusData.IntelligentMassIntersect( ( self._GetHashIdsFromTag( file_service_key, tag_service_key, tag, include_current_tags, include_pending_tags ) for tag in tags_to_include ) )
                
            
            if len( namespaces_to_include ) > 0:
                
                namespace_query_hash_ids = HydrusData.IntelligentMassIntersect( ( self._GetHashIdsFromNamespace( file_service_key, tag_service_key, namespace, include_current_tags, include_pending_tags ) for namespace in namespaces_to_include ) )
                
                if query_hash_ids is None: query_hash_ids = namespace_query_hash_ids
                else: query_hash_ids.intersection_update( namespace_query_hash_ids )
                
            
            if len( wildcards_to_include ) > 0:
                
                wildcard_query_hash_ids = HydrusData.IntelligentMassIntersect( ( self._GetHashIdsFromWildcard( file_service_key, tag_service_key, wildcard, include_current_tags, include_pending_tags ) for wildcard in wildcards_to_include ) )
                
                if query_hash_ids is None: query_hash_ids = wildcard_query_hash_ids
                else: query_hash_ids.intersection_update( wildcard_query_hash_ids )
                
            
            if len( files_info_predicates ) > 0:
                
                if file_service_key == CC.COMBINED_FILE_SERVICE_KEY:
                    
                    query_hash_ids.intersection_update( [ id for ( id, ) in self._c.execute( 'SELECT hash_id FROM files_info WHERE ' + ' AND '.join( files_info_predicates ) + ';' ) ] )
                    
                else:
                    
                    files_info_predicates.insert( 0, 'service_id = ' + str( file_service_id ) )
                    
                    query_hash_ids.intersection_update( [ id for ( id, ) in self._c.execute( 'SELECT hash_id FROM current_files, files_info USING ( hash_id ) WHERE ' + ' AND '.join( files_info_predicates ) + ';' ) ] )
                    
                
            
        else:
            
            if file_service_key == CC.COMBINED_FILE_SERVICE_KEY:
                
                query_hash_ids = self._GetHashIdsThatHaveTags( tag_service_key, include_current_tags, include_pending_tags )
                
            else:
                
                files_info_predicates.insert( 0, 'service_id = ' + str( file_service_id ) )
                
                query_hash_ids = { id for ( id, ) in self._c.execute( 'SELECT hash_id FROM current_files, files_info USING ( hash_id ) WHERE ' + ' AND '.join( files_info_predicates ) + ';' ) }
                
            
        
        #
        
        if 'hash' in simple_preds:
            
            ( search_hash, search_hash_type ) = simple_preds[ 'hash' ]
            
            if search_hash_type != 'sha256':
                
                result = self._GetFileHashes( [ search_hash ], search_hash_type, 'sha256' )
                
                if len( result ) == 0:
                    
                    query_hash_ids = {}
                    
                else:
                    
                    ( search_hash, ) = result
                    
                    hash_id = self._GetHashId( search_hash )
                    
                    query_hash_ids.intersection_update( { hash_id } )
                    
                
            else:
                
                hash_id = self._GetHashId( search_hash )
                
                query_hash_ids.intersection_update( { hash_id } )
                
            
        
        #
        
        if system_predicates.HasSimilarTo():
            
            ( similar_to_hash, max_hamming ) = system_predicates.GetSimilarTo()
            
            hash_id = self._GetHashId( similar_to_hash )
            
            result = self._c.execute( 'SELECT phash FROM perceptual_hashes WHERE hash_id = ?;', ( hash_id, ) ).fetchone()
            
            if result is None:
                
                query_hash_ids = set()
                
            else:
                
                ( phash, ) = result
                
                similar_hash_ids = [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM perceptual_hashes WHERE hydrus_hamming( phash, ? ) <= ?;', ( sqlite3.Binary( phash ), max_hamming ) ) ]
                
                query_hash_ids.intersection_update( similar_hash_ids )
                
            
        
        #
        
        exclude_query_hash_ids = set()
        
        for tag in tags_to_exclude: exclude_query_hash_ids.update( self._GetHashIdsFromTag( file_service_key, tag_service_key, tag, include_current_tags, include_pending_tags ) )
        
        for namespace in namespaces_to_exclude: exclude_query_hash_ids.update( self._GetHashIdsFromNamespace( file_service_key, tag_service_key, namespace, include_current_tags, include_pending_tags ) )
        
        for wildcard in wildcards_to_exclude: exclude_query_hash_ids.update( self._GetHashIdsFromWildcard( file_service_key, tag_service_key, wildcard, include_current_tags, include_pending_tags ) )
        
        query_hash_ids.difference_update( exclude_query_hash_ids )
        
        #
        
        ( file_services_to_include_current, file_services_to_include_pending, file_services_to_exclude_current, file_services_to_exclude_pending ) = system_predicates.GetFileServiceInfo()
        
        for service_key in file_services_to_include_current:
            
            service_id = self._GetServiceId( service_key )
            
            query_hash_ids.intersection_update( [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM current_files WHERE service_id = ?;', ( service_id, ) ) ] )
            
        
        for service_key in file_services_to_include_pending:
            
            service_id = self._GetServiceId( service_key )
            
            query_hash_ids.intersection_update( [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM file_transfers WHERE service_id = ?;', ( service_id, ) ) ] )
            
        
        for service_key in file_services_to_exclude_current:
            
            service_id = self._GetServiceId( service_key )
            
            query_hash_ids.difference_update( [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM current_files WHERE service_id = ?;', ( service_id, ) ) ] )
            
        
        for service_key in file_services_to_exclude_pending:
            
            service_id = self._GetServiceId( service_key )
            
            query_hash_ids.difference_update( [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM file_transfers WHERE service_id = ?;', ( service_id, ) ) ] )
            
        
        for ( operator, value, service_key ) in system_predicates.GetRatingsPredicates():
            
            service_id = self._GetServiceId( service_key )
            
            if value == 'rated': query_hash_ids.intersection_update( [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM local_ratings WHERE service_id = ?;', ( service_id, ) ) ] )
            elif value == 'not rated': query_hash_ids.difference_update( [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM local_ratings WHERE service_id = ?;', ( service_id, ) ) ] )
            else:
                
                if operator == u'\u2248': predicate = str( value * 0.95 ) + ' < rating AND rating < ' + str( value * 1.05 )
                else: predicate = 'rating ' + operator + ' ' + str( value )
                
                query_hash_ids.intersection_update( [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM local_ratings WHERE service_id = ? AND ' + predicate + ';', ( service_id, ) ) ] )
                
            
        
        #
        
        must_be_local = system_predicates.MustBeLocal() or system_predicates.MustBeArchive()
        must_not_be_local = system_predicates.MustNotBeLocal()
        must_be_inbox = system_predicates.MustBeInbox()
        must_be_archive = system_predicates.MustBeArchive()
        
        if file_service_type == HC.LOCAL_FILE:
            
            if must_not_be_local:
                
                query_hash_ids = set()
                
            
        elif must_be_local or must_not_be_local:
            
            local_hash_ids = [ id for ( id, ) in self._c.execute( 'SELECT hash_id FROM current_files WHERE service_id = ?;', ( self._local_file_service_id, ) ) ]
            
            if must_be_local:
                
                query_hash_ids.intersection_update( local_hash_ids )
                
            elif must_not_be_local:
                
                query_hash_ids.difference_update( local_hash_ids )
                
            
        
        if must_be_inbox:
            
            query_hash_ids.intersection_update( self._inbox_hash_ids )
            
        elif must_be_archive:
            
            query_hash_ids.difference_update( self._inbox_hash_ids )
            
        
        #
        
        num_tags_zero = False
        num_tags_nonzero = False
        max_num_tags_exists = False
        
        tag_predicates = []
        
        if 'min_num_tags' in simple_preds:
            
            min_num_tags = simple_preds[ 'min_num_tags' ]
            
            if min_num_tags == 0:
                
                num_tags_nonzero = True
                
            else:
                
                tag_predicates.append( lambda x: x > min_num_tags )
                
            
        
        if 'num_tags' in simple_preds:
            
            num_tags = simple_preds[ 'num_tags' ]
            
            if num_tags == 0:
                
                num_tags_zero = True
                
            else:
                
                tag_predicates.append( lambda x: x == num_tags )
                
            
        
        if 'max_num_tags' in simple_preds:
            
            max_num_tags = simple_preds[ 'max_num_tags' ]
            
            if max_num_tags == 1:
                
                num_tags_zero = True
                
            else:
                
                tag_predicates.append( lambda x: x < max_num_tags )
                
            
        
        tag_predicates_care_about_zero_counts = len( tag_predicates ) > 0 and False not in ( pred( 0 ) for pred in tag_predicates )
        
        if num_tags_zero or num_tags_nonzero or tag_predicates_care_about_zero_counts:
            
            nonzero_tag_query_hash_ids = self._GetHashIdsThatHaveTags( tag_service_key, include_current_tags, include_pending_tags )
            
            if num_tags_zero:
                
                query_hash_ids.difference_update( nonzero_tag_query_hash_ids )
                
            elif num_tags_nonzero:
                
                query_hash_ids.intersection_update( nonzero_tag_query_hash_ids )
                
            
        
        if len( tag_predicates ) > 0:
            
            hash_id_tag_counts = self._GetHashIdsTagCounts( tag_service_key, include_current_tags, include_pending_tags )
            
            good_tag_count_hash_ids = { id for ( id, count ) in hash_id_tag_counts if False not in ( pred( count ) for pred in tag_predicates ) }
            
            if tag_predicates_care_about_zero_counts:
                
                zero_hash_ids = query_hash_ids.difference( nonzero_tag_query_hash_ids )
                
                good_tag_count_hash_ids.update( zero_hash_ids )
                
            
            query_hash_ids.intersection_update( good_tag_count_hash_ids )
            
        
        #
        
        limit = system_predicates.GetLimit()
        
        if limit is not None and limit <= len( query_hash_ids ):
            
            query_hash_ids = random.sample( query_hash_ids, limit )
            
        else:
            
            query_hash_ids = list( query_hash_ids )
            
        
        return query_hash_ids
        
    
    def _GetHashIdsFromTag( self, file_service_key, tag_service_key, tag, include_current_tags, include_pending_tags ):
        
        siblings_manager = self._controller.GetManager( 'tag_siblings' )
        
        tags = siblings_manager.GetAllSiblings( tag )
        
        file_service_id = self._GetServiceId( file_service_key )
        
        if tag_service_key == CC.COMBINED_TAG_SERVICE_KEY:
            
            search_tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
            
        else:
            
            search_tag_service_ids = [ self._GetServiceId( tag_service_key ) ]
            
        
        hash_ids = set()
        
        for tag in tags:
            
            if not self._TagExists( tag ):
                
                continue
                
            
            current_selects = []
            pending_selects = []
            
            try: ( namespace_id, tag_id ) = self._GetNamespaceIdTagId( tag )
            except HydrusExceptions.SizeException: continue
            
            if ':' in tag:
                
                for search_tag_service_id in search_tag_service_ids:
                    
                    ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( search_tag_service_id )
                    
                    if file_service_key == CC.COMBINED_FILE_SERVICE_KEY:
                        
                        current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ' WHERE namespace_id = ' + str( namespace_id ) + ' AND tag_id = ' + str( tag_id ) + ';' )
                        pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ' WHERE namespace_id = ' + str( namespace_id ) + ' AND tag_id = ' + str( tag_id ) + ';' )
                        
                    else:
                        
                        current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND namespace_id = ' + str( namespace_id ) + ' AND tag_id = ' + str( tag_id ) + ';' )
                        pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND namespace_id = ' + str( namespace_id ) + ' AND tag_id = ' + str( tag_id ) + ';' )
                        
                    
                
            else:
                
                for search_tag_service_id in search_tag_service_ids:
                    
                    ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( search_tag_service_id )
                    
                    if file_service_key == CC.COMBINED_FILE_SERVICE_KEY:
                        
                        current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ' WHERE tag_id = ' + str( tag_id ) + ';' )
                        pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ' WHERE tag_id = ' + str( tag_id ) + ';' )
                        
                    else:
                        
                        current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND tag_id = ' + str( tag_id ) + ';' )
                        pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND tag_id = ' + str( tag_id ) + ';' )
                        
                    
                
            
            if include_current_tags:
                
                for current_select in current_selects:
                    
                    hash_ids.update( ( id for ( id, ) in self._c.execute( current_select ) ) )
                    
                
            
            if include_pending_tags:
                
                for pending_select in pending_selects:
                    
                    hash_ids.update( ( id for ( id, ) in self._c.execute( pending_select ) ) )
                    
                
            
        
        return hash_ids
        
    
    def _GetHashIdsFromWildcard( self, file_service_key, tag_service_key, wildcard, include_current_tags, include_pending_tags ):
        
        def GetNamespaceIdsFromWildcard( w ):
            
            if '*' in w:
                
                w = w.replace( '*', '%' )
                
                return { namespace_id for ( namespace_id, ) in self._c.execute( 'SELECT namespace_id FROM namespaces WHERE namespace LIKE ?;', ( w, ) ) }
                
            else:
                
                namespace_id = self._GetNamespaceId( w )
                
                return [ namespace_id ]
                
            
        
        def GetTagIdsFromWildcard( w ):
            
            if '*' in w:
                
                w = w.replace( '*', '%' )
                
                return { tag_id for ( tag_id, ) in self._c.execute( 'SELECT tag_id FROM tags WHERE tag LIKE ? or tag LIKE ?;', ( w, '% ' + w ) ) }
                
            else:
                
                ( namespace_id, tag_id ) = self._GetNamespaceIdTagId( w )
                
                return [ tag_id ]
                
            
        
        file_service_id = self._GetServiceId( file_service_key )
        
        if tag_service_key == CC.COMBINED_TAG_SERVICE_KEY:
            
            search_tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
            
        else:
            
            search_tag_service_ids = [ self._GetServiceId( tag_service_key ) ]
            
        
        current_selects = []
        pending_selects = []
        
        if ':' in wildcard:
            
            ( namespace_wildcard, tag_wildcard ) = wildcard.split( ':', 1 )
            
            possible_namespace_ids = GetNamespaceIdsFromWildcard( namespace_wildcard )
            possible_tag_ids = GetTagIdsFromWildcard( tag_wildcard )
            
            for search_tag_service_id in search_tag_service_ids:
                
                ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( search_tag_service_id )
                
                if file_service_key == CC.COMBINED_FILE_SERVICE_KEY:
                    
                    current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ' WHERE namespace_id IN ' + HydrusData.SplayListForDB( possible_namespace_ids ) + ' AND tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids ) + ';' )
                    pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ' WHERE namespace_id IN ' + HydrusData.SplayListForDB( possible_namespace_ids ) + ' AND tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids ) + ';' )
                    
                else:
                    
                    current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND namespace_id IN ' + HydrusData.SplayListForDB( possible_namespace_ids ) + ' AND tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids ) + ';' )
                    pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND namespace_id IN ' + HydrusData.SplayListForDB( possible_namespace_ids ) + ' AND tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids ) + ';' )
                    
                
            
        else:
            
            possible_tag_ids = GetTagIdsFromWildcard( wildcard )
            
            for search_tag_service_id in search_tag_service_ids:
                
                ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( search_tag_service_id )
                
                if file_service_key == CC.COMBINED_FILE_SERVICE_KEY:
                    
                    current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ' WHERE tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids ) + ';' )
                    pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ' WHERE tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids ) + ';' )
                    
                else:
                    
                    current_selects.append( 'SELECT hash_id FROM ' + current_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids ) + ';' )
                    pending_selects.append( 'SELECT hash_id FROM ' + pending_mappings_table_name + ', current_files USING ( hash_id ) WHERE current_files.service_id = ' + str( file_service_id ) + ' AND tag_id IN ' + HydrusData.SplayListForDB( possible_tag_ids ) + ';' )
                    
                
            
        
        hash_ids = set()
        
        if include_current_tags:
            
            for current_select in current_selects:
                
                hash_ids.update( ( id for ( id, ) in self._c.execute( current_select ) ) )
                
            
        
        if include_pending_tags:
            
            for pending_select in pending_selects:
                
                hash_ids.update( ( id for ( id, ) in self._c.execute( pending_select ) ) )
                
            
        
        return hash_ids
        
    
    def _GetHashIdsTagCounts( self, tag_service_key, include_current, include_pending ):
        
        if tag_service_key == CC.COMBINED_TAG_SERVICE_KEY:
            
            search_tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
            
        else:
            
            search_tag_service_ids = [ self._GetServiceId( tag_service_key ) ]
            
        
        tags_counter = collections.Counter()
        
        for search_tag_service_id in search_tag_service_ids:
            
            ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( search_tag_service_id )
            
            if include_current:
                
                for ( id, count ) in self._c.execute( 'SELECT hash_id, COUNT( DISTINCT tag_id ) FROM ' + current_mappings_table_name + ' GROUP BY hash_id;' ):
                    
                    tags_counter[ id ] += count
                    
                
            
            if include_pending:
                
                for ( id, count ) in self._c.execute( 'SELECT hash_id, COUNT( DISTINCT tag_id ) FROM ' + pending_mappings_table_name + ' GROUP BY hash_id;' ):
                    
                    tags_counter[ id ] += count
                    
                
            
        
        return tags_counter.items()
        
    
    def _GetHashIdsThatHaveTags( self, tag_service_key, include_current, include_pending ):
        
        if tag_service_key == CC.COMBINED_TAG_SERVICE_KEY:
            
            search_tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
            
        else:
            
            search_tag_service_ids = [ self._GetServiceId( tag_service_key ) ]
            
        
        nonzero_tag_hash_ids = set()
        
        for search_tag_service_id in search_tag_service_ids:
            
            ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( search_tag_service_id )
            
            if include_current and include_pending:
                
                nonzero_tag_hash_ids.update( ( id for ( id, ) in self._c.execute( 'SELECT hash_id as h FROM hashes WHERE EXISTS ( SELECT 1 FROM ' + current_mappings_table_name + ' WHERE hash_id = h ) OR EXISTS ( SELECT 1 FROM ' + pending_mappings_table_name + ' WHERE hash_id = h );' ) ) )
                
            elif include_current:
                
                nonzero_tag_hash_ids.update( ( id for ( id, ) in self._c.execute( 'SELECT hash_id as h FROM hashes WHERE EXISTS ( SELECT 1 FROM ' + current_mappings_table_name + ' WHERE hash_id = h );' ) ) )
                
            elif include_pending:
                
                nonzero_tag_hash_ids.update( ( id for ( id, ) in self._c.execute( 'SELECT hash_id as h FROM hashes WHERE EXISTS ( SELECT 1 FROM ' + pending_mappings_table_name + ' WHERE hash_id = h );' ) ) )
                
            
        
        return nonzero_tag_hash_ids
        
    
    def _GetHashIdsToHashes( self, hash_ids ):
        
        # this is actually a bit faster than saying "hash_id IN ( bigass_list )"
        
        results = {}
        
        for hash_id in hash_ids:
            
            ( hash, ) = self._c.execute( 'SELECT hash FROM hashes WHERE hash_id = ?;', ( hash_id, ) ).fetchone()
            
            results[ hash_id ] = hash
            
        
        return results
        
    
    def _GetHashIdStatus( self, hash_id ):
    
        result = self._c.execute( 'SELECT 1 FROM deleted_files WHERE service_id = ? AND hash_id = ?;', ( self._local_file_service_id, hash_id ) ).fetchone()
        
        if result is not None:
            
            return ( CC.STATUS_DELETED, None )
            
        
        result = self._c.execute( 'SELECT 1 FROM current_files WHERE service_id = ? AND hash_id = ?;', ( self._local_file_service_id, hash_id ) ).fetchone()
        
        if result is not None:
            
            hash = self._GetHash( hash_id )
            
            return ( CC.STATUS_REDUNDANT, hash )
            
        
        return ( CC.STATUS_NEW, None )
        
    
    def _GetHydrusSessions( self ):
        
        now = HydrusData.GetNow()
        
        self._c.execute( 'DELETE FROM hydrus_sessions WHERE ? > expiry;', ( now, ) )
        
        sessions = []
        
        results = self._c.execute( 'SELECT service_id, session_key, expiry FROM hydrus_sessions;' ).fetchall()
        
        for ( service_id, session_key, expires ) in results:
            
            service = self._GetService( service_id )
            
            service_key = service.GetServiceKey()
            
            sessions.append( ( service_key, session_key, expires ) )
            
        
        return sessions
        
    
    def _GetJSONDump( self, dump_type ):
        
        ( version, dump ) = self._c.execute( 'SELECT version, dump FROM json_dumps WHERE dump_type = ?;', ( dump_type, ) ).fetchone()
        
        serialisable_info = json.loads( dump )
        
        return HydrusSerialisable.CreateFromSerialisableTuple( ( dump_type, version, serialisable_info ) )
        
    
    
    def _GetJSONDumpNamed( self, dump_type, dump_name = None ):
        
        if dump_name is None:
            
            results = self._c.execute( 'SELECT dump_name, version, dump FROM json_dumps_named WHERE dump_type = ?;', ( dump_type, ) ).fetchall()
            
            objs = []
            
            for ( dump_name, version, dump ) in results:
                
                serialisable_info = json.loads( dump )
                
                objs.append( HydrusSerialisable.CreateFromSerialisableTuple( ( dump_type, dump_name, version, serialisable_info ) ) )
                
            
            return objs
            
        else:
            
            ( version, dump ) = self._c.execute( 'SELECT version, dump FROM json_dumps_named WHERE dump_type = ? AND dump_name = ?;', ( dump_type, dump_name ) ).fetchone()
            
            serialisable_info = json.loads( dump )
            
            return HydrusSerialisable.CreateFromSerialisableTuple( ( dump_type, dump_name, version, serialisable_info ) )
            
        
    
    def _GetJSONDumpNames( self, dump_type ):
        
        names = [ name for ( name, ) in self._c.execute( 'SELECT dump_name FROM json_dumps_named WHERE dump_type = ?;', ( dump_type, ) ) ]
        
        return names
        
    
    def _GetJSONSimple( self, name ):
        
        result = self._c.execute( 'SELECT dump FROM json_dict WHERE name = ?;', ( name, ) ).fetchone()
        
        if result is None:
            
            return None
            
        
        ( json_dump, ) = result
        
        value = json.loads( json_dump )
        
        return value
        
    
    def _GetKnownURLs( self, hash ):
        
        hash_id = self._GetHashId( hash )
        
        urls = [ url for ( url, ) in self._c.execute( 'SELECT url FROM urls WHERE hash_id = ?;', ( hash_id, ) ) ]
        
        return urls
        
    
    def _GetMD5Status( self, md5 ):
        
        result = self._c.execute( 'SELECT hash_id FROM local_hashes WHERE md5 = ?;', ( sqlite3.Binary( md5 ), ) ).fetchone()
        
        if result is None:
            
            return ( CC.STATUS_NEW, None )
            
        else:
            
            ( hash_id, ) = result
            
            return self._GetHashIdStatus( hash_id )
            
        
    
    def _GetMediaResults( self, hash_ids ):
        
        splayed_hash_ids = HydrusData.SplayListForDB( hash_ids )
        
        # get first detailed results
        
        hash_ids_to_info = { hash_id : ( size, mime, width, height, duration, num_frames, num_words ) for ( hash_id, size, mime, width, height, duration, num_frames, num_words ) in self._c.execute( 'SELECT * FROM files_info WHERE hash_id IN ' + splayed_hash_ids + ';' ) }
        
        hash_ids_to_hashes = self._GetHashIdsToHashes( hash_ids )
        
        hash_ids_to_current_file_service_ids_and_timestamps = HydrusData.BuildKeyToListDict( ( ( hash_id, ( service_id, timestamp ) ) for ( hash_id, service_id, timestamp ) in self._c.execute( 'SELECT hash_id, service_id, timestamp FROM current_files WHERE hash_id IN ' + splayed_hash_ids + ';' ) ) )
        
        hash_ids_to_deleted_file_service_ids = HydrusData.BuildKeyToListDict( self._c.execute( 'SELECT hash_id, service_id FROM deleted_files WHERE hash_id IN ' + splayed_hash_ids + ';' ) )
        
        hash_ids_to_pending_file_service_ids = HydrusData.BuildKeyToListDict( self._c.execute( 'SELECT hash_id, service_id FROM file_transfers WHERE hash_id IN ' + splayed_hash_ids + ';' ) )
        
        hash_ids_to_petitioned_file_service_ids = HydrusData.BuildKeyToListDict( self._c.execute( 'SELECT hash_id, service_id FROM file_petitions WHERE hash_id IN ' + splayed_hash_ids + ';' ) )
        
        hash_ids_to_local_ratings = HydrusData.BuildKeyToListDict( [ ( hash_id, ( service_id, rating ) ) for ( service_id, hash_id, rating ) in self._c.execute( 'SELECT service_id, hash_id, rating FROM local_ratings WHERE hash_id IN ' + splayed_hash_ids + ';' ) ] )
        
        # build it
        
        service_ids_to_service_keys = { service_id : service_key for ( service_id, service_key ) in self._c.execute( 'SELECT service_id, service_key FROM services;' ) }
        
        tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
        
        media_results = []
        
        tag_censorship_manager = self._controller.GetManager( 'tag_censorship' )
        
        for hash_id in hash_ids:
            
            hash = hash_ids_to_hashes[ hash_id ]
            
            #
            
            inbox = hash_id in self._inbox_hash_ids
            
            #
            
            raw_tag_ids = []
            
            for tag_service_id in tag_service_ids:
                
                ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( tag_service_id )
                
                raw_tag_ids.extend( ( ( tag_service_id, ( HC.CURRENT, HydrusTags.CombineTag( namespace, tag ) ) ) for ( namespace, tag ) in self._c.execute( 'SELECT namespace, tag FROM namespaces, ( tags, ' + current_mappings_table_name + ' USING ( tag_id ) ) USING ( namespace_id ) WHERE hash_id = ?;', ( hash_id, ) ) ) )
                
                raw_tag_ids.extend( ( ( tag_service_id, ( HC.DELETED, HydrusTags.CombineTag( namespace, tag ) ) ) for ( namespace, tag ) in self._c.execute( 'SELECT namespace, tag FROM namespaces, ( tags, ' + deleted_mappings_table_name + ' USING ( tag_id ) ) USING ( namespace_id ) WHERE hash_id = ?;', ( hash_id, ) ) ) )
                
                raw_tag_ids.extend( ( ( tag_service_id, ( HC.PENDING, HydrusTags.CombineTag( namespace, tag ) ) ) for ( namespace, tag ) in self._c.execute( 'SELECT namespace, tag FROM namespaces, ( tags, ' + pending_mappings_table_name + ' USING ( tag_id ) ) USING ( namespace_id ) WHERE hash_id = ?;', ( hash_id, ) ) ) )
                
                raw_tag_ids.extend( ( ( tag_service_id, ( HC.PETITIONED, HydrusTags.CombineTag( namespace, tag ) ) ) for ( namespace, tag ) in self._c.execute( 'SELECT namespace, tag FROM namespaces, ( tags, ' + petitioned_mappings_table_name + ' USING ( tag_id ) ) USING ( namespace_id ) WHERE hash_id = ?;', ( hash_id, ) ) ) )
                
            
            raw_tag_ids_dict = HydrusData.BuildKeyToListDict( raw_tag_ids )
            
            service_keys_to_statuses_to_tags = collections.defaultdict( HydrusData.default_dict_set )
            
            service_keys_to_statuses_to_tags.update( { service_ids_to_service_keys[ service_id ] : HydrusData.BuildKeyToSetDict( tags_info ) for ( service_id, tags_info ) in raw_tag_ids_dict.items() } )
            
            service_keys_to_statuses_to_tags = tag_censorship_manager.FilterServiceKeysToStatusesToTags( service_keys_to_statuses_to_tags )
            
            tags_manager = ClientMedia.TagsManager( service_keys_to_statuses_to_tags )
            
            #
            
            current_file_service_keys = { service_ids_to_service_keys[ service_id ] for ( service_id, timestamp ) in hash_ids_to_current_file_service_ids_and_timestamps[ hash_id ] }
            
            deleted_file_service_keys = { service_ids_to_service_keys[ service_id ] for service_id in hash_ids_to_deleted_file_service_ids[ hash_id ] }
            
            pending_file_service_keys = { service_ids_to_service_keys[ service_id ] for service_id in hash_ids_to_pending_file_service_ids[ hash_id ] }
            
            petitioned_file_service_keys = { service_ids_to_service_keys[ service_id ] for service_id in hash_ids_to_petitioned_file_service_ids[ hash_id ] }
            
            current_file_service_keys_to_timestamps = { service_ids_to_service_keys[ service_id ] : timestamp for ( service_id, timestamp ) in hash_ids_to_current_file_service_ids_and_timestamps[ hash_id ] }
            
            file_service_keys_cdpp = ClientMedia.LocationsManager( current_file_service_keys, deleted_file_service_keys, pending_file_service_keys, petitioned_file_service_keys, current_file_service_keys_to_timestamps )
            
            #
            
            local_ratings = { service_ids_to_service_keys[ service_id ] : rating for ( service_id, rating ) in hash_ids_to_local_ratings[ hash_id ] }
            
            local_ratings = ClientRatings.LocalRatingsManager( local_ratings )
            remote_ratings = {}
            
            #
            
            if hash_id in hash_ids_to_info:
                
                ( size, mime, width, height, duration, num_frames, num_words ) = hash_ids_to_info[ hash_id ]
                
            else:
                
                ( size, mime, width, height, duration, num_frames, num_words ) = ( None, HC.APPLICATION_UNKNOWN, None, None, None, None, None )
                
            
            media_results.append( ClientMedia.MediaResult( ( hash, inbox, size, mime, width, height, duration, num_frames, num_words, tags_manager, file_service_keys_cdpp, local_ratings, remote_ratings ) ) )
            
        
        return media_results
        
    
    def _GetMediaResultsFromHashes( self, hashes ):
        
        query_hash_ids = set( self._GetHashIds( hashes ) )
        
        return self._GetMediaResults( query_hash_ids )
        
    
    def _GetMime( self, service_id, hash_id ):
        
        result = self._c.execute( 'SELECT mime FROM files_info WHERE service_id = ? AND hash_id = ?;', ( service_id, hash_id ) ).fetchone()
        
        if result is None:
            
            raise HydrusExceptions.FileMissingException( 'Did not have mime information for that file!' )
            
        
        ( mime, ) = result
        
        return mime
        
    
    def _GetNamespaceId( self, namespace ):
        
        result = self._c.execute( 'SELECT namespace_id FROM namespaces WHERE namespace = ?;', ( namespace, ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT INTO namespaces ( namespace ) VALUES ( ? );', ( namespace, ) )
            
            namespace_id = self._c.lastrowid
            
        else:
            
            ( namespace_id, ) = result
            
        
        return namespace_id
        
    
    def _GetNamespaceIdTagId( self, tag ):
        
        tag = HydrusTags.CleanTag( tag )
        
        HydrusTags.CheckTagNotEmpty( tag )
        
        if ':' in tag:
            
            ( namespace, tag ) = tag.split( ':', 1 )
            
            namespace_id = self._GetNamespaceId( namespace )
            
        else:
            
            namespace_id = 1
            
        
        result = self._c.execute( 'SELECT tag_id FROM tags WHERE tag = ?;', ( tag, ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT INTO tags ( tag ) VALUES ( ? );', ( tag, ) )
            
            tag_id = self._c.lastrowid
            
            self._c.execute( 'REPLACE INTO tags_fts4 ( docid, tag ) VALUES ( ?, ? );', ( tag_id, tag ) )
            
        else:
            
            ( tag_id, ) = result
            
        
        result = self._c.execute( 'SELECT 1 FROM existing_tags WHERE namespace_id = ? AND tag_id = ?;', ( namespace_id, tag_id ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT INTO existing_tags ( namespace_id, tag_id ) VALUES ( ?, ? );', ( namespace_id, tag_id ) )
            
        
        return ( namespace_id, tag_id )
        
    
    def _GetNamespaceTag( self, namespace_id, tag_id ):
        
        result = self._c.execute( 'SELECT tag FROM tags WHERE tag_id = ?;', ( tag_id, ) ).fetchone()
        
        if result is None:
            
            raise HydrusExceptions.DataMissing( 'Tag error in database' )
            
        
        ( tag, ) = result
        
        if namespace_id == 1:
            
            return HydrusTags.CombineTag( '', tag )
            
        else:
            
            result = self._c.execute( 'SELECT namespace FROM namespaces WHERE namespace_id = ?;', ( namespace_id, ) ).fetchone()
            
            if result is None:
                
                raise HydrusExceptions.DataMissing( 'Namespace error in database' )
                
            
            ( namespace, ) = result
            
            return HydrusTags.CombineTag( namespace, tag )
            
        
    
    def _GetNews( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        news = self._c.execute( 'SELECT post, timestamp FROM news WHERE service_id = ?;', ( service_id, ) ).fetchall()
        
        return news
        
    
    def _GetNumsPending( self ):
        
        services = self._GetServices( ( HC.TAG_REPOSITORY, HC.FILE_REPOSITORY, HC.IPFS ) )
        
        pendings = {}
        
        for service in services:
            
            service_key = service.GetServiceKey()
            service_type = service.GetServiceType()
            
            service_id = self._GetServiceId( service_key )
            
            if service_type in ( HC.FILE_REPOSITORY, HC.IPFS ): info_types = { HC.SERVICE_INFO_NUM_PENDING_FILES, HC.SERVICE_INFO_NUM_PETITIONED_FILES }
            elif service_type == HC.TAG_REPOSITORY: info_types = { HC.SERVICE_INFO_NUM_PENDING_MAPPINGS, HC.SERVICE_INFO_NUM_PETITIONED_MAPPINGS, HC.SERVICE_INFO_NUM_PENDING_TAG_SIBLINGS, HC.SERVICE_INFO_NUM_PETITIONED_TAG_SIBLINGS, HC.SERVICE_INFO_NUM_PENDING_TAG_PARENTS, HC.SERVICE_INFO_NUM_PETITIONED_TAG_PARENTS }
            
            pendings[ service_key ] = self._GetServiceInfoSpecific( service_id, service_type, info_types )
            
        
        return pendings
        
    
    def _GetOldestTrashHashes( self, minimum_age = 0 ):
        
        timestamp_cutoff = HydrusData.GetNow() - minimum_age
        
        hash_ids = { hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM file_trash WHERE timestamp < ? ORDER BY timestamp ASC LIMIT 10;', ( timestamp_cutoff, ) ) }
        
        return self._GetHashes( hash_ids )
        
    
    def _GetOptions( self ):
        
        result = self._c.execute( 'SELECT options FROM options;' ).fetchone()
        
        if result is None:
            
            options = ClientDefaults.GetClientDefaultOptions()
            
            self._c.execute( 'INSERT INTO options ( options ) VALUES ( ? );', ( options, ) )
            
        else:
            
            ( options, ) = result
            
            default_options = ClientDefaults.GetClientDefaultOptions()
            
            for key in default_options:
                
                if key not in options: options[ key ] = default_options[ key ]
                
            
        
        return options
        
    
    def _GetPending( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        service = self._GetService( service_id )
        
        service_type = service.GetServiceType()
        
        content_data_dict = HydrusData.GetEmptyDataDict()
        all_hash_ids = set()
        
        if service_type == HC.TAG_REPOSITORY:
            
            # mappings
            
            ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
            
            pending_dict = HydrusData.BuildKeyToListDict( [ ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM ' + pending_mappings_table_name + ' ORDER BY tag_id LIMIT 100;' ) ] )
            
            for ( ( namespace_id, tag_id ), hash_ids ) in pending_dict.items():
                
                pending = ( self._GetNamespaceTag( namespace_id, tag_id ), hash_ids )
                
                content_data_dict[ HC.CONTENT_TYPE_MAPPINGS ][ HC.CONTENT_UPDATE_PEND ].append( pending )
                
                all_hash_ids.update( hash_ids )
                
            
            petitioned_dict = HydrusData.BuildKeyToListDict( [ ( ( namespace_id, tag_id, reason_id ), hash_id ) for ( namespace_id, tag_id, hash_id, reason_id ) in self._c.execute( 'SELECT namespace_id, tag_id, hash_id, reason_id FROM ' + petitioned_mappings_table_name + ' ORDER BY reason_id LIMIT 100;' ) ] )
            
            for ( ( namespace_id, tag_id, reason_id ), hash_ids ) in petitioned_dict.items():
                
                petitioned = ( self._GetNamespaceTag( namespace_id, tag_id ), hash_ids, self._GetText( reason_id ) )
                
                content_data_dict[ HC.CONTENT_TYPE_MAPPINGS ][ HC.CONTENT_UPDATE_PETITION ].append( petitioned )
                
                all_hash_ids.update( hash_ids )
                
            
            # tag siblings
            
            pending = [ ( ( self._GetNamespaceTag( old_namespace_id, old_tag_id ), self._GetNamespaceTag( new_namespace_id, new_tag_id ) ), self._GetText( reason_id ) ) for ( old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, reason_id ) in self._c.execute( 'SELECT old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, reason_id FROM tag_sibling_petitions WHERE service_id = ? AND status = ? ORDER BY reason_id LIMIT 100;', ( service_id, HC.PENDING ) ).fetchall() ]
            
            if len( pending ) > 0:
                
                content_data_dict[ HC.CONTENT_TYPE_TAG_SIBLINGS ][ HC.CONTENT_UPDATE_PEND ] = pending
                
            
            petitioned = [ ( ( self._GetNamespaceTag( old_namespace_id, old_tag_id ), self._GetNamespaceTag( new_namespace_id, new_tag_id ) ), self._GetText( reason_id ) ) for ( old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, reason_id ) in self._c.execute( 'SELECT old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, reason_id FROM tag_sibling_petitions WHERE service_id = ? AND status = ? ORDER BY reason_id LIMIT 100;', ( service_id, HC.PETITIONED ) ).fetchall() ]
            
            if len( petitioned ) > 0:
                
                content_data_dict[ HC.CONTENT_TYPE_TAG_SIBLINGS ][ HC.CONTENT_UPDATE_PETITION ] = petitioned
                
            
            # tag parents
            
            pending = [ ( ( self._GetNamespaceTag( child_namespace_id, child_tag_id ), self._GetNamespaceTag( parent_namespace_id, parent_tag_id ) ), self._GetText( reason_id ) ) for ( child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, reason_id ) in self._c.execute( 'SELECT child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, reason_id FROM tag_parent_petitions WHERE service_id = ? AND status = ? ORDER BY reason_id LIMIT 100;', ( service_id, HC.PENDING ) ).fetchall() ]
            
            if len( pending ) > 0:
                
                content_data_dict[ HC.CONTENT_TYPE_TAG_PARENTS ][ HC.CONTENT_UPDATE_PEND ] = pending
                
            
            petitioned = [ ( ( self._GetNamespaceTag( child_namespace_id, child_tag_id ), self._GetNamespaceTag( parent_namespace_id, parent_tag_id ) ), self._GetText( reason_id ) ) for ( child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, reason_id ) in self._c.execute( 'SELECT child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, reason_id FROM tag_parent_petitions WHERE service_id = ? AND status = ? ORDER BY reason_id LIMIT 100;', ( service_id, HC.PETITIONED ) ).fetchall() ]
            
            if len( petitioned ) > 0:
                
                content_data_dict[ HC.CONTENT_TYPE_TAG_PARENTS ][ HC.CONTENT_UPDATE_PETITION ] = petitioned
                
            
        elif service_type == HC.FILE_REPOSITORY:
            
            result = self._c.execute( 'SELECT hash_id FROM file_transfers WHERE service_id = ?;', ( service_id, ) ).fetchone()
            
            if result is not None:
                
                ( hash_id, ) = result
                
                ( media_result, ) = self._GetMediaResults( ( hash_id, ) )
                
                return media_result
                
            
            petitioned = [ ( hash_ids, reason ) for ( reason, hash_ids ) in HydrusData.BuildKeyToListDict( self._c.execute( 'SELECT reason, hash_id FROM reasons, file_petitions USING ( reason_id ) WHERE service_id = ? ORDER BY reason_id LIMIT 100;', ( service_id, ) ) ).items() ]
            
            if len( petitioned ) > 0:
                
                all_hash_ids = { hash_id for hash_id in itertools.chain.from_iterable( ( hash_ids for ( hash_ids, reason ) in petitioned ) ) }
                
                content_data_dict[ HC.CONTENT_TYPE_FILES ][ HC.CONTENT_UPDATE_PETITION ] = petitioned
                
            
        elif service_type == HC.IPFS:
            
            result = self._c.execute( 'SELECT hash_id FROM file_transfers WHERE service_id = ?;', ( service_id, ) ).fetchone()
            
            if result is not None:
                
                ( hash_id, ) = result
                
                ( media_result, ) = self._GetMediaResults( ( hash_id, ) )
                
                return media_result
                
            
            result = self._c.execute( 'SELECT hash_id FROM file_petitions WHERE service_id = ?;', ( service_id, ) ).fetchone()
            
            if result is not None:
                
                ( hash_id, ) = result
                
                hash = self._GetHash( hash_id )
                
                multihash = self._GetServiceFilename( service_id, hash_id )
                
                return ( hash, multihash )
                
            
        
        
        if len( content_data_dict ) > 0:
            
            hash_ids_to_hashes = self._GetHashIdsToHashes( all_hash_ids )
            
            content_update_package = HydrusData.ClientToServerContentUpdatePackage( content_data_dict, hash_ids_to_hashes )
            
            return content_update_package
            
        else:
            
            return None
            
        
    
    def _GetRemoteThumbnailHashesIShouldHave( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        hash_ids = { hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM current_files, files_info USING ( hash_id ) WHERE mime IN ' + HydrusData.SplayListForDB( HC.MIMES_WITH_THUMBNAILS ) + ' AND service_id = ?;', ( service_id, ) ) }
        
        hash_ids.difference_update( ( hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM current_files WHERE service_id = ?;', ( self._local_file_service_id, ) ) ) )
        
        hashes = set( self._GetHashes( hash_ids ) )
        
        return hashes
        
    
    def _GetService( self, service_id ):
        
        if service_id in self._service_cache: service = self._service_cache[ service_id ]
        else:
            
            ( service_key, service_type, name, info ) = self._c.execute( 'SELECT service_key, service_type, name, info FROM services WHERE service_id = ?;', ( service_id, ) ).fetchone()
            
            service = ClientData.GenerateService( service_key, service_type, name, info )
            
            self._service_cache[ service_id ] = service
            
        
        if service.GetServiceType() == HC.LOCAL_BOORU:
            
            info = service.GetInfo()
            
            current_time_struct = time.gmtime()
            
            ( current_year, current_month ) = ( current_time_struct.tm_year, current_time_struct.tm_mon )
            
            ( booru_year, booru_month ) = info[ 'current_data_month' ]
            
            if current_year != booru_year or current_month != booru_month:
                
                info[ 'used_monthly_data' ] = 0
                info[ 'used_monthly_requests' ] = 0
                
                info[ 'current_data_month' ] = ( current_year, current_month )
                
                self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( info, service_id ) )
                
            
        
        return service
        
    
    def _GetServiceFilename( self, service_id, hash_id ):
        
        result = self._c.execute( 'SELECT filename FROM service_filenames WHERE service_id = ? AND hash_id = ?;', ( service_id, hash_id ) ).fetchone()
        
        if result is None:
            
            raise HydrusExceptions.DataMissing( 'Service filename not found!' )
            
        
        ( filename, ) = result
        
        return filename
        
    
    def _GetServiceFilenames( self, service_key, hashes ):
        
        service_id = self._GetServiceId( service_key )
        hash_ids = self._GetHashIds( hashes )
        
        result = [ filename for ( filename, ) in self._c.execute( 'SELECT filename FROM service_filenames WHERE service_id = ? AND hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';', ( service_id, ) ) ]
        
        result.sort()
        
        return result
        
    
    def _GetServices( self, limited_types = HC.ALL_SERVICES ):
        
        service_ids = [ service_id for ( service_id, ) in self._c.execute( 'SELECT service_id FROM services WHERE service_type IN ' + HydrusData.SplayListForDB( limited_types ) + ';' ) ]
        
        services = [ self._GetService( service_id ) for service_id in service_ids ]
        
        return services
        
    
    def _GetServiceId( self, service_key ):
        
        result = self._c.execute( 'SELECT service_id FROM services WHERE service_key = ?;', ( sqlite3.Binary( service_key ), ) ).fetchone()
        
        if result is None:
            
            raise HydrusExceptions.DataMissing( 'Service id error in database' )
            
        
        ( service_id, ) = result
        
        return service_id
        
    
    def _GetServiceIds( self, service_types ): return [ service_id for ( service_id, ) in self._c.execute( 'SELECT service_id FROM services WHERE service_type IN ' + HydrusData.SplayListForDB( service_types ) + ';' ) ]
    
    def _GetServiceInfo( self, service_key ):
        
        service_id = self._GetServiceId( service_key )
        
        service = self._GetService( service_id )
        
        service_type = service.GetServiceType()
        
        if service_type == HC.LOCAL_FILE:
            
            info_types = { HC.SERVICE_INFO_NUM_FILES, HC.SERVICE_INFO_TOTAL_SIZE, HC.SERVICE_INFO_NUM_DELETED_FILES }
            
        elif service_type == HC.FILE_REPOSITORY:
            
            info_types = { HC.SERVICE_INFO_NUM_FILES, HC.SERVICE_INFO_TOTAL_SIZE, HC.SERVICE_INFO_NUM_DELETED_FILES, HC.SERVICE_INFO_NUM_THUMBNAILS, HC.SERVICE_INFO_NUM_THUMBNAILS_LOCAL }
            
        elif service_type == HC.IPFS:
            
            info_types = { HC.SERVICE_INFO_NUM_FILES }
            
        elif service_type == HC.LOCAL_TAG:
            
            info_types = { HC.SERVICE_INFO_NUM_FILES, HC.SERVICE_INFO_NUM_TAGS, HC.SERVICE_INFO_NUM_MAPPINGS }
            
        elif service_type == HC.TAG_REPOSITORY:
            
            info_types = { HC.SERVICE_INFO_NUM_FILES, HC.SERVICE_INFO_NUM_TAGS, HC.SERVICE_INFO_NUM_MAPPINGS, HC.SERVICE_INFO_NUM_DELETED_MAPPINGS }
            
        elif service_type in ( HC.LOCAL_RATING_LIKE, HC.LOCAL_RATING_NUMERICAL ):
            
            info_types = { HC.SERVICE_INFO_NUM_FILES }
            
        elif service_type == HC.LOCAL_BOORU:
            
            info_types = { HC.SERVICE_INFO_NUM_SHARES }
            
        else:
            
            info_types = set()
            
        
        service_info = self._GetServiceInfoSpecific( service_id, service_type, info_types )
        
        return service_info
        
    
    def _GetServiceInfoSpecific( self, service_id, service_type, info_types ):
        
        results = { info_type : info for ( info_type, info ) in self._c.execute( 'SELECT info_type, info FROM service_info WHERE service_id = ? AND info_type IN ' + HydrusData.SplayListForDB( info_types ) + ';', ( service_id, ) ) }
        
        if len( results ) != len( info_types ):
            
            info_types_hit = results.keys()
            
            info_types_missed = info_types.difference( info_types_hit )
            
            if service_type in HC.TAG_SERVICES:
                
                common_tag_info_types = { HC.SERVICE_INFO_NUM_FILES, HC.SERVICE_INFO_NUM_TAGS }
                
                if common_tag_info_types <= info_types_missed:
                    
                    ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
                    
                    ( num_files, num_tags ) = self._c.execute( 'SELECT COUNT( DISTINCT hash_id ), COUNT( DISTINCT tag_id ) FROM ' + current_mappings_table_name + ';' ).fetchone()
                    
                    results[ HC.SERVICE_INFO_NUM_FILES ] = num_files
                    results[ HC.SERVICE_INFO_NUM_TAGS ] = num_tags
                    
                    self._c.execute( 'INSERT INTO service_info ( service_id, info_type, info ) VALUES ( ?, ?, ? );', ( service_id, HC.SERVICE_INFO_NUM_FILES, num_files ) )
                    self._c.execute( 'INSERT INTO service_info ( service_id, info_type, info ) VALUES ( ?, ?, ? );', ( service_id, HC.SERVICE_INFO_NUM_TAGS, num_tags ) )
                    
                    info_types_missed.difference_update( common_tag_info_types )
                    
                
            
            for info_type in info_types_missed:
                
                save_it = True
                
                if service_type in ( HC.LOCAL_FILE, HC.FILE_REPOSITORY, HC.IPFS ):
                    
                    if info_type in ( HC.SERVICE_INFO_NUM_PENDING_FILES, HC.SERVICE_INFO_NUM_PETITIONED_FILES ): save_it = False
                    
                    if info_type == HC.SERVICE_INFO_NUM_FILES: result = self._c.execute( 'SELECT COUNT( * ) FROM current_files WHERE service_id = ?;', ( service_id, ) ).fetchone()
                    elif info_type == HC.SERVICE_INFO_TOTAL_SIZE: result = self._c.execute( 'SELECT SUM( size ) FROM current_files, files_info USING ( hash_id ) WHERE service_id = ?;', ( service_id, ) ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_DELETED_FILES: result = self._c.execute( 'SELECT COUNT( * ) FROM deleted_files WHERE service_id = ?;', ( service_id, ) ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_PENDING_FILES: result = self._c.execute( 'SELECT COUNT( * ) FROM file_transfers WHERE service_id = ?;', ( service_id, ) ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_PETITIONED_FILES: result = self._c.execute( 'SELECT COUNT( * ) FROM file_petitions where service_id = ?;', ( service_id, ) ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_THUMBNAILS: result = self._c.execute( 'SELECT COUNT( * ) FROM current_files, files_info USING ( hash_id ) WHERE service_id = ? AND mime IN ' + HydrusData.SplayListForDB( HC.MIMES_WITH_THUMBNAILS ) + ';', ( service_id, ) ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_THUMBNAILS_LOCAL:
                        
                        hash_ids = [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM current_files, files_info USING ( hash_id ) WHERE mime IN ' + HydrusData.SplayListForDB( HC.MIMES_WITH_THUMBNAILS ) + ' AND service_id = ?;', ( service_id, ) ) ]
                        
                        thumbnails_i_should_have = self._GetHashes( hash_ids )
                        
                        num_local = 0
                        
                        for hash in thumbnails_i_should_have:
                            
                            path = ClientFiles.GetExpectedThumbnailPath( hash )
                            
                            if os.path.exists( path ):
                                
                                num_local += 1
                                
                            
                        
                        result = ( num_local, )
                        
                    elif info_type == HC.SERVICE_INFO_NUM_INBOX: result = self._c.execute( 'SELECT COUNT( * ) FROM file_inbox, current_files USING ( hash_id ) WHERE service_id = ?;', ( service_id, ) ).fetchone()
                    
                elif service_type in HC.TAG_SERVICES:
                    
                    ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
                    
                    if info_type in ( HC.SERVICE_INFO_NUM_PENDING_TAG_SIBLINGS, HC.SERVICE_INFO_NUM_PETITIONED_TAG_SIBLINGS, HC.SERVICE_INFO_NUM_PENDING_TAG_PARENTS, HC.SERVICE_INFO_NUM_PETITIONED_TAG_PARENTS ): save_it = False
                    
                    if info_type == HC.SERVICE_INFO_NUM_FILES: result = self._c.execute( 'SELECT COUNT( DISTINCT hash_id ) FROM ' + current_mappings_table_name + ';' ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_TAGS: result = self._c.execute( 'SELECT COUNT( DISTINCT tag_id ) FROM ' + current_mappings_table_name + ';' ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_MAPPINGS: result = self._c.execute( 'SELECT COUNT( * ) FROM ' + current_mappings_table_name + ';' ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_DELETED_MAPPINGS: result = self._c.execute( 'SELECT COUNT( * ) FROM ' + deleted_mappings_table_name + ';' ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_PENDING_MAPPINGS: result = self._c.execute( 'SELECT COUNT( * ) FROM ' + pending_mappings_table_name + ';' ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_PETITIONED_MAPPINGS: result = self._c.execute( 'SELECT COUNT( * ) FROM ' + petitioned_mappings_table_name + ';' ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_PENDING_TAG_SIBLINGS: result = self._c.execute( 'SELECT COUNT( * ) FROM tag_sibling_petitions WHERE service_id = ? AND status = ?;', ( service_id, HC.PENDING ) ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_PETITIONED_TAG_SIBLINGS: result = self._c.execute( 'SELECT COUNT( * ) FROM tag_sibling_petitions WHERE service_id = ? AND status = ?;', ( service_id, HC.PETITIONED ) ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_PENDING_TAG_PARENTS: result = self._c.execute( 'SELECT COUNT( * ) FROM tag_parent_petitions WHERE service_id = ? AND status = ?;', ( service_id, HC.PENDING ) ).fetchone()
                    elif info_type == HC.SERVICE_INFO_NUM_PETITIONED_TAG_PARENTS: result = self._c.execute( 'SELECT COUNT( * ) FROM tag_parent_petitions WHERE service_id = ? AND status = ?;', ( service_id, HC.PETITIONED ) ).fetchone()
                    
                elif service_type in ( HC.LOCAL_RATING_LIKE, HC.LOCAL_RATING_NUMERICAL ):
                    
                    if info_type == HC.SERVICE_INFO_NUM_FILES: result = self._c.execute( 'SELECT COUNT( * ) FROM local_ratings WHERE service_id = ?;', ( service_id, ) ).fetchone()
                    
                elif service_type == HC.LOCAL_BOORU:
                    
                    if info_type == HC.SERVICE_INFO_NUM_SHARES: result = self._c.execute( 'SELECT COUNT( * ) FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_LOCAL_BOORU, ) ).fetchone()
                    
                
                if result is None: info = 0
                else: ( info, ) = result
                
                if info is None: info = 0
                
                if save_it:
                    
                    self._c.execute( 'INSERT INTO service_info ( service_id, info_type, info ) VALUES ( ?, ?, ? );', ( service_id, info_type, info ) )
                    
                
                results[ info_type ] = info
                
            
        
        return results
        
    
    def _GetSiteId( self, name ):
        
        result = self._c.execute( 'SELECT site_id FROM imageboard_sites WHERE name = ?;', ( name, ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT INTO imageboard_sites ( name ) VALUES ( ? );', ( name, ) )
            
            site_id = self._c.lastrowid
            
        else: ( site_id, ) = result
        
        return site_id
        
    
    def _GetTagArchiveInfo( self ):
        
        return { archive_name : hta.GetNamespaces() for ( archive_name, ( hta_path, hta ) ) in self._tag_archives.items() }
        
    
    def _GetTagArchiveTags( self, hashes ):
        
        result = {}
        
        for ( archive_name, ( hta_path, hta ) ) in self._tag_archives.items():
            
            hash_type = hta.GetHashType()
            
            sha256_to_archive_hashes = {}
            
            if hash_type == HydrusTagArchive.HASH_TYPE_SHA256:
                
                sha256_to_archive_hashes = { hash : hash for hash in hashes }
                
            else:
                
                if hash_type == HydrusTagArchive.HASH_TYPE_MD5: h = 'md5'
                elif hash_type == HydrusTagArchive.HASH_TYPE_SHA1: h = 'sha1'
                elif hash_type == HydrusTagArchive.HASH_TYPE_SHA512: h = 'sha512'
                
                for hash in hashes:
                    
                    hash_id = self._GetHashId( hash )
                    
                    ( archive_hash, ) = self._c.execute( 'SELECT ' + h + ' FROM local_hashes WHERE hash_id = ?;', ( hash_id, ) ).fetchone()
                    
                    sha256_to_archive_hashes[ hash ] = archive_hash
                    
                
            
            hashes_to_tags = { hash : hta.GetTags( sha256_to_archive_hashes[ hash ] ) for hash in hashes }
            
            result[ archive_name ] = hashes_to_tags
            
        
        return result
        
    
    def _GetTagCensorship( self, service_key = None ):
        
        if service_key is None:
            
            result = []
            
            for ( service_id, blacklist, tags ) in self._c.execute( 'SELECT service_id, blacklist, tags FROM tag_censorship;' ).fetchall():
                
                service = self._GetService( service_id )
                
                service_key = service.GetServiceKey()
                
                result.append( ( service_key, blacklist, tags ) )
                
            
        else:
            
            service_id = self._GetServiceId( service_key )
            
            result = self._c.execute( 'SELECT blacklist, tags FROM tag_censorship WHERE service_id = ?;', ( service_id, ) ).fetchone()
            
            if result is None: result = ( True, [] )
            
        
        return result
        
    
    def _GetTagParents( self, service_key = None ):
        
        tag_censorship_manager = self._controller.GetManager( 'tag_censorship' )
        
        if service_key is None:
            
            service_ids_to_statuses_and_pair_ids = HydrusData.BuildKeyToListDict( ( ( service_id, ( status, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id ) ) for ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, status ) in self._c.execute( 'SELECT service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, status FROM tag_parents UNION SELECT service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, status FROM tag_parent_petitions;' ) ) )
            
            service_keys_to_statuses_to_pairs = collections.defaultdict( HydrusData.default_dict_set )
            
            for ( service_id, statuses_and_pair_ids ) in service_ids_to_statuses_and_pair_ids.items():
                
                service = self._GetService( service_id )
                
                service_key = service.GetServiceKey()
                
                statuses_to_pairs = HydrusData.BuildKeyToSetDict( ( ( status, ( self._GetNamespaceTag( child_namespace_id, child_tag_id ), self._GetNamespaceTag( parent_namespace_id, parent_tag_id ) ) ) for ( status, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id ) in statuses_and_pair_ids ) )
                
                statuses_to_pairs = tag_censorship_manager.FilterStatusesToPairs( service_key, statuses_to_pairs )
                
                service_keys_to_statuses_to_pairs[ service_key ] = statuses_to_pairs
                
            
            return service_keys_to_statuses_to_pairs
            
        else:
            
            service_id = self._GetServiceId( service_key )
            
            statuses_and_pair_ids = self._c.execute( 'SELECT child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, status FROM tag_parents WHERE service_id = ? UNION SELECT child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, status FROM tag_parent_petitions WHERE service_id = ?;', ( service_id, service_id ) ).fetchall()
            
            statuses_to_pairs = HydrusData.BuildKeyToSetDict( ( ( status, ( self._GetNamespaceTag( child_namespace_id, child_tag_id ), self._GetNamespaceTag( parent_namespace_id, parent_tag_id ) ) ) for ( child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, status ) in statuses_and_pair_ids ) )
            
            statuses_to_pairs = tag_censorship_manager.FilterStatusesToPairs( service_key, statuses_to_pairs )
            
            return statuses_to_pairs
            
        
    
    def _GetTagSiblings( self, service_key = None ):
        
        tag_censorship_manager = self._controller.GetManager( 'tag_censorship' )
        
        if service_key is None:
            
            service_ids_to_statuses_and_pair_ids = HydrusData.BuildKeyToListDict( ( ( service_id, ( status, old_namespace_id, old_tag_id, new_namespace_id, new_tag_id ) ) for ( service_id, old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, status ) in self._c.execute( 'SELECT service_id, old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, status FROM tag_siblings UNION SELECT service_id, old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, status FROM tag_sibling_petitions;' ) ) )
            
            service_keys_to_statuses_to_pairs = collections.defaultdict( HydrusData.default_dict_set )
            
            for ( service_id, statuses_and_pair_ids ) in service_ids_to_statuses_and_pair_ids.items():
                
                service = self._GetService( service_id )
                
                service_key = service.GetServiceKey()
                
                statuses_to_pairs = HydrusData.BuildKeyToSetDict( ( ( status, ( self._GetNamespaceTag( old_namespace_id, old_tag_id ), self._GetNamespaceTag( new_namespace_id, new_tag_id ) ) ) for ( status, old_namespace_id, old_tag_id, new_namespace_id, new_tag_id ) in statuses_and_pair_ids ) )
                
                statuses_to_pairs = tag_censorship_manager.FilterStatusesToPairs( service_key, statuses_to_pairs )
                
                service_keys_to_statuses_to_pairs[ service_key ] = statuses_to_pairs
                
            
            return service_keys_to_statuses_to_pairs
            
        else:
            
            service_id = self._GetServiceId( service_key )
            
            statuses_and_pair_ids = self._c.execute( 'SELECT old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, status FROM tag_siblings WHERE service_id = ? UNION SELECT old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, status FROM tag_sibling_petitions WHERE service_id = ?;', ( service_id, service_id ) ).fetchall()
            
            statuses_to_pairs = HydrusData.BuildKeyToSetDict( ( ( status, ( self._GetNamespaceTag( old_namespace_id, old_tag_id ), self._GetNamespaceTag( new_namespace_id, new_tag_id ) ) ) for ( old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, status ) in statuses_and_pair_ids ) )
            
            statuses_to_pairs = tag_censorship_manager.FilterStatusesToPairs( service_key, statuses_to_pairs )
            
            return statuses_to_pairs
            
        
    
    def _GetText( self, text_id ):
        
        result = self._c.execute( 'SELECT text FROM texts WHERE text_id = ?;', ( text_id, ) ).fetchone()
        
        if result is None:
            
            raise HydrusExceptions.DataMissing( 'Text lookup error in database' )
            
        
        ( text, ) = result
        
        return text
        
    
    def _GetTextId( self, text ):
        
        result = self._c.execute( 'SELECT text_id FROM texts WHERE text = ?;', ( text, ) ).fetchone()
        
        if result is None:
            
            self._c.execute( 'INSERT INTO texts ( text ) VALUES ( ? );', ( text, ) )
            
            text_id = self._c.lastrowid
            
        else:
            
            ( text_id, ) = result
            
        
        return text_id
        
    
    def _GetURLStatus( self, url ):
        
        result = self._c.execute( 'SELECT hash_id FROM urls WHERE url = ?;', ( url, ) ).fetchone()
        
        if result is None:
            
            return ( CC.STATUS_NEW, None )
            
        else:
            
            ( hash_id, ) = result
            
            return self._GetHashIdStatus( hash_id )
            
        
    
    def _GetWebSessions( self ):
        
        now = HydrusData.GetNow()
        
        self._c.execute( 'DELETE FROM web_sessions WHERE ? > expiry;', ( now, ) )
        
        sessions = []
        
        sessions = self._c.execute( 'SELECT name, cookies, expiry FROM web_sessions;' ).fetchall()
        
        return sessions
        
    
    def _GetYAMLDump( self, dump_type, dump_name = None ):
        
        if dump_name is None:
            
            result = { dump_name : data for ( dump_name, data ) in self._c.execute( 'SELECT dump_name, dump FROM yaml_dumps WHERE dump_type = ?;', ( dump_type, ) ) }
            
            if dump_type == YAML_DUMP_ID_LOCAL_BOORU:
                
                result = { dump_name.decode( 'hex' ) : data for ( dump_name, data ) in result.items() }
                
            
        else:
            
            if dump_type == YAML_DUMP_ID_SUBSCRIPTION and dump_name in self._subscriptions_cache: return self._subscriptions_cache[ dump_name ]
            
            if dump_type == YAML_DUMP_ID_LOCAL_BOORU: dump_name = dump_name.encode( 'hex' )
            
            result = self._c.execute( 'SELECT dump FROM yaml_dumps WHERE dump_type = ? AND dump_name = ?;', ( dump_type, dump_name ) ).fetchone()
            
            if result is None:
                
                if result is None:
                    
                    raise HydrusExceptions.DataMissing( dump_name + ' was not found!' )
                    
                
            else: ( result, ) = result
            
            if dump_type == YAML_DUMP_ID_SUBSCRIPTION: self._subscriptions_cache[ dump_name ] = result
            
        
        return result
        
    
    def _GetYAMLDumpNames( self, dump_type ):
        
        names = [ name for ( name, ) in self._c.execute( 'SELECT dump_name FROM yaml_dumps WHERE dump_type = ?;', ( dump_type, ) ) ]
        
        if dump_type == YAML_DUMP_ID_LOCAL_BOORU:
            
            names = [ name.decode( 'hex' ) for name in names ]
            
        
        return names
        
    
    def _HashExists( self, hash ):
        
        result = self._c.execute( 'SELECT hash_id FROM hashes WHERE hash = ?;', ( sqlite3.Binary( hash ), ) ).fetchone()
        
        if result is None:
            
            return False
            
        else:
            
            return True
            
        
    
    def _ImportFile( self, path, import_file_options = None, override_deleted = False, url = None ):
        
        if import_file_options is None:
            
            import_file_options = ClientDefaults.GetDefaultImportFileOptions()
            
        
        ( archive, exclude_deleted_files, min_size, min_resolution ) = import_file_options.ToTuple()
        
        HydrusImageHandling.ConvertToPngIfBmp( path )
        
        hash = HydrusFileHandling.GetHashFromPath( path )
        
        hash_id = self._GetHashId( hash )
        
        if url is not None:
            
            self._c.execute( 'INSERT OR IGNORE INTO urls ( url, hash_id ) VALUES ( ?, ? );', ( url, hash_id ) )
            
        
        ( status, status_hash ) = self._GetHashIdStatus( hash_id )
        
        if status == CC.STATUS_DELETED:
            
            if override_deleted or not exclude_deleted_files:
                
                status = CC.STATUS_NEW
                
            
        
        if status == CC.STATUS_REDUNDANT:
            
            if archive:
                
                self._ArchiveFiles( ( hash_id, ) )
                
                self.pub_content_updates_after_commit( { CC.LOCAL_FILE_SERVICE_KEY : [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_ARCHIVE, set( ( hash, ) ) ) ] } )
                
            
        elif status == CC.STATUS_NEW:
            
            mime = HydrusFileHandling.GetMime( path )
            
            client_files_manager = self._controller.GetClientFilesManager()
            
            dest_path = client_files_manager.GetExpectedFilePath( hash, mime )
            
            if not os.path.exists( dest_path ):
                
                shutil.copy2( path, dest_path )
                
                try: os.chmod( dest_path, stat.S_IWRITE | stat.S_IREAD )
                except: pass
                
            
            # I moved the file copy up because passing an original filename with unicode chars to getfileinfo
            # was causing problems in windows.
            
            ( size, mime, width, height, duration, num_frames, num_words ) = HydrusFileHandling.GetFileInfo( dest_path )
            
            if width is not None and height is not None:
                
                if min_resolution is not None:
                    
                    ( min_x, min_y ) = min_resolution
                    
                    if width < min_x or height < min_y:
                        
                        os.remove( dest_path )
                        
                        raise Exception( 'Resolution too small' )
                        
                    
                
            
            if min_size is not None:
                
                if size < min_size:
                    
                    os.remove( dest_path )
                    
                    raise Exception( 'File too small' )
                    
                
            
            timestamp = HydrusData.GetNow()
            
            if mime in HC.MIMES_WITH_THUMBNAILS:
                
                thumbnail = HydrusFileHandling.GenerateThumbnail( dest_path )
                
                self._AddThumbnails( [ ( hash, thumbnail ) ] )
                
            
            self._AddFilesInfo( [ ( hash_id, size, mime, width, height, duration, num_frames, num_words ) ], overwrite = True )
            
            self._AddFiles( self._local_file_service_id, [ ( hash_id, timestamp ) ] )
            
            content_update = HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_ADD, ( hash, size, mime, timestamp, width, height, duration, num_frames, num_words ) )
            
            self.pub_content_updates_after_commit( { CC.LOCAL_FILE_SERVICE_KEY : [ content_update ] } )
            
            ( md5, sha1, sha512 ) = HydrusFileHandling.GetExtraHashesFromPath( dest_path )
            
            self._c.execute( 'INSERT OR IGNORE INTO local_hashes ( hash_id, md5, sha1, sha512 ) VALUES ( ?, ?, ?, ? );', ( hash_id, sqlite3.Binary( md5 ), sqlite3.Binary( sha1 ), sqlite3.Binary( sha512 ) ) )
            
            if archive:
                
                self._ArchiveFiles( ( hash_id, ) )
                
            else:
                
                self._InboxFiles( ( hash_id, ) )
                
            
            status = CC.STATUS_SUCCESSFUL
            
        
        tag_services = self._GetServices( HC.TAG_SERVICES )
        
        for service in tag_services:
            
            service_key = service.GetServiceKey()
            info = service.GetInfo()
            
            tag_archive_sync = info[ 'tag_archive_sync' ]
            
            for ( archive_name, namespaces ) in tag_archive_sync.items():
                
                if archive_name in self._tag_archives:
                    
                    ( hta_path, hta ) = self._tag_archives[ archive_name ]
                    
                    adding = True
                    
                    try: self._SyncHashesToTagArchive( [ hash ], hta_path, service_key, adding, namespaces )
                    except: pass
                    
                
            
        
        return ( status, hash )
        
    
    def _InboxFiles( self, hash_ids ):
        
        self._c.executemany( 'INSERT OR IGNORE INTO file_inbox VALUES ( ? );', ( ( hash_id, ) for hash_id in hash_ids ) )
        
        num_added = self._GetRowCount()
        
        if num_added > 0:
            
            splayed_hash_ids = HydrusData.SplayListForDB( hash_ids )
            
            updates = self._c.execute( 'SELECT service_id, COUNT( * ) FROM current_files WHERE hash_id IN ' + splayed_hash_ids + ' GROUP BY service_id;' ).fetchall()
            
            self._c.executemany( 'UPDATE service_info SET info = info + ? WHERE service_id = ? AND info_type = ?;', [ ( count, service_id, HC.SERVICE_INFO_NUM_INBOX ) for ( service_id, count ) in updates ] )
            
            self._inbox_hash_ids.update( hash_ids )
            
        
    
    def _InitArchives( self ):
        
        self._tag_archives = {}
        
        for filename in os.listdir( HC.CLIENT_ARCHIVES_DIR ):
            
            if filename.endswith( '.db' ):
                
                try:
                    
                    hta_path = os.path.join( HC.CLIENT_ARCHIVES_DIR, filename )
                    
                    hta = HydrusTagArchive.HydrusTagArchive( hta_path )
                    
                    archive_name = filename[:-3]
                    
                    self._tag_archives[ archive_name ] = ( hta_path, hta )
                    
                except Exception as e:
                    
                    HydrusData.ShowText( 'An archive failed to load on boot.' )
                    HydrusData.ShowException( e )
                    
                
            
        
    
    def _InitCaches( self ):
        
        self._local_file_service_id = self._GetServiceId( CC.LOCAL_FILE_SERVICE_KEY )
        self._trash_service_id = self._GetServiceId( CC.TRASH_SERVICE_KEY )
        self._local_tag_service_id = self._GetServiceId( CC.LOCAL_TAG_SERVICE_KEY )
        self._combined_file_service_id = self._GetServiceId( CC.COMBINED_FILE_SERVICE_KEY )
        self._combined_tag_service_id = self._GetServiceId( CC.COMBINED_TAG_SERVICE_KEY )
        
        self._subscriptions_cache = {}
        self._service_cache = {}
        
        self._null_namespace_id = self._c.execute( 'SELECT namespace_id FROM namespaces WHERE namespace = ?;', ( '', ) )
        
        self._inbox_hash_ids = { id for ( id, ) in self._c.execute( 'SELECT hash_id FROM file_inbox;' ) }
        
        self._InitArchives()
        
    
    def _InitExternalDatabases( self ):
        
        self._db_filenames[ 'external_caches' ] = 'client.caches.db'
        self._db_filenames[ 'external_mappings' ] = 'client.mappings.db'
        self._db_filenames[ 'external_master' ] = 'client.master.db'
        
    
    def _MaintenanceDue( self ):
        
        # vacuum
        
        stale_time_delta = HC.options[ 'maintenance_vacuum_period' ]
        
        if stale_time_delta is not None:
            
            existing_names_to_timestamps = dict( self._c.execute( 'SELECT name, timestamp FROM vacuum_timestamps;' ).fetchall() )
            
            db_names = [ name for ( index, name, path ) in self._c.execute( 'PRAGMA database_list;' ) if name not in ( 'mem', 'temp' ) ]
            
            due_names = [ name for name in db_names if name not in existing_names_to_timestamps or HydrusData.TimeHasPassed( existing_names_to_timestamps[ name ] + stale_time_delta ) ]
            
            if len( due_names ) > 0:
                
                return True
                
            
        
        # analyze
        
        stale_time_delta = 14 * 86400
        
        existing_names_to_timestamps = dict( self._c.execute( 'SELECT name, timestamp FROM analyze_timestamps;' ).fetchall() )
        
        db_names = [ name for ( index, name, path ) in self._c.execute( 'PRAGMA database_list;' ) if name not in ( 'mem', 'temp' ) ]
        
        all_names = set()
        
        for db_name in db_names:
            
            all_names.update( ( name for ( name, ) in self._c.execute( 'SELECT name FROM ' + db_name + '.sqlite_master;' ) ) )
            
        
        names_to_analyze = [ name for name in all_names if name not in existing_names_to_timestamps or HydrusData.TimeHasPassed( existing_names_to_timestamps[ name ] + stale_time_delta ) ]
        
        if len( names_to_analyze ) > 0:
            
            return True
            
        
        return False
        
    
    def _ManageDBError( self, job, e ):
        
        if isinstance( e, MemoryError ):
            
            HydrusData.ShowText( 'The client is running out of memory! Restart it ASAP!' )
            
        
        ( etype, value, tb ) = sys.exc_info()
        
        db_traceback = os.linesep.join( traceback.format_exception( etype, value, tb ) )
        
        new_e = HydrusExceptions.DBException( HydrusData.ToUnicode( e ), 'Unknown Caller, probably GUI.', db_traceback )
        
        if job.IsSynchronous(): job.PutResult( new_e )
        else: HydrusData.ShowException( new_e )
        
    
    def _ProcessContentUpdatePackage( self, service_key, content_update_package, job_key ):
        
        ( previous_journal_mode, ) = self._c.execute( 'PRAGMA journal_mode;' ).fetchone()
        
        if previous_journal_mode == 'wal' and not self._fast_big_transaction_wal:
            
            self._c.execute( 'COMMIT;' )
            
            self._c.execute( 'PRAGMA journal_mode = TRUNCATE;' )
            
            self._c.execute( 'BEGIN IMMEDIATE;' )
            
        
        c_u_p_num_rows = content_update_package.GetNumRows()
        c_u_p_total_weight_processed = 0
        
        update_speed_string = u'writing\u2026'
        
        content_update_index_string = 'content row ' + HydrusData.ConvertValueRangeToPrettyString( c_u_p_total_weight_processed, c_u_p_num_rows ) + ': '
        
        quit_early = False
        
        package_precise_timestamp = HydrusData.GetNowPrecise()
        
        for ( content_updates, weight ) in content_update_package.IterateContentUpdateChunks():
            
            options = self._controller.GetOptions()
            
            if options[ 'pause_repo_sync' ]:
                
                quit_early = True
                
            
            ( i_paused, should_quit ) = job_key.WaitIfNeeded()
            
            if should_quit:
                
                quit_early = True
                
            
            if quit_early:
                
                package_took = HydrusData.GetNowPrecise() - package_precise_timestamp
                
                rows_s = c_u_p_total_weight_processed / package_took
                
                committing_string = 'wrote ' + HydrusData.ConvertIntToPrettyString( c_u_p_num_rows ) + ' rows at ' + HydrusData.ConvertIntToPrettyString( rows_s ) + ' rows/s - now committing to disk'
                
                job_key.SetVariable( 'popup_text_2', committing_string )
                
                HydrusData.Print( job_key.ToString() )
                
                if previous_journal_mode == 'wal' and not self._fast_big_transaction_wal:
                    
                    self._c.execute( 'COMMIT;' )
                    
                    self._c.execute( 'PRAGMA journal_mode = WAL;' )
                    
                    self._c.execute( 'BEGIN IMMEDIATE;' )
                    
                
                return ( False, c_u_p_total_weight_processed )
                
            
            content_update_index_string = 'content row ' + HydrusData.ConvertValueRangeToPrettyString( c_u_p_total_weight_processed, c_u_p_num_rows ) + ': '
            
            self._controller.pub( 'splash_set_status_text', content_update_index_string + update_speed_string, print_to_log = False )
            job_key.SetVariable( 'popup_text_2', content_update_index_string + update_speed_string )
            
            job_key.SetVariable( 'popup_gauge_2', ( c_u_p_total_weight_processed, c_u_p_num_rows ) )
            
            chunk_precise_timestamp = HydrusData.GetNowPrecise()
            
            self._ProcessContentUpdates( { service_key : content_updates }, do_pubsubs = False )
            
            chunk_took = HydrusData.GetNowPrecise() - chunk_precise_timestamp
            
            rows_s = weight / chunk_took
            
            update_speed_string = 'writing at ' + HydrusData.ConvertIntToPrettyString( rows_s ) + ' rows/s'
            
            c_u_p_total_weight_processed += weight
            
        
        package_took = HydrusData.GetNowPrecise() - package_precise_timestamp
        
        rows_s = c_u_p_total_weight_processed / package_took
        
        committing_string = 'wrote ' + HydrusData.ConvertIntToPrettyString( c_u_p_num_rows ) + ' rows at ' + HydrusData.ConvertIntToPrettyString( rows_s ) + ' rows/s - now committing to disk'
        
        self._controller.pub( 'splash_set_status_text', committing_string )
        job_key.SetVariable( 'popup_text_2', committing_string )
        
        job_key.SetVariable( 'popup_gauge_2', ( c_u_p_num_rows, c_u_p_num_rows ) )
        
        HydrusData.Print( job_key.ToString() )
        
        if previous_journal_mode == 'wal' and not self._fast_big_transaction_wal:
            
            self._c.execute( 'COMMIT;' )
            
            self._c.execute( 'PRAGMA journal_mode = WAL;' )
            
            self._c.execute( 'BEGIN IMMEDIATE;' )
            
        
        return ( True, c_u_p_total_weight_processed )
        
    
    def _ProcessContentUpdates( self, service_keys_to_content_updates, do_pubsubs = True ):
        
        notify_new_downloads = False
        notify_new_pending = False
        notify_new_parents = False
        notify_new_siblings = False
        
        for ( service_key, content_updates ) in service_keys_to_content_updates.items():
            
            try:
                
                service_id = self._GetServiceId( service_key )
                
            except HydrusExceptions.DataMissing:
                
                continue
                
            
            service = self._GetService( service_id )
            
            service_type = service.GetServiceType()
            
            ultimate_mappings_ids = []
            ultimate_deleted_mappings_ids = []
            
            ultimate_pending_mappings_ids = []
            ultimate_pending_rescinded_mappings_ids = []
            
            ultimate_petitioned_mappings_ids = []
            ultimate_petitioned_rescinded_mappings_ids = []
            
            for content_update in content_updates:
                
                ( data_type, action, row ) = content_update.ToTuple()
                
                if service_type in ( HC.FILE_REPOSITORY, HC.LOCAL_FILE, HC.IPFS ):
                    
                    if data_type == HC.CONTENT_TYPE_FILES:
                        
                        if action == HC.CONTENT_UPDATE_ADVANCED:
                            
                            ( sub_action, sub_row ) = row
                            
                            if sub_action == 'delete_deleted':
                                
                                self._c.execute( 'DELETE FROM deleted_files WHERE service_id = ?;', ( service_id, ) )
                                
                            
                            self._c.execute( 'DELETE FROM service_info WHERE service_id = ?;', ( service_id, ) )
                            
                        elif action == HC.CONTENT_UPDATE_ADD:
                            
                            if service_type in ( HC.FILE_REPOSITORY, HC.LOCAL_FILE ):
                                
                                ( hash, size, mime, timestamp, width, height, duration, num_frames, num_words ) = row
                                
                                hash_id = self._GetHashId( hash )
                                
                                self._AddFilesInfo( [ ( hash_id, size, mime, width, height, duration, num_frames, num_words ) ] )
                                
                            elif service_type == HC.IPFS:
                                
                                ( hash, multihash ) = row
                                
                                hash_id = self._GetHashId( hash )
                                
                                self._SetServiceFilename( service_id, hash_id, multihash )
                                
                                timestamp = HydrusData.GetNow()
                                
                            
                            self._AddFiles( service_id, [ ( hash_id, timestamp ) ] )
                            
                        elif action == HC.CONTENT_UPDATE_PEND:
                            
                            hashes = row
                            
                            hash_ids = self._GetHashIds( hashes )
                            
                            self._c.executemany( 'INSERT OR IGNORE INTO file_transfers ( service_id, hash_id ) VALUES ( ?, ? );', [ ( service_id, hash_id ) for hash_id in hash_ids ] )
                            
                            if service_key == CC.LOCAL_FILE_SERVICE_KEY: notify_new_downloads = True
                            else: notify_new_pending = True
                            
                        elif action == HC.CONTENT_UPDATE_PETITION:
                            
                            ( hashes, reason ) = row
                            
                            hash_ids = self._GetHashIds( hashes )
                            
                            reason_id = self._GetTextId( reason )
                            
                            self._c.execute( 'DELETE FROM file_petitions WHERE service_id = ? AND hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';', ( service_id, ) )
                            
                            self._c.executemany( 'INSERT OR IGNORE INTO file_petitions ( service_id, hash_id, reason_id ) VALUES ( ?, ?, ? );', [ ( service_id, hash_id, reason_id ) for hash_id in hash_ids ] )
                            
                            notify_new_pending = True
                            
                        elif action == HC.CONTENT_UPDATE_RESCIND_PEND:
                            
                            hashes = row
                            
                            hash_ids = self._GetHashIds( hashes )
                            
                            self._c.execute( 'DELETE FROM file_transfers WHERE service_id = ? AND hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';', ( service_id, ) )
                            
                            notify_new_pending = True
                            
                        elif action == HC.CONTENT_UPDATE_RESCIND_PETITION:
                            
                            hashes = row
                            
                            hash_ids = self._GetHashIds( hashes )
                            
                            self._c.execute( 'DELETE FROM file_petitions WHERE service_id = ? AND hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';', ( service_id, ) )
                            
                            notify_new_pending = True
                            
                        else:
                            
                            hashes = row
                            
                            hash_ids = self._GetHashIds( hashes )
                            
                            if action == HC.CONTENT_UPDATE_ARCHIVE: self._ArchiveFiles( hash_ids )
                            elif action == HC.CONTENT_UPDATE_INBOX: self._InboxFiles( hash_ids )
                            elif action == HC.CONTENT_UPDATE_DELETE: self._DeleteFiles( service_id, hash_ids )
                            elif action == HC.CONTENT_UPDATE_UNDELETE: self._UndeleteFiles( hash_ids )
                            
                        
                    elif data_type == HC.CONTENT_TYPE_DIRECTORIES:
                        
                        if action == HC.CONTENT_UPDATE_ADD:
                            
                            ( hashes, dirname ) = row
                            
                            hash_ids = self._GetHashIds( hashes )
                            
                            self._SetServiceDirectory( service_id, hash_ids, dirname )
                            
                        elif action == HC.CONTENT_UPDATE_DELETE:
                            
                            dirname = row
                            
                            self._DeleteServiceDirectory( service_id, dirname )
                            
                        
                    
                elif service_type in HC.TAG_SERVICES:
                    
                    if data_type == HC.CONTENT_TYPE_MAPPINGS:
                        
                        if action == HC.CONTENT_UPDATE_ADVANCED:
                            
                            ( sub_action, sub_row ) = row
                            
                            if sub_action in ( 'copy', 'delete', 'delete_deleted' ):
                                
                                self._c.execute( 'CREATE TEMPORARY TABLE temp_operation ( job_id INTEGER PRIMARY KEY AUTOINCREMENT, namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER );' )
                                
                                ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
                                
                                if sub_action == 'copy':
                                    
                                    ( tag, hashes, service_key_target ) = sub_row
                                    
                                    source_table_name = current_mappings_table_name
                                    
                                elif sub_action == 'delete':
                                    
                                    ( tag, hashes ) = sub_row
                                    
                                    source_table_name = current_mappings_table_name
                                    
                                elif sub_action == 'delete_deleted':
                                    
                                    ( tag, hashes ) = sub_row
                                    
                                    source_table_name = deleted_mappings_table_name
                                    
                                
                                predicates = []
                                
                                if tag is not None:
                                    
                                    ( tag_type, tag ) = tag
                                    
                                    if tag_type == 'tag':
                                        
                                        try: ( namespace_id, tag_id ) = self._GetNamespaceIdTagId( tag )
                                        except HydrusExceptions.SizeException: continue
                                        
                                        predicates.append( 'namespace_id = ' + str( namespace_id ) )
                                        predicates.append( 'tag_id = ' + str( tag_id ) )
                                        
                                    elif tag_type == 'namespace':
                                        
                                        namespace_id = self._GetNamespaceId( tag )
                                        
                                        predicates.append( 'namespace_id = ' + str( namespace_id ) )
                                        
                                    
                                
                                if hashes is not None:
                                    
                                    hash_ids = self._GetHashIds( hashes )
                                    
                                    predicates.append( 'hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) )
                                    
                                
                                if len( predicates ) == 0:
                                    
                                    self._c.execute( 'INSERT INTO temp_operation ( namespace_id, tag_id, hash_id ) SELECT namespace_id, tag_id, hash_id FROM ' + source_table_name + ';' )
                                    
                                else:
                                    
                                    self._c.execute( 'INSERT INTO temp_operation ( namespace_id, tag_id, hash_id ) SELECT namespace_id, tag_id, hash_id FROM ' + source_table_name + ' WHERE ' + ' AND '.join( predicates ) + ';' )
                                    
                                
                                num_to_do = self._GetRowCount()
                                
                                i = 0
                                
                                block_size = 1000
                                
                                while i < num_to_do:
                                    
                                    advanced_mappings_ids = self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM temp_operation WHERE job_id BETWEEN ? AND ?;', ( i, i + block_size - 1 ) )
                                    
                                    advanced_mappings_ids = HydrusData.BuildKeyToListDict( ( ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in advanced_mappings_ids ) )
                                    
                                    advanced_mappings_ids = [ ( namespace_id, tag_id, hash_ids ) for ( ( namespace_id, tag_id ), hash_ids ) in advanced_mappings_ids.items() ]
                                    
                                    if sub_action == 'copy':
                                        
                                        service_id_target = self._GetServiceId( service_key_target )
                                        
                                        service_target = self._GetService( service_id_target )
                                        
                                        if service_target.GetServiceType() == HC.LOCAL_TAG: kwarg = 'mappings_ids'
                                        else: kwarg = 'pending_mappings_ids'
                                        
                                        kwargs = { kwarg : advanced_mappings_ids }
                                        
                                        self._UpdateMappings( service_id_target, **kwargs )
                                        
                                    elif sub_action == 'delete':
                                        
                                        self._UpdateMappings( service_id, deleted_mappings_ids = advanced_mappings_ids )
                                        
                                    elif sub_action == 'delete_deleted':
                                        
                                        for ( namespace_id, tag_id, hash_ids ) in advanced_mappings_ids:
                                            
                                            self._c.execute( 'DELETE FROM ' + deleted_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';', ( namespace_id, tag_id ) )
                                            
                                        
                                        self._c.execute( 'DELETE FROM service_info WHERE service_id = ?;', ( service_id, ) )
                                        
                                    
                                    i += block_size
                                    
                                
                                self._c.execute( 'DROP TABLE temp_operation;' )
                                
                                self.pub_after_commit( 'notify_new_pending' )
                                
                            
                        else:
                            
                            if action == HC.CONTENT_UPDATE_PETITION: ( tag, hashes, reason ) = row
                            else: ( tag, hashes ) = row
                            
                            try: ( namespace_id, tag_id ) = self._GetNamespaceIdTagId( tag )
                            except HydrusExceptions.SizeException: continue
                            
                            hash_ids = self._GetHashIds( hashes )
                            
                            if action == HC.CONTENT_UPDATE_ADD: ultimate_mappings_ids.append( ( namespace_id, tag_id, hash_ids ) )
                            elif action == HC.CONTENT_UPDATE_DELETE: ultimate_deleted_mappings_ids.append( ( namespace_id, tag_id, hash_ids ) )
                            elif action == HC.CONTENT_UPDATE_PEND: ultimate_pending_mappings_ids.append( ( namespace_id, tag_id, hash_ids ) )
                            elif action == HC.CONTENT_UPDATE_RESCIND_PEND: ultimate_pending_rescinded_mappings_ids.append( ( namespace_id, tag_id, hash_ids ) )
                            elif action == HC.CONTENT_UPDATE_PETITION:
                                
                                reason_id = self._GetTextId( reason )
                                
                                ultimate_petitioned_mappings_ids.append( ( namespace_id, tag_id, hash_ids, reason_id ) )
                                
                            elif action == HC.CONTENT_UPDATE_RESCIND_PETITION: ultimate_petitioned_rescinded_mappings_ids.append( ( namespace_id, tag_id, hash_ids ) )
                            
                        
                    elif data_type == HC.CONTENT_TYPE_TAG_SIBLINGS:
                        
                        if action in ( HC.CONTENT_UPDATE_ADD, HC.CONTENT_UPDATE_DELETE ):
                            
                            if action == HC.CONTENT_UPDATE_ADD: ( deletee_status, new_status ) = ( HC.PENDING, HC.CURRENT )
                            elif action == HC.CONTENT_UPDATE_DELETE: ( deletee_status, new_status ) = ( HC.PETITIONED, HC.DELETED )
                            
                            ( old_tag, new_tag ) = row
                            
                            try:
                                
                                ( old_namespace_id, old_tag_id ) = self._GetNamespaceIdTagId( old_tag )
                                
                                ( new_namespace_id, new_tag_id ) = self._GetNamespaceIdTagId( new_tag )
                                
                            except HydrusExceptions.SizeException:
                                
                                continue
                                
                            
                            self._c.execute( 'DELETE FROM tag_siblings WHERE service_id = ? AND old_namespace_id = ? AND old_tag_id = ?;', ( service_id, old_namespace_id, old_tag_id ) )
                            self._c.execute( 'DELETE FROM tag_sibling_petitions WHERE service_id = ? AND old_namespace_id = ? AND old_tag_id = ? AND status = ?;', ( service_id, old_namespace_id, old_tag_id, deletee_status ) )
                            
                            self._c.execute( 'INSERT OR IGNORE INTO tag_siblings ( service_id, old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, status ) VALUES ( ?, ?, ?, ?, ?, ? );', ( service_id, old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, new_status ) )
                            
                        elif action in ( HC.CONTENT_UPDATE_PEND, HC.CONTENT_UPDATE_PETITION ):
                            
                            if action == HC.CONTENT_UPDATE_PEND: new_status = HC.PENDING
                            elif action == HC.CONTENT_UPDATE_PETITION: new_status = HC.PETITIONED
                            
                            ( ( old_tag, new_tag ), reason ) = row
                            
                            try:
                                
                                ( old_namespace_id, old_tag_id ) = self._GetNamespaceIdTagId( old_tag )
                                
                                ( new_namespace_id, new_tag_id ) = self._GetNamespaceIdTagId( new_tag )
                                
                            except HydrusExceptions.SizeException:
                                
                                continue
                                
                            
                            reason_id = self._GetTextId( reason )
                            
                            self._c.execute( 'DELETE FROM tag_sibling_petitions WHERE service_id = ? AND old_namespace_id = ? AND old_tag_id = ?;', ( service_id, old_namespace_id, old_tag_id ) )
                            
                            self._c.execute( 'INSERT OR IGNORE INTO tag_sibling_petitions ( service_id, old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, reason_id, status ) VALUES ( ?, ?, ?, ?, ?, ?, ? );', ( service_id, old_namespace_id, old_tag_id, new_namespace_id, new_tag_id, reason_id, new_status ) )
                            
                            notify_new_pending = True
                            
                        elif action in ( HC.CONTENT_UPDATE_RESCIND_PEND, HC.CONTENT_UPDATE_RESCIND_PETITION ):
                            
                            if action == HC.CONTENT_UPDATE_RESCIND_PEND:
                                
                                deletee_status = HC.PENDING
                                
                            elif action == HC.CONTENT_UPDATE_RESCIND_PETITION:
                                
                                deletee_status = HC.PETITIONED
                                
                            
                            ( old_tag, new_tag ) = row
                            
                            try:
                                
                                ( old_namespace_id, old_tag_id ) = self._GetNamespaceIdTagId( old_tag )
                                
                            except HydrusExceptions.SizeException:
                                
                                continue
                                
                            
                            self._c.execute( 'DELETE FROM tag_sibling_petitions WHERE service_id = ? AND old_namespace_id = ? AND old_tag_id = ? AND status = ?;', ( service_id, old_namespace_id, old_tag_id, deletee_status ) )
                            
                            notify_new_pending = True
                            
                        
                        notify_new_siblings = True
                        
                    elif data_type == HC.CONTENT_TYPE_TAG_PARENTS:
                        
                        if action in ( HC.CONTENT_UPDATE_ADD, HC.CONTENT_UPDATE_DELETE ):
                            
                            if action == HC.CONTENT_UPDATE_ADD: ( deletee_status, new_status ) = ( HC.PENDING, HC.CURRENT )
                            elif action == HC.CONTENT_UPDATE_DELETE: ( deletee_status, new_status ) = ( HC.PETITIONED, HC.DELETED )
                            
                            ( child_tag, parent_tag ) = row
                            
                            try:
                                
                                ( child_namespace_id, child_tag_id ) = self._GetNamespaceIdTagId( child_tag )
                                
                                ( parent_namespace_id, parent_tag_id ) = self._GetNamespaceIdTagId( parent_tag )
                                
                            except HydrusExceptions.SizeException: continue
                            
                            self._c.execute( 'DELETE FROM tag_parents WHERE service_id = ? AND child_namespace_id = ? AND child_tag_id = ? AND parent_namespace_id = ? AND parent_tag_id = ?;', ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id ) )
                            self._c.execute( 'DELETE FROM tag_parent_petitions WHERE service_id = ? AND child_namespace_id = ? AND child_tag_id = ? AND parent_namespace_id = ? AND parent_tag_id = ? AND status = ?;', ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, deletee_status ) )
                            
                            self._c.execute( 'INSERT OR IGNORE INTO tag_parents ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, status ) VALUES ( ?, ?, ?, ?, ?, ? );', ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, new_status ) )
                            
                            if action == HC.CONTENT_UPDATE_ADD:
                                
                                ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
                                
                                existing_hash_ids = [ hash for ( hash, ) in self._c.execute( 'SELECT hash_id FROM ' + current_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ?;', ( child_namespace_id, child_tag_id ) ) ]
                                
                                existing_hashes = self._GetHashes( existing_hash_ids )
                                
                                mappings_ids = [ ( parent_namespace_id, parent_tag_id, existing_hash_ids ) ]
                                
                                self._UpdateMappings( service_id, mappings_ids = mappings_ids )
                                
                                special_content_update = HydrusData.ContentUpdate( HC.CONTENT_TYPE_MAPPINGS, HC.CONTENT_UPDATE_ADD, ( parent_tag, existing_hashes ) )
                                
                                self.pub_content_updates_after_commit( { service_key : [ special_content_update ] } )
                                
                            
                        elif action in ( HC.CONTENT_UPDATE_PEND, HC.CONTENT_UPDATE_PETITION ):
                            
                            if action == HC.CONTENT_UPDATE_PEND: new_status = HC.PENDING
                            elif action == HC.CONTENT_UPDATE_PETITION: new_status = HC.PETITIONED
                            
                            ( ( child_tag, parent_tag ), reason ) = row
                            
                            try:
                                
                                ( child_namespace_id, child_tag_id ) = self._GetNamespaceIdTagId( child_tag )
                                
                                ( parent_namespace_id, parent_tag_id ) = self._GetNamespaceIdTagId( parent_tag )
                                
                            except HydrusExceptions.SizeException: continue
                            
                            reason_id = self._GetTextId( reason )
                            
                            self._c.execute( 'DELETE FROM tag_parent_petitions WHERE service_id = ? AND child_namespace_id = ? AND child_tag_id = ? AND parent_namespace_id = ? AND parent_tag_id = ?;', ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id ) )
                            
                            self._c.execute( 'INSERT OR IGNORE INTO tag_parent_petitions ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, reason_id, status ) VALUES ( ?, ?, ?, ?, ?, ?, ? );', ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, reason_id, new_status ) )
                            
                            notify_new_pending = True
                            
                        elif action in ( HC.CONTENT_UPDATE_RESCIND_PEND, HC.CONTENT_UPDATE_RESCIND_PETITION ):
                            
                            if action == HC.CONTENT_UPDATE_RESCIND_PEND: deletee_status = HC.PENDING
                            elif action == HC.CONTENT_UPDATE_RESCIND_PETITION: deletee_status = HC.PETITIONED
                            
                            ( child_tag, parent_tag ) = row
                            
                            try:
                                
                                ( child_namespace_id, child_tag_id ) = self._GetNamespaceIdTagId( child_tag )
                                
                                ( parent_namespace_id, parent_tag_id ) = self._GetNamespaceIdTagId( parent_tag )
                                
                            except HydrusExceptions.SizeException: continue
                            
                            self._c.execute( 'DELETE FROM tag_parent_petitions WHERE service_id = ? AND child_namespace_id = ? AND child_tag_id = ? AND parent_namespace_id = ? AND parent_tag_id = ? AND status = ?;', ( service_id, child_namespace_id, child_tag_id, parent_namespace_id, parent_tag_id, deletee_status ) )
                            
                            notify_new_pending = True
                            
                        
                        notify_new_parents = True
                        
                    
                elif service_type in HC.RATINGS_SERVICES:
                    
                    if action == HC.CONTENT_UPDATE_ADD:
                        
                        ( rating, hashes ) = row
                        
                        hash_ids = self._GetHashIds( hashes )
                        
                        splayed_hash_ids = HydrusData.SplayListForDB( hash_ids )
                        
                        if service_type in ( HC.LOCAL_RATING_LIKE, HC.LOCAL_RATING_NUMERICAL ):
                            
                            ratings_added = 0
                            
                            self._c.execute( 'DELETE FROM local_ratings WHERE service_id = ? AND hash_id IN ' + splayed_hash_ids + ';', ( service_id, ) )
                            
                            ratings_added -= self._GetRowCount()
                            
                            if rating is not None:
                                
                                self._c.executemany( 'INSERT INTO local_ratings ( service_id, hash_id, rating ) VALUES ( ?, ?, ? );', [ ( service_id, hash_id, rating ) for hash_id in hash_ids ] )
                                
                                ratings_added += self._GetRowCount()
                                
                            
                            self._c.execute( 'UPDATE service_info SET info = info + ? WHERE service_id = ? AND info_type = ?;', ( ratings_added, service_id, HC.SERVICE_INFO_NUM_FILES ) )
                            
                            # and then do a thing here where it looks up remote services links and then pends/rescinds pends appropriately
                            
                        
                    
                
            
            if len( ultimate_mappings_ids ) + len( ultimate_deleted_mappings_ids ) + len( ultimate_pending_mappings_ids ) + len( ultimate_pending_rescinded_mappings_ids ) + len( ultimate_petitioned_mappings_ids ) + len( ultimate_petitioned_rescinded_mappings_ids ) > 0:
                
                self._UpdateMappings( service_id, mappings_ids = ultimate_mappings_ids, deleted_mappings_ids = ultimate_deleted_mappings_ids, pending_mappings_ids = ultimate_pending_mappings_ids, pending_rescinded_mappings_ids = ultimate_pending_rescinded_mappings_ids, petitioned_mappings_ids = ultimate_petitioned_mappings_ids, petitioned_rescinded_mappings_ids = ultimate_petitioned_rescinded_mappings_ids )
                
                notify_new_pending = True
                
            
        
        if do_pubsubs:
            
            if notify_new_downloads: self.pub_after_commit( 'notify_new_downloads' )
            if notify_new_pending: self.pub_after_commit( 'notify_new_pending' )
            if notify_new_siblings:
                
                self.pub_after_commit( 'notify_new_siblings' )
                self.pub_after_commit( 'notify_new_parents' )
                
            elif notify_new_parents:
                
                self.pub_after_commit( 'notify_new_parents' )
                
            
            self.pub_content_updates_after_commit( service_keys_to_content_updates )
            
        
    
    def _ProcessServiceUpdates( self, service_keys_to_service_updates ):
        
        do_new_permissions = False
        
        hydrus_requests_made = []
        local_booru_requests_made = []
        
        for ( service_key, service_updates ) in service_keys_to_service_updates.items():
            
            try:
                
                service_id = self._GetServiceId( service_key )
                
            except HydrusExceptions.DataMissing:
                
                continue
                
            
            if service_id in self._service_cache: del self._service_cache[ service_id ]
            
            service = self._GetService( service_id )
            
            ( service_key, service_type, name, info ) = service.ToTuple()
            
            for service_update in service_updates:
                
                ( action, row ) = service_update.ToTuple()
                
                if action == HC.SERVICE_UPDATE_ACCOUNT:
                    
                    account = row
                    
                    update = { 'account' : account, 'last_error' : 0 }
                    
                    self._UpdateServiceInfo( service_id, update )
                    
                    do_new_permissions = True
                    
                elif action == HC.SERVICE_UPDATE_ERROR:
                    
                    update = { 'last_error' : HydrusData.GetNow() }
                    
                    self._UpdateServiceInfo( service_id, update )
                    
                elif action == HC.SERVICE_UPDATE_REQUEST_MADE:
                    
                    num_bytes = row
                    
                    if service_type == HC.LOCAL_BOORU: local_booru_requests_made.append( num_bytes )
                    else: hydrus_requests_made.append( ( service_id, num_bytes ) )
                    
                elif action == HC.SERVICE_UPDATE_NEWS:
                    
                    news_rows = row
                    
                    self._c.executemany( 'INSERT OR IGNORE INTO news VALUES ( ?, ?, ? );', [ ( service_id, post, timestamp ) for ( post, timestamp ) in news_rows ] )
                    
                    now = HydrusData.GetNow()
                    
                    for ( post, timestamp ) in news_rows:
                        
                        if not HydrusData.TimeHasPassed( timestamp + 86400 * 7 ):
                            
                            text = name + ' at ' + time.ctime( timestamp ) + ':' + os.linesep * 2 + post
                            
                            job_key = ClientThreading.JobKey()
                            
                            job_key.SetVariable( 'popup_text_1', text )
                            
                            self.pub_after_commit( 'message', job_key )
                            
                        
                    
                elif action == HC.SERVICE_UPDATE_NEXT_DOWNLOAD_TIMESTAMP:
                    
                    next_download_timestamp = row
                    
                    if next_download_timestamp > info[ 'next_download_timestamp' ]:
                        
                        if info[ 'first_timestamp' ] is None: update = { 'first_timestamp' : next_download_timestamp, 'next_download_timestamp' : next_download_timestamp }
                        else: update = { 'next_download_timestamp' : next_download_timestamp }
                        
                        self._UpdateServiceInfo( service_id, update )
                        
                    
                elif action == HC.SERVICE_UPDATE_NEXT_PROCESSING_TIMESTAMP:
                    
                    next_processing_timestamp = row
                    
                    if next_processing_timestamp > info[ 'next_processing_timestamp' ]:
                        
                        info_update = { 'next_processing_timestamp' : next_processing_timestamp }
                        
                        self._UpdateServiceInfo( service_id, info_update )
                        
                    
                elif action == HC.SERVICE_UPDATE_PAUSE:
                    
                    info_update = { 'paused' : True }
                    
                    self._UpdateServiceInfo( service_id, info_update )
                    
                
            
            self.pub_service_updates_after_commit( service_keys_to_service_updates )
            
        
        for ( service_id, nums_bytes ) in HydrusData.BuildKeyToListDict( hydrus_requests_made ).items():
            
            service = self._GetService( service_id )
            
            info = service.GetInfo()
            
            account = info[ 'account' ]
            
            for num_bytes in nums_bytes: account.RequestMade( num_bytes )
            
            self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( info, service_id ) )
            
        
        if len( local_booru_requests_made ) > 0:
            
            service_id = self._GetServiceId( CC.LOCAL_BOORU_SERVICE_KEY )
            
            service = self._GetService( service_id )
            
            info = service.GetInfo()
            
            info[ 'used_monthly_data' ] += sum( local_booru_requests_made )
            info[ 'used_monthly_requests' ] += len( local_booru_requests_made )
            
            self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( info, service_id ) )
            
        
        if do_new_permissions: self.pub_after_commit( 'notify_new_permissions' )
        
    
    def _Read( self, action, *args, **kwargs ):
        
        if action == 'tag_archive_info': result = self._GetTagArchiveInfo( *args, **kwargs )
        elif action == 'tag_archive_tags': result = self._GetTagArchiveTags( *args, **kwargs )
        elif action == 'autocomplete_predicates': result = self._GetAutocompletePredicates( *args, **kwargs )
        elif action == 'client_files_locations': result = self._GetClientFilesLocations( *args, **kwargs )
        elif action == 'downloads': result = self._GetDownloads( *args, **kwargs )
        elif action == 'file_hashes': result = self._GetFileHashes( *args, **kwargs )
        elif action == 'file_query_ids': result = self._GetHashIdsFromQuery( *args, **kwargs )
        elif action == 'file_system_predicates': result = self._GetFileSystemPredicates( *args, **kwargs )
        elif action == 'filter_hashes': result = self._FilterHashes( *args, **kwargs )
        elif action == 'hydrus_sessions': result = self._GetHydrusSessions( *args, **kwargs )
        elif action == 'imageboards': result = self._GetYAMLDump( YAML_DUMP_ID_IMAGEBOARD, *args, **kwargs )
        elif action == 'known_urls': result = self._GetKnownURLs( *args, **kwargs )
        elif action == 'serialisable': result = self._GetJSONDump( *args, **kwargs )
        elif action == 'serialisable_simple': result = self._GetJSONSimple( *args, **kwargs )
        elif action == 'serialisable_named': result = self._GetJSONDumpNamed( *args, **kwargs )
        elif action == 'serialisable_names': result = self._GetJSONDumpNames( *args, **kwargs )
        elif action == 'service_filenames': result = self._GetServiceFilenames( *args, **kwargs )
        elif action == 'local_booru_share_keys': result = self._GetYAMLDumpNames( YAML_DUMP_ID_LOCAL_BOORU )
        elif action == 'local_booru_share': result = self._GetYAMLDump( YAML_DUMP_ID_LOCAL_BOORU, *args, **kwargs )
        elif action == 'local_booru_shares': result = self._GetYAMLDump( YAML_DUMP_ID_LOCAL_BOORU )
        elif action == 'maintenance_due': result = self._MaintenanceDue( *args, **kwargs )
        elif action == 'md5_status': result = self._GetMD5Status( *args, **kwargs )
        elif action == 'media_results': result = self._GetMediaResultsFromHashes( *args, **kwargs )
        elif action == 'media_results_from_ids': result = self._GetMediaResults( *args, **kwargs )
        elif action == 'news': result = self._GetNews( *args, **kwargs )
        elif action == 'nums_pending': result = self._GetNumsPending( *args, **kwargs )
        elif action == 'oldest_trash_hashes': result = self._GetOldestTrashHashes( *args, **kwargs )
        elif action == 'options': result = self._GetOptions( *args, **kwargs )
        elif action == 'pending': result = self._GetPending( *args, **kwargs )
        elif action == 'remote_booru': result = self._GetYAMLDump( YAML_DUMP_ID_REMOTE_BOORU, *args, **kwargs )
        elif action == 'remote_boorus': result = self._GetYAMLDump( YAML_DUMP_ID_REMOTE_BOORU )
        elif action == 'service_info': result = self._GetServiceInfo( *args, **kwargs )
        elif action == 'services': result = self._GetServices( *args, **kwargs )
        elif action == 'tag_censorship': result = self._GetTagCensorship( *args, **kwargs )
        elif action == 'tag_parents': result = self._GetTagParents( *args, **kwargs )
        elif action == 'tag_siblings': result = self._GetTagSiblings( *args, **kwargs )
        elif action == 'remote_thumbnail_hashes_i_should_have': result = self._GetRemoteThumbnailHashesIShouldHave( *args, **kwargs )
        elif action == 'url_status': result = self._GetURLStatus( *args, **kwargs )
        elif action == 'web_sessions': result = self._GetWebSessions( *args, **kwargs )
        else: raise Exception( 'db received an unknown read command: ' + action )
        
        return result
        
    
    def _RelocateClientFiles( self, prefix, source, dest ):
        
        full_source = os.path.join( source, prefix )
        full_dest = os.path.join( dest, prefix )
        
        if os.path.exists( full_source ):
            
            HydrusPaths.CopyAndMergeTree( full_source, full_dest )
            
        elif not os.path.exists( full_dest ):
            
            os.makedirs( full_dest )
            
        
        portable_dest = HydrusPaths.ConvertAbsPathToPortablePath( dest )
        
        self._c.execute( 'UPDATE client_files_locations SET location = ? WHERE prefix = ?;', ( portable_dest, prefix ) )
        
        if os.path.exists( full_source ):
            
            try: HydrusPaths.RecyclePath( full_source )
            except: pass
            
        
    
    def _RegenerateACCache( self ):
        
        job_key = ClientThreading.JobKey()
        
        job_key.SetVariable( 'popup_title', 'regenerating autocomplete cache' )
        
        self._controller.pub( 'message', job_key )
        
        tag_service_ids = self._GetServiceIds( HC.TAG_SERVICES )
        file_service_ids = self._GetServiceIds( ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ) )
        
        for ( file_service_id, tag_service_id ) in itertools.product( file_service_ids, tag_service_ids ):
            
            job_key.SetVariable( 'popup_text_1', 'generating specific ac_cache ' + str( file_service_id ) + '_' + str( tag_service_id ) )
            
            try:
                
                self._CacheSpecificMappingsDrop( file_service_id, tag_service_id )
                
            except:
                
                pass
                
            
            self._CacheSpecificMappingsGenerate( file_service_id, tag_service_id )
            
        
        for tag_service_id in tag_service_ids:
            
            job_key.SetVariable( 'popup_text_1', 'generating combined files ac_cache ' + str( tag_service_id ) )
            
            try:
                
                self._CacheCombinedFilesMappingsDrop( tag_service_id )
                
            except:
                
                pass
                
            
            self._CacheCombinedFilesMappingsGenerate( tag_service_id )
            
        
        job_key.SetVariable( 'popup_text_1', 'done!' )
        
    
    def _ResetService( self, service_key, delete_updates = False ):
        
        self._c.execute( 'COMMIT;' )
        
        if not self._fast_big_transaction_wal:
            
            self._c.execute( 'PRAGMA journal_mode = TRUNCATE;' )
            
        
        self._c.execute( 'PRAGMA foreign_keys = ON;' )
        
        self._c.execute( 'BEGIN IMMEDIATE;' )
        
        service_id = self._GetServiceId( service_key )
        
        service = self._GetService( service_id )
        
        ( service_key, service_type, name, info ) = service.ToTuple()
        
        prefix = 'resetting ' + name
        
        job_key = ClientThreading.JobKey()
        
        job_key.SetVariable( 'popup_text_1', prefix + ': deleting service' )
        
        self._controller.pub( 'message', job_key )
        
        self._DeleteService( service_id, delete_update_dir = delete_updates )
        
        if service_type in HC.REPOSITORIES:
            
            job_key.SetVariable( 'popup_text_1', prefix + ': deleting downloaded updates' )
            
            if delete_updates:
                
                info[ 'first_timestamp' ] = None
                info[ 'next_download_timestamp' ] = 0
                
            
            info[ 'next_processing_timestamp' ] = 0
            
            self.pub_after_commit( 'notify_restart_repo_sync_daemon' )
            
        
        job_key.SetVariable( 'popup_text_1', prefix + ': recreating service' )
        
        self._AddService( service_key, service_type, name, info )
        
        self.pub_after_commit( 'notify_new_pending' )
        self.pub_after_commit( 'notify_new_services_data' )
        self.pub_after_commit( 'notify_new_services_gui' )
        
        job_key.SetVariable( 'popup_text_1', prefix + ': done!' )
        
        self._c.execute( 'COMMIT;' )
        
        self._InitDBCursor()
        
        self._c.execute( 'BEGIN IMMEDIATE;' )
        
        job_key.Finish()
        
    
    def _SaveOptions( self, options ):
        
        ( old_options, ) = self._c.execute( 'SELECT options FROM options;' ).fetchone()
        
        ( old_width, old_height ) = old_options[ 'thumbnail_dimensions' ]
        
        ( new_width, new_height ) = options[ 'thumbnail_dimensions' ]
        
        self._c.execute( 'UPDATE options SET options = ?;', ( options, ) )
        
        resize_thumbs = new_width != old_width or new_height != old_height
        
        if resize_thumbs:
            
            self.pub_after_commit( 'thumbnail_resize' )
            
        
        self.pub_after_commit( 'notify_new_options' )
        
    
    def _SetJSONDump( self, obj ):
        
        if isinstance( obj, HydrusSerialisable.SerialisableBaseNamed ):
            
            ( dump_type, dump_name, version, serialisable_info ) = obj.GetSerialisableTuple()
            
            try:
                
                dump = json.dumps( serialisable_info )
                
            except Exception as e:
                
                HydrusData.ShowException( e )
                HydrusData.Print( obj )
                HydrusData.Print( serialisable_info )
                
                raise Exception( 'Trying to json dump the object ' + HydrusData.ToUnicode( obj ) + ' with name ' + dump_name + ' caused an error. Its serialisable info has been dumped to the log.' )
                
            
            self._c.execute( 'DELETE FROM json_dumps_named WHERE dump_type = ? AND dump_name = ?;', ( dump_type, dump_name ) )
            
            self._c.execute( 'INSERT INTO json_dumps_named ( dump_type, dump_name, version, dump ) VALUES ( ?, ?, ?, ? );', ( dump_type, dump_name, version, sqlite3.Binary( dump ) ) )
            
        else:
            
            ( dump_type, version, serialisable_info ) = obj.GetSerialisableTuple()
            
            try:
                
                dump = json.dumps( serialisable_info )
                
            except Exception as e:
                
                HydrusData.ShowException( e )
                HydrusData.Print( obj )
                HydrusData.Print( serialisable_info )
                
                raise Exception( 'Trying to json dump the object ' + HydrusData.ToUnicode( obj ) + ' caused an error. Its serialisable info has been dumped to the log.' )
                
            
            self._c.execute( 'DELETE FROM json_dumps WHERE dump_type = ?;', ( dump_type, ) )
            
            self._c.execute( 'INSERT INTO json_dumps ( dump_type, version, dump ) VALUES ( ?, ?, ? );', ( dump_type, version, sqlite3.Binary( dump ) ) )
            
        
    
    def _SetJSONSimple( self, name, value ):
        
        if value is None:
            
            self._c.execute( 'DELET FROM json_dict WHERE name = ?;', ( name, ) )
            
        else:
            
            json_dump = json.dumps( value )
            
            self._c.execute( 'REPLACE INTO json_dict ( name, dump ) VALUES ( ?, ? );', ( name, sqlite3.Binary( json_dump ) ) )
            
        
    
    def _SetPassword( self, password ):
        
        if password is not None: password = hashlib.sha256( password ).digest()
        
        options = self._controller.GetOptions()
        
        options[ 'password' ] = password
        
        self._SaveOptions( options )
        
    
    def _SetServiceFilename( self, service_id, hash_id, filename ):
        
        self._c.execute( 'REPLACE INTO service_filenames ( service_id, hash_id, filename ) VALUES ( ?, ?, ? );', ( service_id, hash_id, filename ) )
        
    
    def _SetServiceDirectory( self, service_id, hash_ids, dirname ):
        
        directory_id = self._GetTextId( dirname )
        
        self._c._execute( 'DELETE FROM service_directories WHERE service_id = ? AND directory_id = ?;', ( service_id, directory_id ) )
        self._c._execute( 'DELETE FROM service_directory_file_map WHERE service_id = ? AND directory_id = ?;', ( service_id, directory_id ) )
        
        num_files = len( hash_ids )
        
        result = self._c.execute( 'SELECT SUM( size ) FROM files_info WHERE hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';' ).fetchone()
        
        if result is None:
            
            total_size = 0
            
        else:
            
            ( total_size, ) = result
            
        
        self._c.execute( 'INSERT INTO service_directories ( service_id, directory_id, num_files, total_size ) VALUES ( ?, ?, ?, ? );', ( service_id, directory_id, num_files, total_size ) )
        self._c.executemany( 'INSERT INTO service_directory_file_map ( service_id, directory_id, hash_id ) VALUES ( ?, ?, ? );', ( ( service_id, directory_id, hash_id ) for hash_id in hash_ids ) )
        
    
    def _SetTagCensorship( self, info ):
        
        self._c.execute( 'DELETE FROM tag_censorship;' )
        
        for ( service_key, blacklist, tags ) in info:
            
            service_id = self._GetServiceId( service_key )
            
            self._c.execute( 'INSERT OR IGNORE INTO tag_censorship ( service_id, blacklist, tags ) VALUES ( ?, ?, ? );', ( service_id, blacklist, tags ) )
            
        
        self.pub_after_commit( 'notify_new_tag_censorship' )
        
    
    def _SetYAMLDump( self, dump_type, dump_name, data ):
        
        if dump_type == YAML_DUMP_ID_SUBSCRIPTION: self._subscriptions_cache[ dump_name ] = data
        
        if dump_type == YAML_DUMP_ID_LOCAL_BOORU: dump_name = dump_name.encode( 'hex' )
        
        self._c.execute( 'DELETE FROM yaml_dumps WHERE dump_type = ? AND dump_name = ?;', ( dump_type, dump_name ) )
        
        try: self._c.execute( 'INSERT INTO yaml_dumps ( dump_type, dump_name, dump ) VALUES ( ?, ?, ? );', ( dump_type, dump_name, data ) )
        except:
            
            HydrusData.Print( ( dump_type, dump_name, data ) )
            
            raise
            
        
        if dump_type == YAML_DUMP_ID_LOCAL_BOORU:
            
            service_id = self._GetServiceId( CC.LOCAL_BOORU_SERVICE_KEY )
            
            self._c.execute( 'DELETE FROM service_info WHERE service_id = ? AND info_type = ?;', ( service_id, HC.SERVICE_INFO_NUM_SHARES ) )
            
            self._controller.pub( 'refresh_local_booru_shares' )
            
        
    
    def _SyncHashesToTagArchive( self, hashes, hta_path, tag_service_key, adding, namespaces ):
        
        hta = None
        
        for ( potential_hta_path, potential_hta ) in self._tag_archives.items():
            
            if hta_path == potential_hta_path:
                
                hta = potential_hta
                
            
        
        if hta is None:
            
            hta = HydrusTagArchive.HydrusTagArchive( hta_path )
            
        
        hash_type = hta.GetHashType()
        
        content_updates = []
        
        for hash in hashes:
            
            if hash_type == HydrusTagArchive.HASH_TYPE_SHA256: archive_hash = hash
            else:
                
                hash_id = self._GetHashId( hash )
                
                if hash_type == HydrusTagArchive.HASH_TYPE_MD5: h = 'md5'
                elif hash_type == HydrusTagArchive.HASH_TYPE_SHA1: h = 'sha1'
                elif hash_type == HydrusTagArchive.HASH_TYPE_SHA512: h = 'sha512'
                
                try: ( archive_hash, ) = self._c.execute( 'SELECT ' + h + ' FROM local_hashes WHERE hash_id = ?;', ( hash_id, ) ).fetchone()
                except: return
                
            
            tags = HydrusTags.CleanTags( hta.GetTags( archive_hash ) )
            
            desired_tags = HydrusTags.FilterNamespaces( tags, namespaces )
            
            if len( desired_tags ) > 0:
                
                if tag_service_key != CC.LOCAL_TAG_SERVICE_KEY and not adding:
                    
                    action = HC.CONTENT_UPDATE_PETITION
                    
                    rows = [ ( tag, ( hash, ), 'admin: tag archive desync' ) for tag in desired_tags ]
                    
                else:
                    
                    if adding:
                        
                        if tag_service_key == CC.LOCAL_TAG_SERVICE_KEY: action = HC.CONTENT_UPDATE_ADD
                        else: action = HC.CONTENT_UPDATE_PEND
                        
                    else: action = HC.CONTENT_UPDATE_DELETE
                    
                    rows = [ ( tag, ( hash, )  ) for tag in desired_tags ]
                    
                
                content_updates.extend( [ HydrusData.ContentUpdate( HC.CONTENT_TYPE_MAPPINGS, action, row ) for row in rows ] )
                
            
        
        if len( content_updates ) > 0:
        
            service_keys_to_content_updates = { tag_service_key : content_updates }
            
            self._ProcessContentUpdates( service_keys_to_content_updates )
            
        
    
    def _TagExists( self, tag ):
        
        if ':' in tag:
            
            ( namespace, tag ) = tag.split( ':', 1 )
            
            result = self._c.execute( 'SELECT namespace_id FROM namespaces WHERE namespace = ?;', ( namespace, ) ).fetchone()
            
            if result is None:
                
                return False
                
            
        
        result = self._c.execute( 'SELECT tag_id FROM tags WHERE tag = ?;', ( tag, ) ).fetchone()
        
        if result is None:
            
            return False
            
        else:
            
            return True
            
        
    
    def _UndeleteFiles( self, hash_ids ):
        
        splayed_hash_ids = HydrusData.SplayListForDB( hash_ids )
        
        rows = self._c.execute( 'SELECT hash_id, timestamp FROM current_files WHERE service_id = ? AND hash_id IN ' + splayed_hash_ids + ';', ( self._trash_service_id, ) ).fetchall()
        
        if len( rows ) > 0:
            
            self._AddFiles( self._local_file_service_id, rows )
            
        
    
    def _UpdateDB( self, version ):
        
        self._controller.pub( 'splash_set_title_text', 'updating db to v' + str( version + 1 ) )
        
        if version == 150:
            
            options = self._GetOptions()
            
            options[ 'file_system_predicates' ][ 'hamming_distance' ] = 5
            
            self._c.execute( 'UPDATE options SET options = ?;', ( options, ) )
            
        
        if version == 151:
            
            results = self._c.execute( 'SELECT * FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_SUBSCRIPTION, ) ).fetchall()
            
            for ( dump_type, dump_name, dump ) in results:
                
                dump[ 'initial_limit' ] = 500
                
                self._c.execute( 'UPDATE yaml_dumps SET dump = ? WHERE dump_type = ? and dump_name = ?;', ( dump, dump_type, dump_name ) )
                
            
        
        if version == 152:
            
            options = self._GetOptions()
            
            options[ 'file_system_predicates' ][ 'num_pixels' ] = ( 1, 2, 2 )
            
            self._c.execute( 'UPDATE options SET options = ?;', ( options, ) )
            
        
        if version == 153:
            
            options = self._GetOptions()
            
            options[ 'file_system_predicates' ] = ClientDefaults.GetClientDefaultOptions()[ 'file_system_predicates' ]
            
            self._c.execute( 'UPDATE options SET options = ?;', ( options, ) )
            
            #
            
            self._c.execute( 'CREATE TABLE json_dumps ( dump_type INTEGER PRIMARY KEY, version INTEGER, dump BLOB_BYTES );' )
            self._c.execute( 'CREATE TABLE json_dumps_named ( dump_type INTEGER, dump_name TEXT, version INTEGER, dump BLOB_BYTES, PRIMARY KEY ( dump_type, dump_name ) );' )
            
            #
            
            results = self._c.execute( 'SELECT * FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_FAVOURITE_CUSTOM_FILTER_ACTIONS, ) ).fetchall()
            
            objs = []
            
            for ( dump_type, dump_name, dump ) in results:
                
                shortcuts = ClientData.Shortcuts( dump_name )
                
                actions = dump
                
                for ( modifier, key, service_key, data ) in actions:
                    
                    if isinstance( service_key, ClientData.ClientServiceIdentifier ): service_key = service_key.GetServiceKey()
                    
                    action = ( service_key, data )
                    
                    shortcuts.SetKeyboardAction( modifier, key, action )
                    
                
                objs.append( shortcuts )
                
            
            for obj in objs:
                
                ( dump_type, dump_name, dump_version, serialisable_info ) = obj.GetSerialisableTuple()
                
                dump = json.dumps( serialisable_info )
                
                self._c.execute( 'INSERT INTO json_dumps_named ( dump_type, dump_name, version, dump ) VALUES ( ?, ?, ?, ? );', ( dump_type, dump_name, dump_version, sqlite3.Binary( dump ) ) )
                
            
            self._c.execute( 'DELETE FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_FAVOURITE_CUSTOM_FILTER_ACTIONS, ) )
            
        
        if version == 156:
            
            results = self._c.execute( 'SELECT dump_type, dump_name, dump FROM json_dumps_named;' ).fetchall()
            
            for ( dump_type, dump_name, dump ) in results:
                
                try:
                    
                    dump = lz4.loads( dump )
                    
                    self._c.execute( 'UPDATE json_dumps_named SET dump = ? WHERE dump_type = ? AND dump_name = ?;', ( sqlite3.Binary( dump ), dump_type, dump_name ) )
                    
                except:
                    
                    continue
                    
                
            
        
        if version == 157:
            
            results = self._c.execute( 'SELECT * FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_SUBSCRIPTION, ) ).fetchall()
            
            for ( dump_type, dump_name, dump ) in results:
                
                dump[ 'get_tags_if_redundant' ] = False
                
                a_i_o = dump[ 'advanced_import_options' ]
                
                if 'auto_archive' not in a_i_o:
                    
                    a_i_o[ 'auto_archive' ] = False
                    
                
                if 'exclude_deleted_files' not in a_i_o:
                    
                    a_i_o[ 'exclude_deleted_files' ] = False
                    
                
                if 'min_resolution' not in a_i_o:
                    
                    a_i_o[ 'min_resolution' ] = None
                    
                
                if 'min_size' not in a_i_o:
                    
                    a_i_o[ 'min_size' ] = None
                    
                
                self._c.execute( 'UPDATE yaml_dumps SET dump = ? WHERE dump_type = ? and dump_name = ?;', ( dump, dump_type, dump_name ) )
                
            
            #
            
            results = self._c.execute( 'SELECT service_id, service_type, info FROM services WHERE service_type IN ( ?, ? );', ( HC.LOCAL_RATING_LIKE, HC.LOCAL_RATING_NUMERICAL ) ).fetchall()
            
            for ( service_id, service_type, info ) in results:
                
                if service_type == HC.LOCAL_RATING_LIKE:
                    
                    del info[ 'like' ]
                    del info[ 'dislike' ]
                    
                    info[ 'colours' ] = ClientRatings.default_like_colours
                    
                else:
                    
                    upper = info[ 'upper' ]
                    lower = info[ 'lower' ]
                    
                    del info[ 'upper' ]
                    del info[ 'lower' ]
                    
                    info[ 'num_stars' ] = upper - lower
                    
                    info[ 'colours' ] = ClientRatings.default_numerical_colours
                    
                
                info[ 'shape' ] = ClientRatings.CIRCLE
                
                self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( info, service_id ) )
                
            
            #
            
            results = self._c.execute( 'SELECT * FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_EXPORT_FOLDER, ) ).fetchall()
            
            for ( dump_type, dump_name, dump ) in results:
                
                details = dump
                
                details[ 'type' ] = HC.EXPORT_FOLDER_TYPE_REGULAR
                
                self._c.execute( 'UPDATE yaml_dumps SET dump = ? WHERE dump_type = ? and dump_name = ?;', ( dump, dump_type, dump_name ) )
                
            
        
        if version == 158:
            
            results = self._c.execute( 'SELECT service_id, service_type, info FROM services WHERE service_type IN ( ?, ? );', ( HC.TAG_REPOSITORY, HC.FILE_REPOSITORY ) ).fetchall()
            
            for ( service_id, service_type, info ) in results:
                
                info[ 'first_timestamp' ] = None
                info[ 'next_download_timestamp' ] = 0
                
                self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( info, service_id ) )
                
            
            for filename in os.listdir( HC.CLIENT_UPDATES_DIR ):
                
                path = os.path.join( HC.CLIENT_UPDATES_DIR, filename )
                
                ClientData.DeletePath( path )
                
            
        
        if version == 159:
            
            results = self._c.execute( 'SELECT service_id, service_type, info FROM services WHERE service_type = ?;', ( HC.LOCAL_RATING_NUMERICAL, ) ).fetchall()
            
            for ( service_id, service_type, info ) in results:
                
                info[ 'allow_zero' ] = True
                
                self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( info, service_id ) )
                
            
        
        if version == 160:
            
            self._c.execute( 'REPLACE INTO yaml_dumps VALUES ( ?, ?, ? );', ( YAML_DUMP_ID_REMOTE_BOORU, 'e621', ClientDefaults.GetDefaultBoorus()[ 'e621' ] ) )
            
            self._c.execute( 'DROP TABLE ratings_filter;' )
            
        
        if version == 161:
            
            self._c.execute( 'DELETE FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_GUI_SESSION, ) )
            self._c.execute( 'DELETE FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_EXPORT_FOLDER, ) )
            
            #
            
            for filename in os.listdir( HC.CLIENT_UPDATES_DIR ):
                
                path = os.path.join( HC.CLIENT_UPDATES_DIR, filename )
                
                with open( path, 'rb' ) as f:
                    
                    inefficient_string = f.read()
                    
                
                try:
                    
                    ( dump_type, dump_version, dump ) = json.loads( inefficient_string )
                    
                    serialisable_info = json.loads( dump )
                    
                    better_string = json.dumps( ( dump_type, dump_version, serialisable_info ) )
                    
                    with open( path, 'wb' ) as f:
                        
                        f.write( better_string )
                        
                    
                except:
                    
                    continue
                    
                
            
        
        if version == 162:
            
            self._c.execute( 'DROP INDEX mappings_service_id_tag_id_index;' )
            self._c.execute( 'DROP INDEX mappings_service_id_hash_id_index;' )
            self._c.execute( 'DROP INDEX mappings_service_id_status_index;' )
            
            self._c.execute( 'CREATE INDEX mappings_namespace_id_index ON mappings ( namespace_id );' )
            self._c.execute( 'CREATE INDEX mappings_tag_id_index ON mappings ( tag_id );' )
            self._c.execute( 'CREATE INDEX mappings_status_index ON mappings ( status );' )
            
        
        if version == 163:
            
            self._c.execute( 'DROP INDEX mappings_status_index;' )
            
            self._c.execute( 'CREATE INDEX mappings_status_pending_index ON mappings ( status ) WHERE status = 1;' )
            self._c.execute( 'CREATE INDEX mappings_status_deleted_index ON mappings ( status ) WHERE status = 2;' )
            
            #
            
            info = {}
            
            self._AddService( CC.TRASH_SERVICE_KEY, HC.LOCAL_FILE, CC.TRASH_SERVICE_KEY, info )
            
            self._trash_service_id = self._GetServiceId( CC.TRASH_SERVICE_KEY )
            self._local_file_service_id = self._GetServiceId( CC.LOCAL_FILE_SERVICE_KEY )
            
            deleted_hash_ids = [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM deleted_files WHERE service_id = ?;', ( self._local_file_service_id, ) ) ]
            
            self._c.executemany( 'INSERT OR IGNORE INTO deleted_files ( service_id, hash_id ) VALUES ( ?, ? );', ( ( self._trash_service_id, hash_id ) for hash_id in deleted_hash_ids ) )
            
        
        if version == 164:
            
            self._c.execute( 'CREATE TABLE file_trash ( hash_id INTEGER PRIMARY KEY, timestamp INTEGER );' )
            self._c.execute( 'CREATE INDEX file_trash_timestamp ON file_trash ( timestamp );' )
            
            self._trash_service_id = self._GetServiceId( CC.TRASH_SERVICE_KEY )
            
            trash_hash_ids = [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM files_info WHERE service_id = ?;', ( self._trash_service_id, ) ) ]
            
            now = HydrusData.GetNow()
            
            self._c.executemany( 'INSERT OR IGNORE INTO file_trash ( hash_id, timestamp ) VALUES ( ?, ? );', ( ( hash_id, now ) for hash_id in trash_hash_ids ) )
            
            self._c.execute( 'DELETE FROM service_info WHERE service_id = ?;', ( self._trash_service_id, ) )
            
            #
            
            self._c.execute( 'DROP INDEX mappings_status_pending_index;' )
            self._c.execute( 'DROP INDEX mappings_status_deleted_index;' )
            
            self._c.execute( 'CREATE INDEX mappings_status_index ON mappings ( status );' )
            
            #
            
            self._c.execute( 'REPLACE INTO yaml_dumps VALUES ( ?, ?, ? );', ( YAML_DUMP_ID_REMOTE_BOORU, 'yande.re', ClientDefaults.GetDefaultBoorus()[ 'yande.re' ] ) )
            
        
        if version == 169:
            
            result = self._c.execute( 'SELECT tag_id FROM tags WHERE tag = ?;', ( '', ) ).fetchone()
            
            if result is not None:
                
                ( tag_id, ) = result
                
                self._c.execute( 'DELETE FROM mappings WHERE tag_id = ?;', ( tag_id, ) )
                
            
            #
            
            def iterate_all_file_paths():
                
                for prefix in HydrusData.IterateHexPrefixes():
                    
                    dir = os.path.join( HC.CLIENT_FILES_DIR, prefix )
                    
                    next_paths = os.listdir( dir )
                    
                    for path in next_paths:
                        
                        yield os.path.join( dir, path )
                        
                    
                
            
            for ( i, path ) in enumerate( iterate_all_file_paths() ):
                
                try: os.chmod( path, stat.S_IWRITE | stat.S_IREAD )
                except: pass
                
                if i % 100 == 0:
                    
                    self._controller.pub( 'splash_set_status_text', 'updating file permissions ' + HydrusData.ConvertIntToPrettyString( i ) )
                    
                
            
        
        if version == 171:
            
            self._controller.pub( 'splash_set_status_text', 'moving updates about' )
            
            for filename in os.listdir( HC.CLIENT_UPDATES_DIR ):
                
                try:
                    
                    ( service_key_encoded, gumpf ) = filename.split( '_', 1 )
                    
                except ValueError:
                    
                    continue
                    
                
                dest_dir = os.path.join( HC.CLIENT_UPDATES_DIR, service_key_encoded )
                
                if not os.path.exists( dest_dir ):
                    
                    os.makedirs( dest_dir )
                    
                
                source_path = os.path.join( HC.CLIENT_UPDATES_DIR, filename )
                dest_path = os.path.join( dest_dir, gumpf )
                
                shutil.move( source_path, dest_path )
                
            
            #
            
            service_ids = self._GetServiceIds( ( HC.LOCAL_RATING_LIKE, HC.LOCAL_RATING_NUMERICAL ) )
            
            for service_id in service_ids: self._c.execute( 'DELETE FROM service_info WHERE service_id = ?;', ( service_id, ) )
            
        
        if version == 172:
            
            delete_actions = {}
            
            delete_actions[ CC.STATUS_SUCCESSFUL ] = CC.IMPORT_FOLDER_DELETE
            delete_actions[ CC.STATUS_REDUNDANT ] = CC.IMPORT_FOLDER_DELETE
            delete_actions[ CC.STATUS_DELETED ] = CC.IMPORT_FOLDER_DELETE
            delete_actions[ CC.STATUS_FAILED ] = CC.IMPORT_FOLDER_IGNORE
            
            sync_actions = {}
            
            sync_actions[ CC.STATUS_SUCCESSFUL ] = CC.IMPORT_FOLDER_IGNORE
            sync_actions[ CC.STATUS_REDUNDANT ] = CC.IMPORT_FOLDER_IGNORE
            sync_actions[ CC.STATUS_DELETED ] = CC.IMPORT_FOLDER_IGNORE
            sync_actions[ CC.STATUS_FAILED ] = CC.IMPORT_FOLDER_IGNORE
            
            import_folders = []
            
            results = self._c.execute( 'SELECT dump_name, dump FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_IMPORT_FOLDER, ) )
            
            for ( i, ( path, details ) ) in enumerate( results ):
                
                name = 'import folder ' + str( i )
                
                import_file_options = ClientData.ImportFileOptions( automatic_archive = False, exclude_deleted = False, min_size = None, min_resolution = None )
                
                if details[ 'type' ] == HC.IMPORT_FOLDER_TYPE_DELETE:
                    
                    actions = delete_actions
                    
                else:
                    
                    actions = sync_actions
                    
                
                period = details[ 'check_period' ]
                
                tag = details[ 'local_tag' ]
                
                service_keys_to_explicit_tags = dict()
                
                if tag is not None:
                    
                    service_keys_to_explicit_tags[ CC.LOCAL_TAG_SERVICE_KEY ] = { tag }
                    
                
                import_tag_options = ClientData.ImportTagOptions( service_keys_to_explicit_tags = service_keys_to_explicit_tags )
                
                import_folder = ClientImporting.ImportFolder( name, path, import_file_options = import_file_options, import_tag_options = import_tag_options, actions = actions, action_locations = {}, period = period, open_popup = True )
                
                import_folder._last_checked = details[ 'last_checked' ]
                
                for path in details[ 'cached_imported_paths' ]:
                    
                    import_folder._path_cache.AddSeed( path )
                    import_folder._path_cache.UpdateSeedStatus( path, CC.STATUS_SUCCESSFUL )
                    
                
                for path in details[ 'failed_imported_paths' ]:
                    
                    import_folder._path_cache.AddSeed( path )
                    import_folder._path_cache.UpdateSeedStatus( path, CC.STATUS_FAILED )
                    
                
                import_folder._paused = True
                
                import_folders.append( import_folder )
                
            
            for import_folder in import_folders:
                
                ( dump_type, dump_name, obj_version, serialisable_info ) = import_folder.GetSerialisableTuple()
                
                dump = json.dumps( serialisable_info )
                
                self._c.execute( 'INSERT INTO json_dumps_named ( dump_type, dump_name, version, dump ) VALUES ( ?, ?, ?, ? );', ( dump_type, dump_name, obj_version, sqlite3.Binary( dump ) ) )
                
            
        
        if version == 175:
            
            HC.options = self._GetOptions()
            self._controller._options = HC.options
            
            self._c.execute( 'DELETE FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_IMPORT_FOLDER, ) )
            
            #
            
            def ConvertSiteTypeQueryTypeToGalleryIdentifier( site_type, query_type ):
                
                if site_type == HC.SITE_TYPE_BOORU:
                    
                    ( booru_name, gumpf ) = query_type
                    
                    return ClientDownloading.GalleryIdentifier( site_type, additional_info = booru_name )
                    
                elif site_type == HC.SITE_TYPE_HENTAI_FOUNDRY:
                    
                    if query_type in ( 'tag', 'tags' ):
                        
                        return ClientDownloading.GalleryIdentifier( HC.SITE_TYPE_HENTAI_FOUNDRY_TAGS )
                        
                    else:
                        
                        return ClientDownloading.GalleryIdentifier( HC.SITE_TYPE_HENTAI_FOUNDRY_ARTIST )
                        
                    
                elif site_type == HC.SITE_TYPE_PIXIV:
                    
                    if query_type in ( 'tag', 'tags' ):
                        
                        return ClientDownloading.GalleryIdentifier( HC.SITE_TYPE_PIXIV_TAG )
                        
                    else:
                        
                        return ClientDownloading.GalleryIdentifier( HC.SITE_TYPE_PIXIV_ARTIST_ID )
                        
                    
                else:
                    
                    return ClientDownloading.GalleryIdentifier( site_type )
                    
                
            
            #
            
            subscriptions = []
            
            results = self._c.execute( 'SELECT dump_name, dump FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_SUBSCRIPTION, ) )
            
            for ( name, info ) in results:
                
                try:
                    
                    self._controller.pub( 'splash_set_status_text', 'updating subscription ' + name )
                    
                    subscription = ClientImporting.Subscription( name )
                    
                    site_type = info[ 'site_type' ]
                    query_type = info[ 'query_type' ]
                    
                    frequency_type = info[ 'frequency_type' ]
                    frequency = info[ 'frequency' ]
                    
                    service_keys_to_namespaces = info[ 'advanced_tag_options' ]
                    import_file_options = info[ 'advanced_import_options' ]
                    
                    automatic_archive = import_file_options[ 'auto_archive' ]
                    exclude_deleted = import_file_options[ 'exclude_deleted_files' ]
                    min_size = import_file_options[ 'min_size' ]
                    min_resolution = import_file_options[ 'min_resolution' ]
                    
                    gallery_identifier = ConvertSiteTypeQueryTypeToGalleryIdentifier( site_type, query_type )
                    gallery_stream_identifiers = ClientDownloading.GetGalleryStreamIdentifiers( gallery_identifier )
                    query = info[ 'query' ]
                    period = frequency_type * frequency
                    get_tags_if_redundant = info[ 'get_tags_if_redundant' ]
                    
                    if 'initial_limit' in info:
                        
                        initial_file_limit = info[ 'initial_limit' ]
                        
                    else:
                        
                        initial_file_limit = None
                        
                    
                    periodic_file_limit = None
                    paused = info[ 'paused' ]
                    import_file_options = ClientData.ImportFileOptions( automatic_archive = automatic_archive, exclude_deleted = exclude_deleted, min_size = min_size, min_resolution = min_resolution )
                    import_tag_options = ClientData.ImportTagOptions( service_keys_to_namespaces = service_keys_to_namespaces )
                    
                    subscription.SetTuple( gallery_identifier, gallery_stream_identifiers, query, period, get_tags_if_redundant, initial_file_limit, periodic_file_limit, paused, import_file_options, import_tag_options )
                    
                    last_checked = info[ 'last_checked' ]
                    
                    if last_checked is None:
                        
                        last_checked = 0
                        
                    
                    subscription._last_checked = last_checked
                    
                    for url in info[ 'url_cache' ]:
                        
                        subscription._seed_cache.AddSeed( url )
                        subscription._seed_cache.UpdateSeedStatus( url, CC.STATUS_SUCCESSFUL )
                        
                    
                    subscriptions.append( subscription )
                    
                except:
                    
                    traceback.print_exc()
                    
                    self._controller.pub( 'splash_set_status_text', 'error updating subscription ' + name )
                    
                    time.sleep( 5 )
                    
                
            
            self._controller.pub( 'splash_set_status_text', 'saving updated subscriptions' )
            
            for subscription in subscriptions:
                
                ( dump_type, dump_name, obj_version, serialisable_info ) = subscription.GetSerialisableTuple()
                
                dump = json.dumps( serialisable_info )
                
                self._c.execute( 'INSERT INTO json_dumps_named ( dump_type, dump_name, version, dump ) VALUES ( ?, ?, ?, ? );', ( dump_type, dump_name, obj_version, sqlite3.Binary( dump ) ) )
                
            
            self._c.execute( 'DELETE FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_SUBSCRIPTION, ) )
            
            #
            
            self._controller.pub( 'splash_set_status_text', 'updating gui sessions with gallery download pages' )
            
            import ClientGUIManagement
            import ClientGUIPages
            
            new_sessions = []
            
            sessions = self._GetJSONDumpNamed( HydrusSerialisable.SERIALISABLE_TYPE_GUI_SESSION )
            
            for session in sessions:
                
                session_name = session.GetName()
                
                new_session = ClientGUIPages.GUISession( session_name )
                
                for ( page_name, management_controller, hashes ) in session.IteratePages():
                    
                    if management_controller.GetType() == ClientGUIManagement.MANAGEMENT_TYPE_IMPORT_GALLERY:
                        
                        try:
                            
                            site_type = management_controller.GetVariable( 'site_type' )
                            query_type = management_controller.GetVariable( 'gallery_type' )
                            
                            gallery_identifier = ConvertSiteTypeQueryTypeToGalleryIdentifier( site_type, query_type )
                            
                            management_controller = ClientGUIManagement.CreateManagementControllerImportGallery( gallery_identifier )
                            
                            gallery_import = management_controller.GetVariable( 'gallery_import' )
                            
                        except:
                            
                            traceback.print_exc()
                            
                            continue
                            
                        
                    
                    new_session.AddPage( page_name, management_controller, hashes )
                    
                
                self._SetJSONDump( new_session )
                
            
        
        if version == 176:
            
            old_options = self._GetOptions()
            
            new_options = ClientData.ClientOptions()
            
            self._controller._new_options = new_options
            
            for ( name, ato ) in old_options[ 'default_advanced_tag_options' ].items():
                
                try:
                    
                    if name == 'default':
                        
                        gallery_identifier = ClientDownloading.GalleryIdentifier( HC.SITE_TYPE_DEFAULT )
                        
                    elif isinstance( name, int ):
                        
                        site_type = name
                        
                        gallery_identifier = ClientDownloading.GalleryIdentifier( site_type )
                        
                    else:
                        
                        ( booru_id, booru_name ) = name
                        
                        gallery_identifier = ClientDownloading.GalleryIdentifier( HC.SITE_TYPE_BOORU, additional_info = booru_name )
                        
                    
                    service_keys_to_namespaces = {}
                    
                    for ( service_key, namespace_object ) in ato.items():
                        
                        if isinstance( namespace_object, list ):
                            
                            service_keys_to_namespaces[ service_key ] = namespace_object
                            
                        elif isinstance( namespace_object, bool ):
                            
                            service_keys_to_namespaces[ service_key ] = [ 'all namespaces' ]
                            
                        
                    
                    import_tag_options = ClientData.ImportTagOptions( service_keys_to_namespaces = service_keys_to_namespaces )
                    
                    new_options.SetDefaultImportTagOptions( gallery_identifier, import_tag_options )
                    
                except:
                    
                    traceback.print_exc()
                    
                    continue
                    
                
            
            #
            
            ( dump_type, dump_version, serialisable_info ) = new_options.GetSerialisableTuple()
            
            dump = json.dumps( serialisable_info )
            
            self._c.execute( 'INSERT INTO json_dumps ( dump_type, version, dump ) VALUES ( ?, ?, ? );', ( dump_type, dump_version, sqlite3.Binary( dump ) ) )
            
            #
            
            del old_options[ 'default_advanced_tag_options' ]
            
            self._c.execute( 'UPDATE options SET options = ?;', ( old_options, ) )
            
        
        if version == 177:
            
            self._c.execute( 'DROP INDEX mappings_status_index;' )
            self._c.execute( 'CREATE INDEX mappings_service_id_status_index ON mappings ( service_id, status );' )
            
        
        if version == 180:
            
            self._c.execute( 'REPLACE INTO yaml_dumps VALUES ( ?, ?, ? );', ( YAML_DUMP_ID_REMOTE_BOORU, 'rule34hentai', ClientDefaults.GetDefaultBoorus()[ 'rule34hentai' ] ) )
            
            #
            
            names_seen = set()
            
            info = self._c.execute( 'SELECT service_id, name FROM services;', ).fetchall()
            
            for ( service_id, name ) in info:
                
                if name in names_seen:
                    
                    while name in names_seen:
                        
                        name += str( random.randint( 0, 9 ) )
                        
                    
                    self._c.execute( 'UPDATE services SET name = ? WHERE service_id = ?;', ( name, service_id ) )
                    
                
                names_seen.add( name )
                
            
        
        if version == 182:
            
            hash_ids = { hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM files_info WHERE mime = ?;', ( HC.APPLICATION_FLASH, ) ) }
            
            num_done = 0
            
            num_to_do = len( hash_ids )
            
            for hash_id in hash_ids:
                
                num_done += 1
                
                if num_done % 10 == 0:
                    
                    self._controller.pub( 'splash_set_status_text', 'updating flash thumbnails: ' + HydrusData.ConvertValueRangeToPrettyString( num_done, num_to_do ) )
                    
                
                hash = self._GetHash( hash_id )
                
                file_path = ClientFiles.GetExpectedFilePath( HC.CLIENT_FILES_DIR, hash, HC.APPLICATION_FLASH )
                
                if os.path.exists( file_path ):
                    
                    thumbnail = HydrusFileHandling.GenerateThumbnail( file_path )
                    
                    self._AddThumbnails( [ ( hash, thumbnail ) ] )
                    
                
            
            #
            
            self._c.execute( 'DELETE FROM service_info WHERE info_type IN ( ?, ? );', ( HC.SERVICE_INFO_NUM_THUMBNAILS, HC.SERVICE_INFO_NUM_THUMBNAILS_LOCAL ) )
            
        
        if version == 183:
            
            self._c.execute( 'CREATE TABLE client_files_locations ( prefix TEXT, location TEXT );' )
            
            location = HydrusPaths.ConvertAbsPathToPortablePath( HC.CLIENT_FILES_DIR )
            
            for prefix in HydrusData.IterateHexPrefixes():
                
                self._c.execute( 'INSERT INTO client_files_locations ( prefix, location ) VALUES ( ?, ? );', ( prefix, location ) )
                
            
        
        if version == 184:
            
            result = self._c.execute( 'SELECT tag_id FROM tags WHERE tag = ?;', ( '', ) ).fetchone()
            
            if result is not None:
                
                ( tag_id, ) = result
                
                self._c.execute( 'DELETE FROM mappings WHERE tag_id = ?;', ( tag_id, ) )
                
            
        
        if version == 188:
            
            self._c.execute( 'CREATE TABLE analyze_timestamps ( name TEXT, timestamp INTEGER );' )
            
        
        if version == 189:
            
            self._controller.pub( 'splash_set_status_text', 'updating file tables' )
            
            #
            
            self._c.execute( 'DROP INDEX file_petitions_hash_id_index;' )
            
            self._c.execute( 'ALTER TABLE file_petitions RENAME TO file_petitions_old;' )
            
            self._c.execute( 'CREATE TABLE file_petitions ( service_id INTEGER, hash_id INTEGER, reason_id INTEGER, PRIMARY KEY( service_id, hash_id, reason_id ) );' )
            self._c.execute( 'CREATE INDEX file_petitions_hash_id_index ON file_petitions ( hash_id );' )
            
            self._c.execute( 'INSERT INTO file_petitions SELECT * FROM file_petitions_old;' )
            
            self._c.execute( 'DROP TABLE file_petitions_old;' )
            
            #
            
            self._c.execute( 'ALTER TABLE files_info RENAME TO files_info_old;' )
            
            self._c.execute( 'CREATE TABLE current_files ( service_id INTEGER REFERENCES services ON DELETE CASCADE, hash_id INTEGER, timestamp INTEGER, PRIMARY KEY( service_id, hash_id ) );' )
            self._c.execute( 'CREATE INDEX current_files_timestamp ON current_files ( timestamp );' )
            
            self._c.execute( 'CREATE TABLE files_info ( hash_id INTEGER PRIMARY KEY, size INTEGER, mime INTEGER, width INTEGER, height INTEGER, duration INTEGER, num_frames INTEGER, num_words INTEGER );' )
            self._c.execute( 'CREATE INDEX files_info_size ON files_info ( size );' )
            self._c.execute( 'CREATE INDEX files_info_mime ON files_info ( mime );' )
            self._c.execute( 'CREATE INDEX files_info_width ON files_info ( width );' )
            self._c.execute( 'CREATE INDEX files_info_height ON files_info ( height );' )
            self._c.execute( 'CREATE INDEX files_info_duration ON files_info ( duration );' )
            self._c.execute( 'CREATE INDEX files_info_num_frames ON files_info ( num_frames );' )
            
            self._c.execute( 'INSERT INTO current_files SELECT service_id, hash_id, timestamp FROM files_info_old;' )
            self._c.execute( 'INSERT OR IGNORE INTO files_info SELECT hash_id, size, mime, width, height, duration, num_frames, num_words FROM files_info_old;' )
            
            self._c.execute( 'DROP TABLE files_info_old;' )
            
        
        if version == 192:
            
            no_wal_path = os.path.join( HC.DB_DIR, 'no-wal' )
            
            if os.path.exists( no_wal_path ):
                
                os.remove( no_wal_path )
                
            
        
        if version == 193:
            
            self._c.execute( 'CREATE TABLE service_filenames ( service_id INTEGER REFERENCES services ON DELETE CASCADE, hash_id INTEGER, filename TEXT, PRIMARY KEY( service_id, hash_id ) );' )
            
        
        if version == 194:
            
            service_data = self._c.execute( 'SELECT service_id, info FROM services WHERE service_type IN ( ?, ? );', ( HC.FILE_REPOSITORY, HC.TAG_REPOSITORY ) ).fetchall()
            
            for ( service_id, info ) in service_data:
                
                info[ 'next_processing_timestamp' ] = 0
                
                self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( info, service_id ) )
                
            
            #
            
            service_data = self._c.execute( 'SELECT service_id, info FROM services WHERE service_type = ?;', ( HC.IPFS, ) ).fetchall()
            
            for ( service_id, info ) in service_data:
                
                info[ 'multihash_prefix' ] = ''
                
                self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( info, service_id ) )
                
            
        
        if version == 195:
            
            self._controller.pub( 'splash_set_status_text', 'clearing out surplus autocomplete entries' )
            
            combined_tag_service_id = self._GetServiceId( CC.COMBINED_TAG_SERVICE_KEY )
            
            self._c.execute( 'DELETE FROM autocomplete_tags_cache WHERE tag_service_id = ?;', ( combined_tag_service_id, ) )
            
            #
            
            self._controller.pub( 'splash_set_status_text', 'clearing out existing tags orphans' )
            
            self._c.execute( 'DELETE FROM existing_tags;' )
            
            self._c.execute( 'INSERT OR IGNORE INTO existing_tags SELECT DISTINCT namespace_id, tag_id FROM mappings;' )
            self._c.execute( 'INSERT OR IGNORE INTO existing_tags SELECT DISTINCT child_namespace_id, child_tag_id FROM tag_parents;' )
            self._c.execute( 'INSERT OR IGNORE INTO existing_tags SELECT DISTINCT parent_namespace_id, parent_tag_id FROM tag_parents;' )
            self._c.execute( 'INSERT OR IGNORE INTO existing_tags SELECT DISTINCT old_namespace_id, old_tag_id FROM tag_siblings;' )
            self._c.execute( 'INSERT OR IGNORE INTO existing_tags SELECT DISTINCT new_namespace_id, new_tag_id FROM tag_siblings;' )
            
            #
            
            self._controller.pub( 'splash_set_status_text', 'clearing out orphan autocomplete entries' )
            
            namespace_ids = [ namespace_id for ( namespace_id, ) in self._c.execute( 'SELECT namespace_id FROM namespaces;' ) ]
            
            for namespace_id in namespace_ids:
                
                self._c.execute( 'DELETE FROM autocomplete_tags_cache WHERE namespace_id = ? AND tag_id NOT IN ( SELECT tag_id FROM existing_tags WHERE namespace_id = ? );', ( namespace_id, namespace_id ) )
                
            
        
        if version == 196:
            
            self._controller.pub( 'splash_set_status_text', 'clearing out more surplus autocomplete entries' )
            
            combined_file_service_id = self._GetServiceId( CC.COMBINED_FILE_SERVICE_KEY )
            
            self._c.execute( 'DELETE FROM autocomplete_tags_cache WHERE file_service_id != ?;', ( combined_file_service_id, ) )
            
        
        if version == 198:
            
            all_service_info = self._c.execute( 'SELECT * FROM services;' ).fetchall()
            
            self._c.execute( 'DROP TABLE services;' )
            
            self._c.execute( 'CREATE TABLE services ( service_id INTEGER PRIMARY KEY AUTOINCREMENT, service_key BLOB_BYTES, service_type INTEGER, name TEXT, info TEXT_YAML );' )
            self._c.execute( 'CREATE UNIQUE INDEX services_service_key_index ON services ( service_key );' )
            
            self._c.executemany( 'INSERT INTO services VALUES ( ?, ?, ?, ?, ? );', ( ( service_id, sqlite3.Binary( service_key ), service_type, name, info ) for ( service_id, service_key, service_type, name, info ) in all_service_info ) )
            
            self._c.execute( 'DROP TABLE autocomplete_tags_cache;' )
            
            #
            
            self._controller.pub( 'splash_set_status_text', 'exporting mappings to external db' )
            
            self._c.execute( 'CREATE TABLE IF NOT EXISTS external_mappings.mappings ( service_id INTEGER, namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, status INTEGER, PRIMARY KEY( service_id, namespace_id, tag_id, hash_id, status ) );' )
            
            self._c.execute( 'INSERT INTO external_mappings.mappings SELECT * FROM main.mappings;' )
            
            self._c.execute( 'DROP TABLE main.mappings;' )
            
            self._c.execute( 'CREATE TABLE IF NOT EXISTS external_mappings.mapping_petitions ( service_id INTEGER, namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, reason_id INTEGER, PRIMARY KEY( service_id, namespace_id, tag_id, hash_id, reason_id ) );' )
            
            self._c.execute( 'INSERT INTO external_mappings.mapping_petitions SELECT * FROM main.mapping_petitions;' )
            
            self._c.execute( 'DROP TABLE main.mapping_petitions;' )
            
        
        if version == 199:
            
            self._c.execute( 'CREATE TABLE json_dict ( name TEXT PRIMARY KEY, dump BLOB_BYTES );' )
            
            results = self._GetYAMLDump( YAML_DUMP_ID_SINGLE )
            
            for ( name, value ) in results.items():
                
                self._SetJSONSimple( name, value )
                
            
            self._c.execute( 'DELETE FROM yaml_dumps WHERE dump_type = ?;', ( YAML_DUMP_ID_SINGLE, ) )
            
            #
            
            self._controller.pub( 'splash_set_status_text', 'exporting deleted mappings to new table' )
            
            self._c.execute( 'CREATE TABLE IF NOT EXISTS external_mappings.deleted_mappings ( service_id INTEGER, namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( service_id, namespace_id, tag_id, hash_id ) );' )
            
            self._c.execute( 'INSERT INTO external_mappings.deleted_mappings SELECT service_id, namespace_id, tag_id, hash_id FROM mappings WHERE status = ?;', ( HC.DELETED, ) )
            
            self._c.execute( 'DELETE FROM mappings WHERE status = ?;', ( HC.DELETED, ) )
            
            self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.deleted_mappings_namespace_id_index ON deleted_mappings ( namespace_id );' )
            self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.deleted_mappings_tag_id_index ON deleted_mappings ( tag_id );' )
            self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.deleted_mappings_hash_id_index ON deleted_mappings ( hash_id );' )
            
        
        if version == 200:
            
            self._controller.pub( 'splash_set_status_text', 'deleting service mapping orphans' )
            
            names = { name for ( name, ) in self._c.execute( 'SELECT name FROM external_mappings.sqlite_master WHERE type = ?;', ( 'table', ) ) }
            
            if 'mappings' in names: # it is possible that at least one user did the update, but the subsequent vacuum failed, so the version didn't increment, so this catches them
                
                service_ids = self._GetServiceIds( HC.TAG_SERVICES )
                
                splayed_service_ids = HydrusData.SplayListForDB( service_ids )
                
                self._c.execute( 'DELETE FROM mappings WHERE service_id NOT IN ' + splayed_service_ids + ';' )
                self._c.execute( 'DELETE FROM deleted_mappings WHERE service_id NOT IN ' + splayed_service_ids + ';' )
                self._c.execute( 'DELETE FROM mapping_petitions WHERE service_id NOT IN ' + splayed_service_ids + ';' )
                
                #
                
                self._controller.pub( 'splash_set_status_text', 'exporting hashes to external db' )
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS external_master.hashes ( hash_id INTEGER PRIMARY KEY, hash BLOB_BYTES UNIQUE );' )
                
                self._c.execute( 'INSERT INTO external_master.hashes SELECT * FROM main.hashes;' )
                
                self._c.execute( 'DROP TABLE main.hashes;' )
                
                #
                
                self._controller.pub( 'splash_set_status_text', 'exporting tags to external db' )
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS external_master.namespaces ( namespace_id INTEGER PRIMARY KEY, namespace TEXT UNIQUE );' )
                
                self._c.execute( 'INSERT INTO external_master.namespaces SELECT * FROM main.namespaces;' )
                
                self._c.execute( 'DROP TABLE main.namespaces;' )
                
                #
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS external_master.tags ( tag_id INTEGER PRIMARY KEY, tag TEXT UNIQUE );' )
                
                self._c.execute( 'INSERT INTO external_master.tags SELECT * FROM main.tags;' )
                
                self._c.execute( 'DROP TABLE main.tags;' )
                
                self._c.execute( 'DROP TABLE main.tags_fts4;' )
                
                self._c.execute( 'CREATE VIRTUAL TABLE IF NOT EXISTS external_master.tags_fts4 USING fts4( tag );' )
                
                self._c.execute( 'REPLACE INTO tags_fts4 ( docid, tag ) SELECT * FROM tags;' )
                
                #
                
                self._controller.pub( 'splash_set_status_text', 'splitting and compacting mappings tables' )
                
                mapping_petitions_rip = self._c.execute( 'SELECT * FROM mapping_petitions;' ).fetchall()
                
                self._c.execute( 'DROP TABLE mapping_petitions;' )
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS external_mappings.mapping_petitions ( service_id INTEGER, namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, reason_id INTEGER, PRIMARY KEY( service_id, namespace_id, tag_id, hash_id, reason_id ) ) WITHOUT ROWID;' )
                
                self._c.executemany( 'INSERT INTO mapping_petitions VALUES ( ?, ?, ?, ?, ? );', mapping_petitions_rip )
                
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.mapping_petitions_hash_id_index ON mapping_petitions ( hash_id );' )
                
                del mapping_petitions_rip
                
                #
                
                deleted_mappings_rip = self._c.execute( 'SELECT * FROM deleted_mappings;' ).fetchall()
                
                self._c.execute( 'DROP TABLE deleted_mappings;' )
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS external_mappings.deleted_mappings ( service_id INTEGER, namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( service_id, namespace_id, tag_id, hash_id ) ) WITHOUT ROWID;' )
                
                self._c.executemany( 'INSERT INTO deleted_mappings VALUES ( ?, ?, ?, ? );', deleted_mappings_rip )
                
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.deleted_mappings_namespace_id_index ON deleted_mappings ( namespace_id );' )
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.deleted_mappings_tag_id_index ON deleted_mappings ( tag_id );' )
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.deleted_mappings_hash_id_index ON deleted_mappings ( hash_id );' )
                
                del deleted_mappings_rip
                
                #
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS external_mappings.current_mappings ( service_id INTEGER, namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( service_id, namespace_id, tag_id, hash_id ) ) WITHOUT ROWID;' )
                
                self._c.execute( 'INSERT INTO current_mappings SELECT service_id, namespace_id, tag_id, hash_id FROM mappings WHERE status = ?;', ( HC.CURRENT, ) )
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS external_mappings.pending_mappings ( service_id INTEGER, namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( service_id, namespace_id, tag_id, hash_id ) ) WITHOUT ROWID;' )
                
                self._c.execute( 'INSERT INTO pending_mappings SELECT service_id, namespace_id, tag_id, hash_id FROM mappings WHERE status = ?;', ( HC.PENDING, ) )
                
                self._c.execute( 'DROP TABLE mappings;' )
                
                self._controller.pub( 'splash_set_status_text', 'creating mappings indices' )
                
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.current_mappings_namespace_id_index ON current_mappings ( namespace_id );' )
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.current_mappings_tag_id_index ON current_mappings ( tag_id );' )
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.current_mappings_hash_id_index ON current_mappings ( hash_id );' )
                
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.pending_mappings_namespace_id_index ON pending_mappings ( namespace_id );' )
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.pending_mappings_tag_id_index ON pending_mappings ( tag_id );' )
                self._c.execute( 'CREATE INDEX IF NOT EXISTS external_mappings.pending_mappings_hash_id_index ON pending_mappings ( hash_id );' )
                
                #
                
                self._c.execute( 'DELETE FROM service_info;' )
                
                self._c.execute( 'COMMIT;' )
                
                self._CloseDBCursor()
                
                for filename in self._db_filenames.values():
                    
                    self._controller.pub( 'splash_set_status_text', 'vacuuming ' + filename )
                    
                    db_path = os.path.join( self._db_dir, filename )
                    
                    try:
                        
                        if HydrusDB.CanVacuum( db_path ):
                            
                            HydrusDB.VacuumDB( db_path )
                            
                        
                    except Exception as e:
                        
                        HydrusData.Print( 'Vacuum failed!' )
                        HydrusData.PrintException( e )
                        
                    
                
                self._InitDBCursor()
                
                self._c.execute( 'BEGIN IMMEDIATE;' )
                
            
        
        if version == 201:
            
            file_service_ids = self._GetServiceIds( ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ) )
            tag_service_ids = self._GetServiceIds( ( HC.LOCAL_TAG, HC.TAG_REPOSITORY ) )
            
            for ( file_service_id, tag_service_id ) in itertools.product( file_service_ids, tag_service_ids ):
                
                self._controller.pub( 'splash_set_status_text', 'generating specific ac_cache ' + str( file_service_id ) + '_' + str( tag_service_id ) )
                
                # this is a direct copy of the old code, as v204 ditched current_mappings, breaking the call
                # I've flattened all the other subcalls as well, just in case they soon change
                
                suffix = str( file_service_id ) + '_' + str( tag_service_id )
                
                files_table_name = 'external_caches.specific_files_cache_' + suffix
                
                current_mappings_table_name = 'external_caches.specific_current_mappings_cache_' + suffix
                
                pending_mappings_table_name = 'external_caches.specific_pending_mappings_cache_' + suffix
                
                ac_cache_table_name = 'external_caches.specific_ac_cache_' + suffix
                
                self._c.execute( 'CREATE TABLE ' + files_table_name + ' ( hash_id INTEGER PRIMARY KEY );' )
                
                self._c.execute( 'CREATE TABLE ' + current_mappings_table_name + ' ( hash_id INTEGER, namespace_id INTEGER, tag_id INTEGER, PRIMARY KEY( hash_id, namespace_id, tag_id ) ) WITHOUT ROWID;' )
                
                self._c.execute( 'CREATE TABLE ' + pending_mappings_table_name + ' ( hash_id INTEGER, namespace_id INTEGER, tag_id INTEGER, PRIMARY KEY( hash_id, namespace_id, tag_id ) ) WITHOUT ROWID;' )
                
                self._c.execute( 'CREATE TABLE ' + ac_cache_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, current_count INTEGER, pending_count INTEGER, PRIMARY KEY( namespace_id, tag_id ) ) WITHOUT ROWID;' )
                
                #
                
                hash_ids = [ hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id FROM current_files WHERE service_id = ?;', ( file_service_id, ) ) ]
                
                if len( hash_ids ) > 0:
                    
                    self._c.executemany( 'INSERT OR IGNORE INTO ' + files_table_name + ' VALUES ( ? );', ( ( hash_id, ) for hash_id in hash_ids ) )
                    
                    ac_cache_changes = []
                    
                    for group_of_hash_ids in HydrusData.SplitListIntoChunks( hash_ids, 100 ):
                        
                        splayed_group_of_hash_ids = HydrusData.SplayListForDB( group_of_hash_ids )
                        
                        current_mapping_ids_raw = self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM current_mappings WHERE service_id = ? AND hash_id IN ' + splayed_group_of_hash_ids + ';', ( tag_service_id, ) ).fetchall()
                        
                        current_mapping_ids_dict = HydrusData.BuildKeyToSetDict( [ ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in current_mapping_ids_raw ] )
                        
                        pending_mapping_ids_raw = self._c.execute( 'SELECT namespace_id, tag_id, hash_id FROM pending_mappings WHERE service_id = ? AND hash_id IN ' + splayed_group_of_hash_ids + ';', ( tag_service_id, ) ).fetchall()
                        
                        pending_mapping_ids_dict = HydrusData.BuildKeyToSetDict( [ ( ( namespace_id, tag_id ), hash_id ) for ( namespace_id, tag_id, hash_id ) in pending_mapping_ids_raw ] )
                        
                        all_ids_seen = set( current_mapping_ids_dict.keys() )
                        all_ids_seen.update( pending_mapping_ids_dict.keys() )
                        
                        for ( namespace_id, tag_id ) in all_ids_seen:
                            
                            current_hash_ids = current_mapping_ids_dict[ ( namespace_id, tag_id ) ]
                            
                            num_current = len( current_hash_ids )
                            
                            if num_current > 0:
                                
                                self._c.executemany( 'INSERT OR IGNORE INTO ' + current_mappings_table_name + ' ( hash_id, namespace_id, tag_id ) VALUES ( ?, ?, ? );', ( ( hash_id, namespace_id, tag_id ) for hash_id in current_hash_ids ) )
                                
                            
                            pending_hash_ids = pending_mapping_ids_dict[ ( namespace_id, tag_id ) ]
                            
                            num_pending = len( pending_hash_ids )
                            
                            if num_pending > 0:
                                
                                self._c.executemany( 'INSERT OR IGNORE INTO ' + pending_mappings_table_name + ' ( hash_id, namespace_id, tag_id ) VALUES ( ?, ?, ? );', ( ( hash_id, namespace_id, tag_id ) for hash_id in pending_hash_ids ) )
                                
                            
                            if num_current > 0 or num_pending > 0:
                                
                                ac_cache_changes.append( ( namespace_id, tag_id, num_current, num_pending ) )
                                
                            
                        
                    
                    if len( ac_cache_changes ) > 0:
                        
                        self._c.executemany( 'INSERT OR IGNORE INTO ' + ac_cache_table_name + ' ( namespace_id, tag_id, current_count, pending_count ) VALUES ( ?, ?, ?, ? );', ( ( namespace_id, tag_id, 0, 0 ) for ( namespace_id, tag_id, num_current, num_pending ) in ac_cache_changes ) )
                        
                        self._c.executemany( 'UPDATE ' + ac_cache_table_name + ' SET current_count = current_count + ?, pending_count = pending_count + ? WHERE namespace_id = ? AND tag_id = ?;', ( ( num_current, num_pending, namespace_id, tag_id ) for ( namespace_id, tag_id, num_current, num_pending ) in ac_cache_changes ) )
                        
                    
                
            
            for tag_service_id in tag_service_ids:
                
                self._controller.pub( 'splash_set_status_text', 'generating combined files ac_cache ' + str( tag_service_id ) )
                
                # this is a direct copy of the old code, as v204 ditched current_mappings, breaking the call
                # I've flattened all the other subcalls as well, just in case they soon change
                
                ac_cache_table_name = 'external_caches.combined_files_ac_cache_' + str( tag_service_id )
                
                self._c.execute( 'CREATE TABLE ' + ac_cache_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, current_count INTEGER, pending_count INTEGER, PRIMARY KEY( namespace_id, tag_id ) ) WITHOUT ROWID;' )
                
                #
                
                current_mappings_exist = self._c.execute( 'SELECT 1 FROM current_mappings WHERE service_id = ? LIMIT 1;', ( tag_service_id, ) ).fetchone() is not None
                pending_mappings_exist = self._c.execute( 'SELECT 1 FROM pending_mappings WHERE service_id = ? LIMIT 1;', ( tag_service_id, ) ).fetchone() is not None
                
                if current_mappings_exist or pending_mappings_exist:
                    
                    all_known_ids = self._c.execute( 'SELECT namespace_id, tag_id FROM existing_tags;' ).fetchall()
                    
                    for group_of_ids in HydrusData.SplitListIntoChunks( all_known_ids, 10000 ):
                        
                        current_counter = collections.Counter()
                        
                        if current_mappings_exist:
                            
                            for ( namespace_id, tag_id ) in group_of_ids:
                                
                                result = self._c.execute( 'SELECT COUNT( * ) FROM current_mappings WHERE service_id = ? AND namespace_id = ? AND tag_id = ?;', ( tag_service_id, namespace_id, tag_id ) ).fetchone()
                                
                                if result is not None:
                                    
                                    ( count, ) = result
                                    
                                    if count > 0:
                                        
                                        current_counter[ ( namespace_id, tag_id ) ] = count
                                        
                                    
                                
                            
                        
                        #
                        
                        pending_counter = collections.Counter()
                        
                        if pending_mappings_exist:
                            
                            for ( namespace_id, tag_id ) in group_of_ids:
                                
                                result = self._c.execute( 'SELECT COUNT( * ) FROM pending_mappings WHERE service_id = ? AND namespace_id = ? AND tag_id = ?;', ( tag_service_id, namespace_id, tag_id ) ).fetchone()
                                
                                if result is not None:
                                    
                                    ( count, ) = result
                                    
                                    if count > 0:
                                        
                                        pending_counter[ ( namespace_id, tag_id ) ] = count
                                        
                                    
                                
                            
                        
                        all_ids_seen = set( current_counter.keys() )
                        all_ids_seen.update( pending_counter.keys() )
                        
                        count_ids = [ ( namespace_id, tag_id, current_counter[ ( namespace_id, tag_id ) ], pending_counter[ ( namespace_id, tag_id ) ] ) for ( namespace_id, tag_id ) in all_ids_seen ]
                        
                        if len( count_ids ) > 0:
                            
                            self._c.executemany( 'INSERT OR IGNORE INTO ' + ac_cache_table_name + ' ( namespace_id, tag_id, current_count, pending_count ) VALUES ( ?, ?, ?, ? );', ( ( namespace_id, tag_id, 0, 0 ) for ( namespace_id, tag_id, current_delta, pending_delta ) in count_ids ) )
                            
                            self._c.executemany( 'UPDATE ' + ac_cache_table_name + ' SET current_count = current_count + ?, pending_count = pending_count + ? WHERE namespace_id = ? AND tag_id = ?;', ( ( current_delta, pending_delta, namespace_id, tag_id ) for ( namespace_id, tag_id, current_delta, pending_delta ) in count_ids ) )
                            
                            self._c.executemany( 'DELETE FROM ' + ac_cache_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND current_count = ? AND pending_count = ?;', ( ( namespace_id, tag_id, 0, 0 ) for ( namespace_id, tag_id, current_delta, pending_delta ) in count_ids ) )
                            
                        
                    
                
            
            cache_dir = os.path.join( HC.DB_DIR, 'client_cache' )
            
            if os.path.exists( cache_dir ):
                
                try:
                    
                    HydrusPaths.DeletePath( cache_dir )
                    
                except Exception as e:
                    
                    HydrusData.Print( 'Tried to delete the superfluous cache dir, but got an error:' )
                    
                    HydrusData.PrintException( e )
                    
                
            
        
        if version == 202:
            
            self._c.execute( 'DELETE FROM analyze_timestamps;' )
            
        
        if version == 203:
            
            service_ids = self._GetServiceIds( HC.TAG_SERVICES )
            
            for service_id in service_ids:
                
                self._controller.pub( 'splash_set_status_text', 'creating new mappings tables: ' + str( service_id ) )
                
                ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( service_id )
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS ' + current_mappings_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( namespace_id, tag_id, hash_id ) ) WITHOUT ROWID;' )
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS ' + deleted_mappings_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( namespace_id, tag_id, hash_id ) ) WITHOUT ROWID;' )
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS ' + pending_mappings_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, PRIMARY KEY( namespace_id, tag_id, hash_id ) ) WITHOUT ROWID;' )
                
                self._c.execute( 'CREATE TABLE IF NOT EXISTS ' + petitioned_mappings_table_name + ' ( namespace_id INTEGER, tag_id INTEGER, hash_id INTEGER, reason_id INTEGER, PRIMARY KEY( namespace_id, tag_id, hash_id, reason_id ) ) WITHOUT ROWID;' )
                
                #
                
                self._c.execute( 'INSERT OR IGNORE INTO ' + current_mappings_table_name + ' SELECT namespace_id, tag_id, hash_id FROM current_mappings WHERE service_id = ?;', ( service_id, ) )
                self._c.execute( 'INSERT OR IGNORE INTO ' + deleted_mappings_table_name + ' SELECT namespace_id, tag_id, hash_id FROM deleted_mappings WHERE service_id = ?;', ( service_id, ) )
                self._c.execute( 'INSERT OR IGNORE INTO ' + pending_mappings_table_name + ' SELECT namespace_id, tag_id, hash_id FROM pending_mappings WHERE service_id = ?;', ( service_id, ) )
                self._c.execute( 'INSERT OR IGNORE INTO ' + petitioned_mappings_table_name + ' SELECT namespace_id, tag_id, hash_id, reason_id FROM mapping_petitions WHERE service_id = ?;', ( service_id, ) )
                
                #
                
                self._controller.pub( 'splash_set_status_text', 'creating new mappings indices: ' + str( service_id ) )
                
                current_mappings_table_simple_name = current_mappings_table_name.split( '.' )[1]
                deleted_mappings_table_simple_name = deleted_mappings_table_name.split( '.' )[1]
                pending_mappings_table_simple_name = pending_mappings_table_name.split( '.' )[1]
                petitioned_mappings_table_simple_name = petitioned_mappings_table_name.split( '.' )[1]
                
                self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + current_mappings_table_name + '_tag_id_index ON ' + current_mappings_table_simple_name + ' ( tag_id );' )
                self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + current_mappings_table_name + '_hash_id_index ON ' + current_mappings_table_simple_name + ' ( hash_id );' )
                
                self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + deleted_mappings_table_name + '_hash_id_index ON ' + deleted_mappings_table_simple_name + ' ( hash_id );' )
                
                self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + pending_mappings_table_name + '_tag_id_index ON ' + pending_mappings_table_simple_name + ' ( tag_id );' )
                self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + pending_mappings_table_name + '_hash_id_index ON ' + pending_mappings_table_simple_name + ' ( hash_id );' )
                
                self._c.execute( 'CREATE INDEX IF NOT EXISTS ' + petitioned_mappings_table_name + '_hash_id_index ON ' + petitioned_mappings_table_simple_name + ' ( hash_id );' )
                
            
            self._c.execute( 'DROP TABLE current_mappings;' )
            self._c.execute( 'DROP TABLE pending_mappings;' )
            self._c.execute( 'DROP TABLE deleted_mappings;' )
            self._c.execute( 'DROP TABLE mapping_petitions;' )
            
            self._controller.pub( 'splash_set_status_text', 'analyzing new tables' )
            
            self._Analyze()
            
            self._c.execute( 'COMMIT;' )
            
            self._CloseDBCursor()
            
            for filename in self._db_filenames.values():
                
                self._controller.pub( 'splash_set_status_text', 'vacuuming ' + filename )
                
                db_path = os.path.join( self._db_dir, filename )
                
                try:
                    
                    if HydrusDB.CanVacuum( db_path ):
                        
                        HydrusDB.VacuumDB( db_path )
                        
                    
                except Exception as e:
                    
                    HydrusData.Print( 'Vacuum failed!' )
                    HydrusData.PrintException( e )
                    
                
            
            self._InitDBCursor()
            
            self._c.execute( 'BEGIN IMMEDIATE;' )
            
        
        if version == 204:
            
            self._c.execute( 'DROP TABLE shutdown_timestamps;' )
            
            self._c.execute( 'CREATE TABLE vacuum_timestamps ( name TEXT, timestamp INTEGER );' )
            
        
        if version == 205:
            
            self._c.execute( 'CREATE TABLE service_directories ( service_id INTEGER REFERENCES services ON DELETE CASCADE, directory_id INTEGER, num_files INTEGER, total_size INTEGER, PRIMARY KEY( service_id, directory_id ) );' )
            self._c.execute( 'CREATE TABLE service_directory_file_map ( service_id INTEGER REFERENCES services ON DELETE CASCADE, directory_id INTEGER, hash_id INTEGER, PRIMARY KEY( service_id, directory_id, hash_id ) );' )
            
            #
            
            self._c.execute( 'CREATE TABLE IF NOT EXISTS external_master.texts ( text_id INTEGER PRIMARY KEY, text TEXT UNIQUE );' )
            
            #
            
            self._c.execute( 'INSERT OR IGNORE INTO texts SELECT reason_id, reason FROM reasons;' )
            
            self._c.execute( 'DROP TABLE reasons;' )
            
        
        self._controller.pub( 'splash_set_title_text', 'updated db to v' + str( version + 1 ) )
        
        self._c.execute( 'UPDATE version SET version = ?;', ( version + 1, ) )
        
        HydrusGlobals.is_db_updated = True
        
    
    def _UpdateImageboards( self, site_edit_log ):
        
        for ( site_action, site_data ) in site_edit_log:
            
            if site_action == HC.ADD:
                
                site_name = site_data
                
                self._GetSiteId( site_name )
                
            elif site_action == HC.DELETE:
                
                site_name = site_data
                
                site_id = self._GetSiteId( site_name )
                
                self._c.execute( 'DELETE FROM imageboard_sites WHERE site_id = ?;', ( site_id, ) )
                self._c.execute( 'DELETE FROM imageboards WHERE site_id = ?;', ( site_id, ) )
                
            elif site_action == HC.EDIT:
                
                ( site_name, edit_log ) = site_data
                
                site_id = self._GetSiteId( site_name )
                
                for ( action, data ) in edit_log:
                    
                    if action == HC.ADD:
                        
                        name = data
                        
                        imageboard = ClientData.Imageboard( name, '', 60, [], {} )
                        
                        self._c.execute( 'INSERT INTO imageboards ( site_id, name, imageboard ) VALUES ( ?, ?, ? );', ( site_id, name, imageboard ) )
                        
                    elif action == HC.DELETE:
                        
                        name = data
                        
                        self._c.execute( 'DELETE FROM imageboards WHERE site_id = ? AND name = ?;', ( site_id, name ) )
                        
                    elif action == HC.EDIT:
                        
                        imageboard = data
                        
                        name = imageboard.GetName()
                        
                        self._c.execute( 'UPDATE imageboards SET imageboard = ? WHERE site_id = ? AND name = ?;', ( imageboard, site_id, name ) )
                        
                    
                
            
        
    
    def _UpdateMappings( self, tag_service_id, mappings_ids = None, deleted_mappings_ids = None, pending_mappings_ids = None, pending_rescinded_mappings_ids = None, petitioned_mappings_ids = None, petitioned_rescinded_mappings_ids = None ):
        
        ( current_mappings_table_name, deleted_mappings_table_name, pending_mappings_table_name, petitioned_mappings_table_name ) = GenerateMappingsTableNames( tag_service_id )
        
        if mappings_ids is None: mappings_ids = []
        if deleted_mappings_ids is None: deleted_mappings_ids = []
        if pending_mappings_ids is None: pending_mappings_ids = []
        if pending_rescinded_mappings_ids is None: pending_rescinded_mappings_ids = []
        if petitioned_mappings_ids is None: petitioned_mappings_ids = []
        if petitioned_rescinded_mappings_ids is None: petitioned_rescinded_mappings_ids = []
        
        file_service_ids = self._GetServiceIds( ( HC.LOCAL_FILE, HC.FILE_REPOSITORY ) )
        
        # this method grew into a monster that merged deleted, pending and current according to a heirarchy of services
        # this cost a lot of CPU time and was extremely difficult to maintain
        # now it attempts a simpler union, not letting delete overwrite a current or pending
        
        other_service_ids = [ service_id for service_id in self._GetServiceIds( HC.TAG_SERVICES ) if service_id != tag_service_id ]
        
        splayed_other_service_ids = HydrusData.SplayListForDB( other_service_ids )
        
        change_in_num_mappings = 0
        change_in_num_deleted_mappings = 0
        change_in_num_pending_mappings = 0
        change_in_num_petitioned_mappings = 0
        change_in_num_tags = 0
        change_in_num_files = 0
        
        all_adds = mappings_ids + pending_mappings_ids
        
        tag_ids_being_added = { tag_id for ( namespace_id, tag_id, hash_ids ) in all_adds }
        
        hash_ids_lists = [ hash_ids for ( namespace_id, tag_id, hash_ids ) in all_adds ]
        hash_ids_being_added = { hash_id for hash_id in itertools.chain.from_iterable( hash_ids_lists ) }
        
        all_removes = deleted_mappings_ids + pending_rescinded_mappings_ids
        
        tag_ids_being_removed = { tag_id for ( namespace_id, tag_id, hash_ids ) in all_removes }
        
        hash_ids_lists = [ hash_ids for ( namespace_id, tag_id, hash_ids ) in all_removes ]
        hash_ids_being_removed = { hash_id for hash_id in itertools.chain.from_iterable( hash_ids_lists ) }
        
        tag_ids_to_search_for = tag_ids_being_added.union( tag_ids_being_removed )
        hash_ids_to_search_for = hash_ids_being_added.union( hash_ids_being_removed )
        
        self._c.execute( 'CREATE TABLE mem.temp_tag_ids ( tag_id INTEGER );' )
        self._c.execute( 'CREATE TABLE mem.temp_hash_ids ( hash_id INTEGER );' )
        
        self._c.executemany( 'INSERT INTO temp_tag_ids ( tag_id ) VALUES ( ? );', ( ( tag_id, ) for tag_id in tag_ids_to_search_for ) )
        self._c.executemany( 'INSERT INTO temp_hash_ids ( hash_id ) VALUES ( ? );', ( ( hash_id, ) for hash_id in hash_ids_to_search_for ) )
        
        pre_existing_tag_ids = { tag_id for ( tag_id, ) in self._c.execute( 'SELECT tag_id as t FROM temp_tag_ids WHERE EXISTS ( SELECT 1 FROM ' + current_mappings_table_name + ' WHERE tag_id = t );' ) }
        pre_existing_hash_ids = { hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id as h FROM temp_hash_ids WHERE EXISTS ( SELECT 1 FROM ' + current_mappings_table_name + ' WHERE hash_id = h );' ) }
        
        num_tags_added = len( tag_ids_being_added.difference( pre_existing_tag_ids ) )
        num_files_added = len( hash_ids_being_added.difference( pre_existing_hash_ids ) )
        
        change_in_num_tags += num_tags_added
        change_in_num_files += num_files_added
        
        combined_files_current_counter = collections.Counter()
        combined_files_pending_counter = collections.Counter()
        
        if len( mappings_ids ) > 0:
            
            for ( namespace_id, tag_id, hash_ids ) in mappings_ids:
                
                splayed_hash_ids = HydrusData.SplayListForDB( hash_ids )
                
                self._c.execute( 'DELETE FROM ' + deleted_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND hash_id IN ' + splayed_hash_ids + ';', ( namespace_id, tag_id ) )
                
                num_deleted_deleted = self._GetRowCount()
                
                self._c.execute( 'DELETE FROM ' + pending_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND hash_id IN ' + splayed_hash_ids + ';', ( namespace_id, tag_id ) )
                
                num_pending_deleted = self._GetRowCount()
                
                self._c.executemany( 'INSERT OR IGNORE INTO ' + current_mappings_table_name + ' VALUES ( ?, ?, ? );', [ ( namespace_id, tag_id, hash_id ) for hash_id in hash_ids ] )
                
                num_current_inserted = self._GetRowCount()
                
                change_in_num_deleted_mappings -= num_deleted_deleted
                change_in_num_pending_mappings -= num_pending_deleted
                change_in_num_mappings += num_current_inserted
                
                combined_files_pending_counter[ ( namespace_id, tag_id ) ] -= num_pending_deleted
                combined_files_current_counter[ ( namespace_id, tag_id ) ] += num_current_inserted
                
            
            for file_service_id in file_service_ids:
                
                self._CacheSpecificMappingsAddMappings( file_service_id, tag_service_id, mappings_ids )
                
            
        
        if len( deleted_mappings_ids ) > 0:
            
            for ( namespace_id, tag_id, hash_ids ) in deleted_mappings_ids:
                
                splayed_hash_ids = HydrusData.SplayListForDB( hash_ids )
                
                self._c.execute( 'DELETE FROM ' + current_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND hash_id IN ' + splayed_hash_ids + ';', ( namespace_id, tag_id ) )
                
                num_current_deleted = self._GetRowCount()
                
                self._c.execute( 'DELETE FROM ' + petitioned_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND hash_id IN ' + splayed_hash_ids + ';', ( namespace_id, tag_id ) )
                
                num_petitions_deleted = self._GetRowCount()
                
                self._c.executemany( 'INSERT OR IGNORE INTO ' + deleted_mappings_table_name + ' VALUES ( ?, ?, ? );', [ ( namespace_id, tag_id, hash_id ) for hash_id in hash_ids ] )
                
                num_deleted_inserted = self._GetRowCount()
                
                change_in_num_mappings -= num_current_deleted
                change_in_num_petitioned_mappings -= num_petitions_deleted
                change_in_num_deleted_mappings += num_deleted_inserted
                
                combined_files_current_counter[ ( namespace_id, tag_id ) ] -= num_current_deleted
                
            
            for file_service_id in file_service_ids:
                
                self._CacheSpecificMappingsDeleteMappings( file_service_id, tag_service_id, deleted_mappings_ids )
                
            
        
        if len( pending_mappings_ids ) > 0:
            
            for ( namespace_id, tag_id, hash_ids ) in pending_mappings_ids:
                
                self._c.executemany( 'INSERT OR IGNORE INTO ' + pending_mappings_table_name + ' VALUES ( ?, ?, ? );', [ ( namespace_id, tag_id, hash_id ) for hash_id in hash_ids ] )
                
                num_pending_inserted = self._GetRowCount()
                
                change_in_num_pending_mappings += num_pending_inserted
                
                combined_files_pending_counter[ ( namespace_id, tag_id ) ] += num_pending_inserted
                
            
            for file_service_id in file_service_ids:
                
                self._CacheSpecificMappingsPendMappings( file_service_id, tag_service_id, pending_mappings_ids )
                
            
        
        if len( pending_rescinded_mappings_ids ) > 0:
            
            for ( namespace_id, tag_id, hash_ids ) in pending_rescinded_mappings_ids:
                
                self._c.execute( 'DELETE FROM ' + pending_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';', ( namespace_id, tag_id ) )
                
                num_pending_deleted = self._GetRowCount()
                
                change_in_num_pending_mappings -= num_pending_deleted
                
                combined_files_pending_counter[ ( namespace_id, tag_id ) ] -= num_pending_deleted
                
            
            for file_service_id in file_service_ids:
                
                self._CacheSpecificMappingsRescindPendingMappings( file_service_id, tag_service_id, pending_rescinded_mappings_ids )
                
            
        
        combined_files_seen_ids = set( ( key for ( key, value ) in combined_files_current_counter.items() if value != 0 ) )
        combined_files_seen_ids.update( ( key for ( key, value ) in combined_files_pending_counter.items() if value != 0 ) )
        
        combined_files_counts = [ ( namespace_id, tag_id, combined_files_current_counter[ ( namespace_id, tag_id ) ], combined_files_pending_counter[ ( namespace_id, tag_id ) ] ) for ( namespace_id, tag_id ) in combined_files_seen_ids ]
        
        self._CacheCombinedFilesMappingsUpdate( tag_service_id, combined_files_counts )
        
        # 
        
        post_existing_tag_ids = { tag_id for ( tag_id, ) in self._c.execute( 'SELECT tag_id as t FROM temp_tag_ids WHERE EXISTS ( SELECT 1 FROM ' + current_mappings_table_name + ' WHERE tag_id = t );' ) }
        post_existing_hash_ids = { hash_id for ( hash_id, ) in self._c.execute( 'SELECT hash_id as h FROM temp_hash_ids WHERE EXISTS ( SELECT 1 FROM ' + current_mappings_table_name + ' WHERE hash_id = h );' ) }
        
        self._c.execute( 'DROP TABLE temp_tag_ids;' )
        self._c.execute( 'DROP TABLE temp_hash_ids;' )
        
        num_tags_removed = len( pre_existing_tag_ids.intersection( tag_ids_being_removed ).difference( post_existing_tag_ids ) )
        num_files_removed = len( pre_existing_hash_ids.intersection( hash_ids_being_removed ).difference( post_existing_hash_ids ) )
        
        change_in_num_tags -= num_tags_removed
        change_in_num_files -= num_files_removed
        
        for ( namespace_id, tag_id, hash_ids, reason_id ) in petitioned_mappings_ids:
            
            self._c.executemany( 'INSERT OR IGNORE INTO ' + petitioned_mappings_table_name + ' VALUES ( ?, ?, ?, ? );', [ ( namespace_id, tag_id, hash_id, reason_id ) for hash_id in hash_ids ] )
            
            num_petitions_inserted = self._GetRowCount()
            
            change_in_num_petitioned_mappings += num_petitions_inserted
            
        
        for ( namespace_id, tag_id, hash_ids ) in petitioned_rescinded_mappings_ids:
            
            self._c.execute( 'DELETE FROM ' + petitioned_mappings_table_name + ' WHERE namespace_id = ? AND tag_id = ? AND hash_id IN ' + HydrusData.SplayListForDB( hash_ids ) + ';', ( namespace_id, tag_id ) )
            
            num_petitions_deleted = self._GetRowCount()
            
            change_in_num_petitioned_mappings -= num_petitions_deleted
            
        
        service_info_updates = []
        
        if change_in_num_mappings != 0: service_info_updates.append( ( change_in_num_mappings, tag_service_id, HC.SERVICE_INFO_NUM_MAPPINGS ) )
        if change_in_num_deleted_mappings != 0: service_info_updates.append( ( change_in_num_deleted_mappings, tag_service_id, HC.SERVICE_INFO_NUM_DELETED_MAPPINGS ) )
        if change_in_num_pending_mappings != 0: service_info_updates.append( ( change_in_num_pending_mappings, tag_service_id, HC.SERVICE_INFO_NUM_PENDING_MAPPINGS ) )
        if change_in_num_petitioned_mappings != 0: service_info_updates.append( ( change_in_num_petitioned_mappings, tag_service_id, HC.SERVICE_INFO_NUM_PETITIONED_MAPPINGS ) )
        if change_in_num_tags != 0: service_info_updates.append( ( change_in_num_tags, tag_service_id, HC.SERVICE_INFO_NUM_TAGS ) )
        if change_in_num_files != 0: service_info_updates.append( ( change_in_num_files, tag_service_id, HC.SERVICE_INFO_NUM_FILES ) )
        
        if len( service_info_updates ) > 0: self._c.executemany( 'UPDATE service_info SET info = info + ? WHERE service_id = ? AND info_type = ?;', service_info_updates )
        
    
    def _UpdateServerServices( self, admin_service_key, original_services_info, edit_log, service_keys_to_access_keys ):
        
        self._c.execute( 'COMMIT;' )
        
        if not self._fast_big_transaction_wal:
            
            self._c.execute( 'PRAGMA journal_mode = TRUNCATE;' )
            
        
        self._c.execute( 'PRAGMA foreign_keys = ON;' )
        
        self._c.execute( 'BEGIN IMMEDIATE;' )
        
        self.pub_after_commit( 'notify_new_services_data' )
        self.pub_after_commit( 'notify_new_services_gui' )
        
        admin_service_id = self._GetServiceId( admin_service_key )
        
        admin_service = self._GetService( admin_service_id )
        
        admin_info = admin_service.GetInfo()
        
        host = admin_info[ 'host' ]
        
        #
        
        server_service_keys_to_client_service_info = {}
        
        current_client_services_info = self._c.execute( 'SELECT service_key, service_type, info FROM services;' ).fetchall()
        
        for ( server_service_key, service_type, server_options ) in original_services_info:
            
            server_port = server_options[ 'port' ]
            
            for ( client_service_key, service_type, client_info ) in current_client_services_info:
                
                if 'host' in client_info and 'port' in client_info:
                    
                    if client_info[ 'host' ] == host and client_info[ 'port' ] == server_port:
                        
                        server_service_keys_to_client_service_info[ server_service_key ] = ( client_service_key, service_type, client_info )
                        
                    
                
            
        
        #
        
        for ( action, data ) in edit_log:
            
            if action == HC.ADD:
                
                ( service_key, service_type, server_options ) = data
                
                info = {}
                
                info[ 'host' ] = host
                info[ 'port' ] = server_options[ 'port' ]
                info[ 'access_key' ] = service_keys_to_access_keys[ service_key ]
                
                name = HC.service_string_lookup[ service_type ] + ' at ' + host + ':' + str( info[ 'port' ] )
                
                self._AddService( service_key, service_type, name, info )
                
            elif action == HC.DELETE:
                
                server_service_key = data
                
                if server_service_key in server_service_keys_to_client_service_info:
                    
                    ( client_service_key, service_type, client_info ) = server_service_keys_to_client_service_info[ server_service_key ]
                    
                    service_id = self._GetServiceId( client_service_key )
                    
                    self._DeleteService( service_id )
                    
                
            elif action == HC.EDIT:
                
                ( server_service_key, service_type, server_options ) = data
                
                if server_service_key in server_service_keys_to_client_service_info:
                    
                    ( client_service_key, service_type, client_info ) = server_service_keys_to_client_service_info[ server_service_key ]
                    
                    service_id = self._GetServiceId( client_service_key )
                    
                    client_info[ 'port' ] = server_options[ 'port' ]
                    
                    self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( client_info, service_id ) )
                    
                
            
        
        self.pub_after_commit( 'notify_new_pending' )
        
        self._c.execute( 'COMMIT;' )
        
        self._InitDBCursor()
        
        self._c.execute( 'BEGIN IMMEDIATE;' )
        
    
    def _UpdateServices( self, edit_log ):
        
        self._c.execute( 'COMMIT;' )
        
        if not self._fast_big_transaction_wal:
            
            self._c.execute( 'PRAGMA journal_mode = TRUNCATE;' )
            
        
        self._c.execute( 'PRAGMA foreign_keys = ON;' )
        
        self._c.execute( 'BEGIN IMMEDIATE;' )
        
        self.pub_after_commit( 'notify_new_services_data' )
        self.pub_after_commit( 'notify_new_services_gui' )
        
        for entry in edit_log:
            
            action = entry.GetAction()
            
            if action == HC.ADD:
                
                ( service_key, service_type, name, info ) = entry.GetData()
                
                self._AddService( service_key, service_type, name, info )
                
            elif action == HC.DELETE:
                
                service_key = entry.GetIdentifier()
                
                service_id = self._GetServiceId( service_key )
                
                self._DeleteService( service_id )
                
            elif action == HC.EDIT:
                
                ( service_key, service_type, new_name, info_update ) = entry.GetData()
                
                service_id = self._GetServiceId( service_key )
                
                self._c.execute( 'UPDATE services SET name = ? WHERE service_id = ?;', ( new_name, service_id ) )
                
                if service_type in HC.RESTRICTED_SERVICES:
                    
                    account = HydrusData.GetUnknownAccount()
                    
                    account.MakeStale()
                    
                    info_update[ 'account' ] = account
                    
                    self.pub_after_commit( 'permissions_are_stale' )
                    
                    session_manager = HydrusGlobals.client_controller.GetClientSessionManager()
                    
                    session_manager.DeleteSessionKey( service_key )
                    
                
                if service_type in HC.TAG_SERVICES:
                    
                    ( old_info, ) = self._c.execute( 'SELECT info FROM services WHERE service_id = ?;', ( service_id, ) ).fetchone()
                    
                    old_tag_archive_sync = old_info[ 'tag_archive_sync' ]
                    new_tag_archive_sync = info_update[ 'tag_archive_sync' ]
                    
                    for archive_name in new_tag_archive_sync.keys():
                        
                        namespaces = set( new_tag_archive_sync[ archive_name ] )
                        
                        if archive_name in old_tag_archive_sync:
                            
                            old_namespaces = old_tag_archive_sync[ archive_name ]
                            
                            namespaces.difference_update( old_namespaces )
                            
                            if len( namespaces ) == 0:
                                
                                continue
                                
                            
                        
                        ( hta_path, hta ) = self._tag_archives[ archive_name ]
                        
                        file_service_key = CC.LOCAL_FILE_SERVICE_KEY
                        
                        adding = True
                        
                        self._controller.pub( 'sync_to_tag_archive', hta_path, service_key, file_service_key, adding, namespaces )
                        
                    
                
                self._UpdateServiceInfo( service_id, info_update )
                
                if service_id in self._service_cache: del self._service_cache[ service_id ]
                
                if service_type == HC.LOCAL_BOORU:
                    
                    self.pub_after_commit( 'restart_booru' )
                    self.pub_after_commit( 'notify_new_upnp_mappings' )
                    
                
            
        
        self.pub_after_commit( 'notify_new_pending' )
        
        self._c.execute( 'COMMIT;' )
        
        self._InitDBCursor()
        
        self._c.execute( 'BEGIN IMMEDIATE;' )
        
    
    def _UpdateServiceInfo( self, service_id, update ):
        
        ( info, ) = self._c.execute( 'SELECT info FROM services WHERE service_id = ?;', ( service_id, ) ).fetchone()
        
        for ( k, v ) in update.items(): info[ k ] = v
        
        self._c.execute( 'UPDATE services SET info = ? WHERE service_id = ?;', ( info, service_id ) )
        
    
    def _Vacuum( self, stop_time = None, force_vacuum = False ):
        
        stale_time_delta = HC.options[ 'maintenance_vacuum_period' ]
        
        if stale_time_delta is None:
            
            return
            
        
        existing_names_to_timestamps = dict( self._c.execute( 'SELECT name, timestamp FROM vacuum_timestamps;' ).fetchall() )
        
        db_names = [ name for ( index, name, path ) in self._c.execute( 'PRAGMA database_list;' ) if name not in ( 'mem', 'temp' ) ]
        
        if force_vacuum:
            
            due_names = db_names
            
        else:
            
            due_names = [ name for name in db_names if name not in existing_names_to_timestamps or HydrusData.TimeHasPassed( existing_names_to_timestamps[ name ] + stale_time_delta ) ]
            
        
        if len( due_names ) > 0:
            
            self._c.execute( 'COMMIT;' )
            
            job_key = ClientThreading.JobKey()
            
            job_key.SetVariable( 'popup_title', 'database maintenance - vacuum' )
            
            self._controller.pub( 'message', job_key )
            
            self._CloseDBCursor()
            
            time.sleep( 1 )
            
            names_done = []
            
            for name in due_names:
                
                self._controller.pub( 'splash_set_status_text', 'vacuuming ' + name )
                job_key.SetVariable( 'popup_text_1', 'vacuuming ' + name )
                
                try:
                    
                    db_path = os.path.join( self._db_dir, self._db_filenames[ name ] )
                    
                    if HydrusDB.CanVacuum( db_path, stop_time = stop_time ):
                        
                        started = HydrusData.GetNowPrecise()
                        
                        HydrusDB.VacuumDB( db_path )
                        
                        time_took = HydrusData.GetNowPrecise() - started
                        
                        HydrusData.Print( 'Vacuumed ' + db_path + ' in ' + HydrusData.ConvertTimeDeltaToPrettyString( time_took ) )
                        
                        names_done.append( name )
                        
                    
                except Exception as e:
                    
                    HydrusData.Print( 'vacuum failed:' )
                    
                    HydrusData.ShowException( e )
                    
                    size = os.path.getsize( db_path )
                    
                    pretty_size = HydrusData.ConvertIntToBytes( size )
                    
                    text = 'An attempt to vacuum the database failed.'
                    text += os.linesep * 2
                    text += 'For now, automatic vacuuming has been disabled. If the error is not obvious, please contact the hydrus developer.'
                    
                    HydrusData.ShowText( text )
                    
                    self._InitDBCursor()
                    
                    self._c.execute( 'BEGIN IMMEDIATE;' )
                    
                    HC.options[ 'maintenance_vacuum_period' ] = None
                    
                    self._SaveOptions( HC.options )
                    
                    return
                    
                
            
            job_key.SetVariable( 'popup_text_1', 'cleaning up' )
            
            self._InitDBCursor()
            
            self._c.execute( 'BEGIN IMMEDIATE;' )
            
            self._c.executemany( 'DELETE FROM vacuum_timestamps WHERE name = ?;', ( ( name, ) for name in names_done ) )
            
            self._c.executemany( 'INSERT OR IGNORE INTO vacuum_timestamps ( name, timestamp ) VALUES ( ?, ? );', ( ( name, HydrusData.GetNow() ) for name in names_done ) )
            
            job_key.SetVariable( 'popup_text_1', 'done!' )
            
            wx.CallLater( 1000 * 30, job_key.Delete )
            
        
    
    def _Write( self, action, *args, **kwargs ):
        
        if action == 'analyze': result = self._Analyze( *args, **kwargs )
        elif action == 'backup': result = self._Backup( *args, **kwargs )
        elif action == 'clear_orphans': result = self._ClearOrphans( *args, **kwargs )
        elif action == 'content_update_package':result = self._ProcessContentUpdatePackage( *args, **kwargs )
        elif action == 'content_updates':result = self._ProcessContentUpdates( *args, **kwargs )
        elif action == 'copy_files': result = self._CopyFiles( *args, **kwargs )
        elif action == 'db_integrity': result = self._CheckDBIntegrity( *args, **kwargs )
        elif action == 'delete_hydrus_session_key': result = self._DeleteHydrusSessionKey( *args, **kwargs )
        elif action == 'delete_imageboard': result = self._DeleteYAMLDump( YAML_DUMP_ID_IMAGEBOARD, *args, **kwargs )
        elif action == 'delete_local_booru_share': result = self._DeleteYAMLDump( YAML_DUMP_ID_LOCAL_BOORU, *args, **kwargs )
        elif action == 'delete_pending': result = self._DeletePending( *args, **kwargs )
        elif action == 'delete_remote_booru': result = self._DeleteYAMLDump( YAML_DUMP_ID_REMOTE_BOORU, *args, **kwargs )
        elif action == 'delete_serialisable_named': result = self._DeleteJSONDumpNamed( *args, **kwargs )
        elif action == 'delete_service_info': result = self._DeleteServiceInfo( *args, **kwargs )
        elif action == 'export_mappings': result = self._ExportToTagArchive( *args, **kwargs )
        elif action == 'file_integrity': result = self._CheckFileIntegrity( *args, **kwargs )
        elif action == 'hydrus_session': result = self._AddHydrusSession( *args, **kwargs )
        elif action == 'imageboard': result = self._SetYAMLDump( YAML_DUMP_ID_IMAGEBOARD, *args, **kwargs )
        elif action == 'import_file': result = self._ImportFile( *args, **kwargs )
        elif action == 'local_booru_share': result = self._SetYAMLDump( YAML_DUMP_ID_LOCAL_BOORU, *args, **kwargs )
        elif action == 'regenerate_ac_cache': result = self._RegenerateACCache( *args, **kwargs )        
        elif action == 'relocate_client_files': result = self._RelocateClientFiles( *args, **kwargs )
        elif action == 'remote_booru': result = self._SetYAMLDump( YAML_DUMP_ID_REMOTE_BOORU, *args, **kwargs )
        elif action == 'reset_service': result = self._ResetService( *args, **kwargs )
        elif action == 'save_options': result = self._SaveOptions( *args, **kwargs )
        elif action == 'serialisable_simple': result = self._SetJSONSimple( *args, **kwargs )
        elif action == 'serialisable': result = self._SetJSONDump( *args, **kwargs )
        elif action == 'service_updates': result = self._ProcessServiceUpdates( *args, **kwargs )
        elif action == 'set_password': result = self._SetPassword( *args, **kwargs )
        elif action == 'sync_hashes_to_tag_archive': result = self._SyncHashesToTagArchive( *args, **kwargs )
        elif action == 'tag_censorship': result = self._SetTagCensorship( *args, **kwargs )
        elif action == 'thumbnails': result = self._AddThumbnails( *args, **kwargs )
        elif action == 'update_server_services': result = self._UpdateServerServices( *args, **kwargs )
        elif action == 'update_services': result = self._UpdateServices( *args, **kwargs )
        elif action == 'vacuum': result = self._Vacuum( *args, **kwargs )
        elif action == 'web_session': result = self._AddWebSession( *args, **kwargs )
        else: raise Exception( 'db received an unknown write command: ' + action )
        
        return result
        
    
    def pub_content_updates_after_commit( self, service_keys_to_content_updates ):
        
        self.pub_after_commit( 'content_updates_data', service_keys_to_content_updates )
        self.pub_after_commit( 'content_updates_gui', service_keys_to_content_updates )
        
    
    def pub_service_updates_after_commit( self, service_keys_to_service_updates ):
        
        self.pub_after_commit( 'service_updates_data', service_keys_to_service_updates )
        self.pub_after_commit( 'service_updates_gui', service_keys_to_service_updates )
        
    
    def RestoreBackup( self, path ):
        
        for filename in self._db_filenames.values():
            
            source = os.path.join( path, filename )
            dest = os.path.join( self._db_dir, filename )
            
            if not HydrusPaths.PathsHaveSameSizeAndDate( source, dest ):
                
                shutil.copy2( source, dest )
                
            
        
        HydrusPaths.MirrorTree( os.path.join( path, 'client_archives' ), HC.CLIENT_ARCHIVES_DIR )
        HydrusPaths.MirrorTree( os.path.join( path, 'client_files' ), HC.CLIENT_FILES_DIR )
        HydrusPaths.MirrorTree( os.path.join( path, 'client_thumbnails' ), HC.CLIENT_THUMBNAILS_DIR )
        HydrusPaths.MirrorTree( os.path.join( path, 'client_updates' ), HC.CLIENT_UPDATES_DIR )
        
    