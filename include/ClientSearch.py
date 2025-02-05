import ClientConstants as CC
import ClientData
import HydrusConstants as HC
import HydrusData
import HydrusGlobals
import HydrusSerialisable
import HydrusTags
import re
import wx

def FilterPredicatesBySearchEntry( search_entry, predicates ):
    
    tags_to_predicates = {}
    
    for predicate in predicates:
        
        ( predicate_type, value, inclusive ) = predicate.GetInfo()
        
        if predicate_type == HC.PREDICATE_TYPE_TAG:
            
            tags_to_predicates[ value ] = predicate
            
        
    
    matching_tags = FilterTagsBySearchEntry( search_entry, tags_to_predicates.keys() )
    
    matches = [ tags_to_predicates[ tag ] for tag in matching_tags ]
    
    return matches
    
def FilterTagsBySearchEntry( search_entry, tags, search_siblings = True ):
    
    def compile_re( s ):
        
        regular_parts_of_s = s.split( '*' )
        
        escaped_parts_of_s = [ re.escape( part ) for part in regular_parts_of_s ]
        
        s = '.*'.join( escaped_parts_of_s )
        
        return re.compile( '(\\A|\\s)' + s + '(\\s|\\Z)', flags = re.UNICODE )
        
    
    if ':' in search_entry:
        
        search_namespace = True
        
        ( namespace_entry, search_entry ) = search_entry.split( ':', 1 )
        
        namespace_re_predicate = compile_re( namespace_entry )
        
    else:
        
        search_namespace = False
        
    
    if '*' not in search_entry: search_entry += '*'
    
    re_predicate = compile_re( search_entry )
    
    sibling_manager = HydrusGlobals.client_controller.GetManager( 'tag_siblings' )
    
    result = []
    
    for tag in tags:
        
        if search_siblings:
            
            possible_tags = sibling_manager.GetAllSiblings( tag )
            
        else:
            
            possible_tags = [ tag ]
            
        
        for possible_tag in possible_tags:
            
            if ':' in possible_tag:
                
                ( n, t ) = possible_tag.split( ':', 1 )
                
                if search_namespace and re.search( namespace_re_predicate, n ) is None:
                    
                    continue
                    
                
                comparee = t
                
            else:
                
                if search_namespace:
                    
                    continue
                    
                
                comparee = possible_tag
                
            
            if re.search( re_predicate, comparee ) is not None:
                
                result.append( tag )
                
                break
                
            
        
    
    return result
    
def SortPredicates( predicates ):
    
    def cmp_func( x, y ): return cmp( x.GetCount(), y.GetCount() )
    
    predicates.sort( cmp = cmp_func, reverse = True )
    
    return predicates

class FileQueryResult( object ):
    
    def __init__( self, media_results ):
        
        self._hashes_to_media_results = { media_result.GetHash() : media_result for media_result in media_results }
        self._hashes_ordered = [ media_result.GetHash() for media_result in media_results ]
        self._hashes = set( self._hashes_ordered )
        
        HydrusGlobals.client_controller.sub( self, 'ProcessContentUpdates', 'content_updates_data' )
        HydrusGlobals.client_controller.sub( self, 'ProcessServiceUpdates', 'service_updates_data' )
        
    
    def __iter__( self ):
        
        for hash in self._hashes_ordered:
            
            yield self._hashes_to_media_results[ hash ]
            
        
    
    def __len__( self ): return len( self._hashes_ordered )
    
    def _Remove( self, hashes ):
        
        for hash in hashes:
            
            if hash in self._hashes_to_media_results:
                
                del self._hashes_to_media_results[ hash ]
                
                self._hashes_ordered.remove( hash )
                
            
        
        self._hashes.difference_update( hashes )
        
    
    def AddMediaResults( self, media_results ):
        
        for media_result in media_results:
            
            hash = media_result.GetHash()
            
            if hash in self._hashes:
                
                continue
                
            
            self._hashes_to_media_results[ hash ] = media_result
            
            self._hashes_ordered.append( hash )
            
            self._hashes.add( hash )
            
        
    
    def GetHashes( self ): return self._hashes
    
    def GetMediaResult( self, hash ): return self._hashes_to_media_results[ hash ]
    
    def GetMediaResults( self ): return [ self._hashes_to_media_results[ hash ] for hash in self._hashes_ordered ]
    
    def ProcessContentUpdates( self, service_keys_to_content_updates ):
        
        for ( service_key, content_updates ) in service_keys_to_content_updates.items():
            
            for content_update in content_updates:
                
                hashes = content_update.GetHashes()
                
                if len( hashes ) > 0:
                    
                    for hash in self._hashes.intersection( hashes ):
                        
                        media_result = self._hashes_to_media_results[ hash ]
                        
                        media_result.ProcessContentUpdate( service_key, content_update )
                        
                    
                
            
        
    
    def ProcessServiceUpdates( self, service_keys_to_service_updates ):
        
        for ( service_key, service_updates ) in service_keys_to_service_updates.items():
            
            for service_update in service_updates:
                
                ( action, row ) = service_update.ToTuple()
                
                if action == HC.SERVICE_UPDATE_DELETE_PENDING:
                    
                    for media_result in self._hashes_to_media_results.values(): media_result.DeletePending( service_key )
                    
                elif action == HC.SERVICE_UPDATE_RESET:
                    
                    for media_result in self._hashes_to_media_results.values(): media_result.ResetService( service_key )
                    
                
            
        
    
