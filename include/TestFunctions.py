import collections
import HydrusConstants as HC
import ClientDownloading
import os
import TestConstants
import unittest
import HydrusData
import ClientConstants as CC

class TestClientDownloadingFunctions( unittest.TestCase ):
    
    def test_dict_to_content_updates( self ):
        
        hash = HydrusData.GenerateKey()
        
        hashes = set( [ hash ] )
        
        local_key = CC.LOCAL_TAG_SERVICE_KEY
        remote_key = HydrusData.GenerateKey()
        
        service_keys_to_tags = { local_key : { 'a' } }
        
        content_updates = { local_key : [ HydrusData.ContentUpdate( HC.CONTENT_DATA_TYPE_MAPPINGS, HC.CONTENT_UPDATE_ADD, ( 'a', hashes ) ) ] }
        
        self.assertEqual( ClientDownloading.ConvertServiceKeysToTagsToServiceKeysToContentUpdates( hash, service_keys_to_tags ), content_updates )
        
        service_keys_to_tags = { remote_key : { 'c' } }
        
        content_updates = { remote_key : [ HydrusData.ContentUpdate( HC.CONTENT_DATA_TYPE_MAPPINGS, HC.CONTENT_UPDATE_PEND, ( 'c', hashes ) ) ] }
        
        self.assertEqual( ClientDownloading.ConvertServiceKeysToTagsToServiceKeysToContentUpdates( hash, service_keys_to_tags ), content_updates )
        
        service_keys_to_tags = { local_key : [ 'a', 'character:b' ], remote_key : [ 'c', 'series:d' ] }
        
        content_updates = {}
        
        content_updates[ local_key ] = [ HydrusData.ContentUpdate( HC.CONTENT_DATA_TYPE_MAPPINGS, HC.CONTENT_UPDATE_ADD, ( 'a', hashes ) ), HydrusData.ContentUpdate( HC.CONTENT_DATA_TYPE_MAPPINGS, HC.CONTENT_UPDATE_ADD, ( 'character:b', hashes ) ) ]
        content_updates[ remote_key ] = [ HydrusData.ContentUpdate( HC.CONTENT_DATA_TYPE_MAPPINGS, HC.CONTENT_UPDATE_PEND, ( 'c', hashes ) ), HydrusData.ContentUpdate( HC.CONTENT_DATA_TYPE_MAPPINGS, HC.CONTENT_UPDATE_PEND, ( 'series:d', hashes ) ) ]
        
        self.assertEqual( HydrusData.ContentUpdate( HC.CONTENT_DATA_TYPE_MAPPINGS, HC.CONTENT_UPDATE_PEND, 'c' ), HydrusData.ContentUpdate( HC.CONTENT_DATA_TYPE_MAPPINGS, HC.CONTENT_UPDATE_PEND, 'c' ) )
        self.assertEqual( ClientDownloading.ConvertServiceKeysToTagsToServiceKeysToContentUpdates( hash, service_keys_to_tags ), content_updates )
        
    
    def test_number_conversion( self ):
        
        i = 123456789
        
        i_pretty = HydrusData.ConvertIntToPrettyString( i )
        
        # this test only works on anglo computers; it is mostly so I can check it is working on mine
        
        self.assertEqual( i_pretty, '123,456,789' )
        
    
    def test_tags_to_dict( self ):
        
        local_key = HydrusData.GenerateKey()
        remote_key = HydrusData.GenerateKey()
        
        advanced_tag_options = {}
        
        advanced_tag_options[ local_key ] = [ '', 'character' ]
        advanced_tag_options[ remote_key ] = [ '', 'character' ]
        
        tags = [ 'a', 'character:b', 'series:c' ]
        
        service_keys_to_tags = { local_key : { 'a', 'character:b' }, remote_key : { 'a', 'character:b' } }
        
        self.assertEqual( ClientDownloading.ConvertTagsToServiceKeysToTags( tags, advanced_tag_options ), service_keys_to_tags )
        
    