class FileSearchContext( HydrusSerialisable.SerialisableBase ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_FILE_SEARCH_CONTEXT
    SERIALISABLE_VERSION = 1
    
    def __init__( self, file_service_key = CC.COMBINED_FILE_SERVICE_KEY, tag_service_key = CC.COMBINED_TAG_SERVICE_KEY, include_current_tags = True, include_pending_tags = True, predicates = None ):
        
        if predicates is None: predicates = []
        
        self._file_service_key = file_service_key
        self._tag_service_key = tag_service_key
        
        self._include_current_tags = include_current_tags
        self._include_pending_tags = include_pending_tags
        
        self._predicates = predicates
        
        self._search_complete = False
        
        self._InitialiseTemporaryVariables()
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_predicates = [ predicate.GetSerialisableTuple() for predicate in self._predicates ]
        
        return ( self._file_service_key.encode( 'hex' ), self._tag_service_key.encode( 'hex' ), self._include_current_tags, self._include_pending_tags, serialisable_predicates, self._search_complete )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( file_service_key, tag_service_key, self._include_current_tags, self._include_pending_tags, serialisable_predicates, self._search_complete ) = serialisable_info
        
        self._file_service_key = file_service_key.decode( 'hex' )
        self._tag_service_key = tag_service_key.decode( 'hex' )
        
        self._predicates = [ HydrusSerialisable.CreateFromSerialisableTuple( pred_tuple ) for pred_tuple in serialisable_predicates ]
        
        self._InitialiseTemporaryVariables()
        
    
    def _InitialiseTemporaryVariables( self ):
        
        system_predicates = [ predicate for predicate in self._predicates if predicate.GetType() in HC.SYSTEM_PREDICATES ]
        
        self._system_predicates = FileSystemPredicates( system_predicates )
        
        tag_predicates = [ predicate for predicate in self._predicates if predicate.GetType() == HC.PREDICATE_TYPE_TAG ]
        
        self._tags_to_include = []
        self._tags_to_exclude = []
        
        for predicate in tag_predicates:
            
            tag = predicate.GetValue()
            
            if predicate.GetInclusive(): self._tags_to_include.append( tag )
            else: self._tags_to_exclude.append( tag )
            
        
        namespace_predicates = [ predicate for predicate in self._predicates if predicate.GetType() == HC.PREDICATE_TYPE_NAMESPACE ]
        
        self._namespaces_to_include = []
        self._namespaces_to_exclude = []
        
        for predicate in namespace_predicates:
            
            namespace = predicate.GetValue()
            
            if predicate.GetInclusive(): self._namespaces_to_include.append( namespace )
            else: self._namespaces_to_exclude.append( namespace )
            
        
        wildcard_predicates =  [ predicate for predicate in self._predicates if predicate.GetType() == HC.PREDICATE_TYPE_WILDCARD ]
        
        self._wildcards_to_include = []
        self._wildcards_to_exclude = []
        
        for predicate in wildcard_predicates:
            
            wildcard = predicate.GetValue()
            
            if predicate.GetInclusive(): self._wildcards_to_include.append( wildcard )
            else: self._wildcards_to_exclude.append( wildcard )
            
        
    
    def GetFileServiceKey( self ): return self._file_service_key
    def GetNamespacesToExclude( self ): return self._namespaces_to_exclude
    def GetNamespacesToInclude( self ): return self._namespaces_to_include
    def GetPredicates( self ): return self._predicates
    def GetSystemPredicates( self ): return self._system_predicates
    def GetTagServiceKey( self ): return self._tag_service_key
    def GetTagsToExclude( self ): return self._tags_to_exclude
    def GetTagsToInclude( self ): return self._tags_to_include
    def GetWildcardsToExclude( self ): return self._wildcards_to_exclude
    def GetWildcardsToInclude( self ): return self._wildcards_to_include
    def IncludeCurrentTags( self ): return self._include_current_tags
    def IncludePendingTags( self ): return self._include_pending_tags
    def IsComplete( self ): return self._search_complete
    def SetComplete( self ): self._search_complete = True
    
    def SetFileServiceKey( self, file_service_key ):
        
        self._file_service_key = file_service_key
        
    
    def SetIncludeCurrentTags( self, value ):
        
        self._include_current_tags = value
        
    
    def SetIncludePendingTags( self, value ):
        
        self._include_pending_tags = value
        
    
    def SetPredicates( self, predicates ):
        
        self._predicates = predicates
        
        self._InitialiseTemporaryVariables()
        
    
    def SetTagServiceKey( self, tag_service_key ):
        
        self._tag_service_key = tag_service_key
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_FILE_SEARCH_CONTEXT ] = FileSearchContext

class FileSystemPredicates( object ):
    
    def __init__( self, system_predicates ):
        
        self._inbox = False
        self._archive = False
        self._local = False
        self._not_local = False
        
        self._common_info = {}
        
        self._limit = None
        self._similar_to = None
        
        self._file_services_to_include_current = []
        self._file_services_to_include_pending = []
        self._file_services_to_exclude_current = []
        self._file_services_to_exclude_pending = []
        
        self._ratings_predicates = []
        
        new_options = HydrusGlobals.client_controller.GetNewOptions()
        
        forced_search_limit = new_options.GetNoneableInteger( 'forced_search_limit' )
        
        if forced_search_limit is not None:
            
            self._limit = forced_search_limit
            
        
        for predicate in system_predicates:
            
            predicate_type = predicate.GetType()
            value = predicate.GetValue()
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_INBOX: self._inbox = True
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_ARCHIVE: self._archive = True
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_LOCAL: self._local = True
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_NOT_LOCAL: self._not_local = True
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_HASH:
                
                ( hash, hash_type ) = value
                
                self._common_info[ 'hash' ] = ( hash, hash_type )
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_AGE:
                
                ( operator, years, months, days, hours ) = value
                
                age = ( ( ( ( ( ( ( years * 12 ) + months ) * 30 ) + days ) * 24 ) + hours ) * 3600 )
                
                now = HydrusData.GetNow()
                
                # this is backwards because we are talking about age, not timestamp
                
                if operator == '<': self._common_info[ 'min_timestamp' ] = now - age
                elif operator == '>': self._common_info[ 'max_timestamp' ] = now - age
                elif operator == u'\u2248':
                    
                    self._common_info[ 'min_timestamp' ] = now - int( age * 1.15 )
                    self._common_info[ 'max_timestamp' ] = now - int( age * 0.85 )
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_MIME:
                
                mimes = value
                
                if isinstance( mimes, int ): mimes = ( mimes, )
                
                self._common_info[ 'mimes' ] = mimes
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_DURATION:
                
                ( operator, duration ) = value
                
                if operator == '<': self._common_info[ 'max_duration' ] = duration
                elif operator == '>': self._common_info[ 'min_duration' ] = duration
                elif operator == '=': self._common_info[ 'duration' ] = duration
                elif operator == u'\u2248':
                    
                    if duration == 0: self._common_info[ 'duration' ] = 0
                    else:
                        
                        self._common_info[ 'min_duration' ] = int( duration * 0.85 )
                        self._common_info[ 'max_duration' ] = int( duration * 1.15 )
                        
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_RATING:
                
                ( operator, value, service_key ) = value
                
                self._ratings_predicates.append( ( operator, value, service_key ) )
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_RATIO:
                
                ( operator, ratio_width, ratio_height ) = value
                
                if operator == '=': self._common_info[ 'ratio' ] = ( ratio_width, ratio_height )
                elif operator == u'\u2248':
                    
                    self._common_info[ 'min_ratio' ] = ( ratio_width * 0.85, ratio_height )
                    self._common_info[ 'max_ratio' ] = ( ratio_width * 1.15, ratio_height )
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_SIZE:
                
                ( operator, size, unit ) = value
                
                size = size * unit
                
                if operator == '<': self._common_info[ 'max_size' ] = size
                elif operator == '>': self._common_info[ 'min_size' ] = size
                elif operator == '=': self._common_info[ 'size' ] = size
                elif operator == u'\u2248':
                    
                    self._common_info[ 'min_size' ] = int( size * 0.85 )
                    self._common_info[ 'max_size' ] = int( size * 1.15 )
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_NUM_TAGS:
                
                ( operator, num_tags ) = value
                
                if operator == '<': self._common_info[ 'max_num_tags' ] = num_tags
                elif operator == '=': self._common_info[ 'num_tags' ] = num_tags
                elif operator == '>': self._common_info[ 'min_num_tags' ] = num_tags
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_WIDTH:
                
                ( operator, width ) = value
                
                if operator == '<': self._common_info[ 'max_width' ] = width
                elif operator == '>': self._common_info[ 'min_width' ] = width
                elif operator == '=': self._common_info[ 'width' ] = width
                elif operator == u'\u2248':
                    
                    if width == 0: self._common_info[ 'width' ] = 0
                    else:
                        
                        self._common_info[ 'min_width' ] = int( width * 0.85 )
                        self._common_info[ 'max_width' ] = int( width * 1.15 )
                        
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_NUM_PIXELS:
                
                ( operator, num_pixels, unit ) = value
                
                num_pixels = num_pixels * unit
                
                if operator == '<': self._common_info[ 'max_num_pixels' ] = num_pixels
                elif operator == '>': self._common_info[ 'min_num_pixels' ] = num_pixels
                elif operator == '=': self._common_info[ 'num_pixels' ] = num_pixels
                elif operator == u'\u2248':
                    
                    self._common_info[ 'min_num_pixels' ] = int( num_pixels * 0.85 )
                    self._common_info[ 'max_num_pixels' ] = int( num_pixels * 1.15 )
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_HEIGHT:
                
                ( operator, height ) = value
                
                if operator == '<': self._common_info[ 'max_height' ] = height
                elif operator == '>': self._common_info[ 'min_height' ] = height
                elif operator == '=': self._common_info[ 'height' ] = height
                elif operator == u'\u2248':
                    
                    if height == 0: self._common_info[ 'height' ] = 0
                    else:
                        
                        self._common_info[ 'min_height' ] = int( height * 0.85 )
                        self._common_info[ 'max_height' ] = int( height * 1.15 )
                        
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_NUM_WORDS:
                
                ( operator, num_words ) = value
                
                if operator == '<': self._common_info[ 'max_num_words' ] = num_words
                elif operator == '>': self._common_info[ 'min_num_words' ] = num_words
                elif operator == '=': self._common_info[ 'num_words' ] = num_words
                elif operator == u'\u2248':
                    
                    if num_words == 0: self._common_info[ 'num_words' ] = 0
                    else:
                        
                        self._common_info[ 'min_num_words' ] = int( num_words * 0.85 )
                        self._common_info[ 'max_num_words' ] = int( num_words * 1.15 )
                        
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_LIMIT:
                
                limit = value
                
                if self._limit is None:
                    
                    self._limit = limit
                    
                else:
                    
                    self._limit = min( limit, self._limit )
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_FILE_SERVICE:
                
                ( operator, current_or_pending, service_key ) = value
                
                if operator == True:
                    
                    if current_or_pending == HC.CURRENT: self._file_services_to_include_current.append( service_key )
                    else: self._file_services_to_include_pending.append( service_key )
                    
                else:
                    
                    if current_or_pending == HC.CURRENT: self._file_services_to_exclude_current.append( service_key )
                    else: self._file_services_to_exclude_pending.append( service_key )
                    
                
            
            if predicate_type == HC.PREDICATE_TYPE_SYSTEM_SIMILAR_TO:
                
                ( hash, max_hamming ) = value
                
                self._similar_to = ( hash, max_hamming )
                
            
        
    
    def GetFileServiceInfo( self ): return ( self._file_services_to_include_current, self._file_services_to_include_pending, self._file_services_to_exclude_current, self._file_services_to_exclude_pending )
    
    def GetSimpleInfo( self ): return self._common_info
    
    def GetLimit( self ): return self._limit
    
    def GetRatingsPredicates( self ): return self._ratings_predicates
    
    def GetSimilarTo( self ): return self._similar_to
    
    def HasSimilarTo( self ): return self._similar_to is not None
    
    def MustBeArchive( self ): return self._archive
    
    def MustBeInbox( self ): return self._inbox
    
    def MustBeLocal( self ): return self._local
    
    def MustNotBeLocal( self ): return self._not_local
    
class Predicate( HydrusSerialisable.SerialisableBase ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PREDICATE
    SERIALISABLE_VERSION = 1
    
    def __init__( self, predicate_type = None, value = None, inclusive = True, counts = None ):
        
        if counts is None: counts = {}
        
        if isinstance( value, list ):
            
            value = tuple( value )
            
        
        self._predicate_type = predicate_type
        self._value = value
        
        self._inclusive = inclusive
        self._counts = {}
        
        self._counts[ HC.CURRENT ] = 0
        self._counts[ HC.PENDING ] = 0
        
        for ( current_or_pending, count ) in counts.items(): self.AddToCount( current_or_pending, count )
        
    
    def __eq__( self, other ):
        
        return self.__hash__() == other.__hash__()
        
    
    def __hash__( self ):
        
        return ( self._predicate_type, self._value, self._inclusive ).__hash__()
        
    
    def __ne__( self, other ):
        
        return self.__hash__() != other.__hash__()
        
    
    def __repr__( self ):
        
        return 'Predicate: ' + HydrusData.ToUnicode( ( self._predicate_type, self._value, self._inclusive, self._counts ) )
        
    
    def _GetSerialisableInfo( self ):
        
        if self._predicate_type in ( HC.PREDICATE_TYPE_SYSTEM_RATING, HC.PREDICATE_TYPE_SYSTEM_FILE_SERVICE ):
            
            ( operator, value, service_key ) = self._value
            
            serialisable_value = ( operator, value, service_key.encode( 'hex' ) )
            
        elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_SIMILAR_TO:
            
            ( hash, max_hamming ) = self._value
            
            serialisable_value = ( hash.encode( 'hex' ), max_hamming )
            
        elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_HASH:
            
            ( hash, hash_type ) = self._value
            
            serialisable_value = ( hash.encode( 'hex' ), hash_type )
            
        else:
            
            serialisable_value = self._value
            
        
        return ( self._predicate_type, serialisable_value, self._inclusive )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( self._predicate_type, serialisable_value, self._inclusive ) = serialisable_info
        
        if self._predicate_type in ( HC.PREDICATE_TYPE_SYSTEM_RATING, HC.PREDICATE_TYPE_SYSTEM_FILE_SERVICE ):
            
            ( operator, value, service_key ) = serialisable_value
            
            self._value = ( operator, value, service_key.decode( 'hex' ) )
            
        elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_SIMILAR_TO:
            
            ( serialisable_hash, max_hamming ) = serialisable_value
            
            self._value = ( serialisable_hash.decode( 'hex' ), max_hamming )
            
        elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_HASH:
            
            ( serialisable_hash, hash_type ) = serialisable_value
            
            self._value = ( serialisable_hash.decode( 'hex' ), hash_type )
            
        else:
            
            self._value = serialisable_value
            
        
        if isinstance( self._value, list ):
            
            self._value = tuple( self._value )
            
        
    
    def AddToCount( self, current_or_pending, count ): self._counts[ current_or_pending ] += count
    
    def GetCopy( self ): return Predicate( self._predicate_type, self._value, self._inclusive, self._counts )
    
    def GetCountlessCopy( self ): return Predicate( self._predicate_type, self._value, self._inclusive )
    
    def GetCount( self, current_or_pending = None ):
        
        if current_or_pending is None: return sum( self._counts.values() )
        else: return self._counts[ current_or_pending ]
        
    
    def GetInclusive( self ):
        
        # patch from an upgrade mess-up ~v144
        if not hasattr( self, '_inclusive' ):
            
            if self._predicate_type not in HC.SYSTEM_PREDICATES:
                
                ( operator, value ) = self._value
                
                self._value = value
                
                self._inclusive = operator == '+'
                
            else: self._inclusive = True
            
        
        return self._inclusive
        
    
    def GetInfo( self ): return ( self._predicate_type, self._value, self._inclusive )
    
    def GetInverseCopy( self ):
        
        if self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_ARCHIVE:
            
            return Predicate( HC.PREDICATE_TYPE_SYSTEM_INBOX )
            
        elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_INBOX:
            
            return Predicate( HC.PREDICATE_TYPE_SYSTEM_ARCHIVE )
            
        elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_LOCAL:
            
            return Predicate( HC.PREDICATE_TYPE_SYSTEM_NOT_LOCAL )
            
        elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_NOT_LOCAL:
            
            return Predicate( HC.PREDICATE_TYPE_SYSTEM_LOCAL )
            
        elif self._predicate_type in ( HC.PREDICATE_TYPE_TAG, HC.PREDICATE_TYPE_NAMESPACE, HC.PREDICATE_TYPE_WILDCARD ):
            
            return Predicate( self._predicate_type, self._value, not self._inclusive )
            
        else:
            
            return None
            
        
    
    def GetType( self ):
        
        return self._predicate_type
        
    
    def GetUnicode( self, with_count = True ):
        
        count_text = u''
        
        if with_count:
            
            if self._counts[ HC.CURRENT ] > 0: count_text += u' (' + HydrusData.ConvertIntToPrettyString( self._counts[ HC.CURRENT ] ) + u')'
            if self._counts[ HC.PENDING ] > 0: count_text += u' (+' + HydrusData.ConvertIntToPrettyString( self._counts[ HC.PENDING ] ) + u')'
            
        
        if self._predicate_type in HC.SYSTEM_PREDICATES:
            
            if self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_EVERYTHING: base = u'system:everything'
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_INBOX: base = u'system:inbox'
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_ARCHIVE: base = u'system:archive'
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_UNTAGGED: base = u'system:untagged'
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_LOCAL: base = u'system:local'
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_NOT_LOCAL: base = u'system:not local'
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_DIMENSIONS: base = u'system:dimensions'
            elif self._predicate_type in ( HC.PREDICATE_TYPE_SYSTEM_NUM_TAGS, HC.PREDICATE_TYPE_SYSTEM_WIDTH, HC.PREDICATE_TYPE_SYSTEM_HEIGHT, HC.PREDICATE_TYPE_SYSTEM_NUM_WORDS ):
                
                if self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_NUM_TAGS: base = u'system:number of tags'
                elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_WIDTH: base = u'system:width'
                elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_HEIGHT: base = u'system:height'
                elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_NUM_WORDS: base = u'system:number of words'
                
                if self._value is not None:
                    
                    ( operator, value ) = self._value
                    
                    base += u' ' + operator + u' ' + HydrusData.ConvertIntToPrettyString( value )
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_DURATION:
                
                base = u'system:duration'
                
                if self._value is not None:
                    
                    ( operator, value ) = self._value
                    
                    base += u' ' + operator + u' ' + HydrusData.ConvertMillisecondsToPrettyTime( value )
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_RATIO:
                
                base = u'system:ratio'
                
                if self._value is not None:
                    
                    ( operator, ratio_width, ratio_height ) = self._value
                    
                    base += u' ' + operator + u' ' + str( ratio_width ) + u':' + str( ratio_height )
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_SIZE:
                
                base = u'system:size'
                
                if self._value is not None:
                    
                    ( operator, size, unit ) = self._value
                    
                    base += u' ' + operator + u' ' + str( size ) + HydrusData.ConvertIntToUnit( unit )
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_LIMIT:
                
                base = u'system:limit'
                
                if self._value is not None:
                    
                    value = self._value
                    
                    base += u' is ' + HydrusData.ConvertIntToPrettyString( value )
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_AGE:
                
                base = u'system:age'
                
                if self._value is not None:
                    
                    ( operator, years, months, days, hours ) = self._value
                    
                    base += u' ' + operator + u' ' + str( years ) + u'y' + str( months ) + u'm' + str( days ) + u'd' + str( hours ) + u'h'
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_NUM_PIXELS:
                
                base = u'system:num_pixels'
                
                if self._value is not None:
                    
                    ( operator, num_pixels, unit ) = self._value
                    
                    base += u' ' + operator + u' ' + str( num_pixels ) + ' ' + HydrusData.ConvertIntToPixels( unit )
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_HASH:
                
                base = u'system:hash'
                
                if self._value is not None:
                    
                    ( hash, hash_type ) = self._value
                    
                    base = u'system:' + hash_type + ' hash is ' + hash.encode( 'hex' )
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_MIME:
                
                base = u'system:mime'
                
                if self._value is not None:
                    
                    mimes = self._value
                    
                    if set( mimes ) == set( HC.SEARCHABLE_MIMES ):
                        
                        mime_text = 'anything'
                        
                    elif set( mimes ) == set( HC.SEARCHABLE_MIMES ).intersection( set( HC.APPLICATIONS ) ):
                        
                        mime_text = 'application'
                        
                    elif set( mimes ) == set( HC.SEARCHABLE_MIMES ).intersection( set( HC.AUDIO ) ):
                        
                        mime_text = 'audio'
                        
                    elif set( mimes ) == set( HC.SEARCHABLE_MIMES ).intersection( set( HC.IMAGES ) ):
                        
                        mime_text = 'image'
                        
                    elif set( mimes ) == set( HC.SEARCHABLE_MIMES ).intersection( set( HC.VIDEO ) ):
                        
                        mime_text = 'video'
                        
                    else:
                        
                        mime_text = ', '.join( [ HC.mime_string_lookup[ mime ] for mime in mimes ] )
                        
                    
                    base += u' is ' + mime_text
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_RATING:
                
                base = u'system:rating'
                
                if self._value is not None:
                    
                    ( operator, value, service_key ) = self._value
                    
                    service = HydrusGlobals.client_controller.GetServicesManager().GetService( service_key )
                    
                    base += u' for ' + service.GetName() + u' ' + operator + u' ' + HydrusData.ToUnicode( value )
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_SIMILAR_TO:
                
                base = u'system:similar to'
                
                if self._value is not None:
                    
                    ( hash, max_hamming ) = self._value
                    
                    base += u' ' + hash.encode( 'hex' ) + u' using max hamming of ' + str( max_hamming )
                    
                
            elif self._predicate_type == HC.PREDICATE_TYPE_SYSTEM_FILE_SERVICE:
                
                base = u'system:'
                
                if self._value is None:
                    
                    base += 'file service'
                    
                else:
                    
                    ( operator, current_or_pending, service_key ) = self._value
                    
                    if operator == True: base += u'is'
                    else: base += u'is not'
                    
                    if current_or_pending == HC.PENDING: base += u' pending to '
                    else: base += u' currently in '
                    
                    service = HydrusGlobals.client_controller.GetServicesManager().GetService( service_key )
                    
                    base += service.GetName()
                    
                
            
            base += count_text
            
        elif self._predicate_type == HC.PREDICATE_TYPE_TAG:
            
            tag = self._value
            
            if not self._inclusive: base = u'-'
            else: base = u''
            
            base += HydrusTags.RenderTag( tag )
            
            base += count_text
            
            siblings_manager = HydrusGlobals.client_controller.GetManager( 'tag_siblings' )
            
            sibling = siblings_manager.GetSibling( tag )
            
            if sibling is not None: base += u' (will display as ' + HydrusTags.RenderTag( sibling ) + ')'
            
        elif self._predicate_type == HC.PREDICATE_TYPE_PARENT:
            
            base = '    '
            
            tag = self._value
            
            base += HydrusTags.RenderTag( tag )
            
            base += count_text
            
        elif self._predicate_type == HC.PREDICATE_TYPE_NAMESPACE:
            
            namespace = self._value
            
            if not self._inclusive: base = u'-'
            else: base = u''
            
            base += namespace + u':*anything*'
            
        elif self._predicate_type == HC.PREDICATE_TYPE_WILDCARD:
            
            wildcard = self._value
            
            if not self._inclusive: base = u'-'
            else: base = u''
            
            base += HydrusTags.RenderTag( wildcard )
            
        
        return base
        
    
    def GetValue( self ): return self._value
    
    def SetInclusive( self, inclusive ): self._inclusive = inclusive

HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PREDICATE ] = Predicate

SYSTEM_PREDICATE_INBOX = Predicate( HC.PREDICATE_TYPE_SYSTEM_INBOX, None )

SYSTEM_PREDICATE_ARCHIVE = Predicate( HC.PREDICATE_TYPE_SYSTEM_ARCHIVE, None )

SYSTEM_PREDICATE_LOCAL = Predicate( HC.PREDICATE_TYPE_SYSTEM_LOCAL, None )

SYSTEM_PREDICATE_NOT_LOCAL = Predicate( HC.PREDICATE_TYPE_SYSTEM_NOT_LOCAL, None )
