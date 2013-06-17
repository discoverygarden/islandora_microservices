
from plugin_manager import IslandoraListenerPlugin as ILP
from islandoraUtils import DSConverter as CONV, fedoraLib as FL
import logging
from os import path
from shutil import rmtree
import mimetypes
from islandoraUtils.xmlib import import_etree
etree = import_etree()

class fjm(ILP):
    def __init__(self):
        self.logger = logging.getLogger('IslandoraListenerPlugin.fjm')

    def fedoraMessage(self, message, obj, client):
        logger = self.logger
        logger.debug(message)
        if message['dsid']:
            if message['dsid'] == 'TIFF':
                CONV.create_jpeg_derivative(obj, 'TIFF', 'FULL_JPG', label='Derived full-sized JPEG')
                CONV.create_jpeg_derivative(obj, 'TIFF', 'WEB_JPG', dimensions=(1024, 1024), label='Derived web-sized JPEG')
                CONV.create_jpeg_derivative(obj, 'TIFF', 'TN', dimensions=(200, 200), label='Derived thumbnail-sized JPEG')
            elif message['dsid'] == 'FULL_JPG' and 'TIFF' not in obj:
                CONV.create_jpeg_derivative(obj, 'FULL_JPG', 'WEB_JPG', dimensions=(1024, 1024), label='Derived web-sized JPEG')
                CONV.create_jpeg_derivative(obj, 'FULL_JPG', 'TN', dimensions=(200, 200), label='Derived thumbnail-sized JPEG')
            elif message['dsid'] == 'PDF':
                CONV.create_swf(obj, 'PDF', 'SWF')
                CONV.create_thumbnail(obj, 'PDF', 'TN')
            elif message['dsid'] == 'JPG':
                CONV.create_thumbnail(obj, 'JPG', 'TN')
            elif message['dsid'] == 'MARCXML':
                CONV.marcxml_to_mods(obj, 'MARCXML', 'MODS')
            elif message['dsid'] == 'OBJ':
                CONV.create_swf(obj, 'OBJ', 'SWF')
                CONV.create_thumbnail(obj, 'OBJ', 'TN')
            elif message['dsid'] == 'ENDNOTE' and 'ENDNOTE' in obj and 'MODS' in obj:
                self.__fix_ir_ingest(obj)
        elif message['method'] == 'ingest':
            if 'ENDNOTE' in obj and 'MODS' in obj: #FIXME:  This might be better off implemented on the PHP side, via the Bibutils post-process hook... (Which I did not know existed for the initial implementation...  Or it might be better off done here...  Dunno...)
                self.__fix_ir_ingest(obj)

    def islandoraMessage(self, method, message, client):
        pass
        
    def __fix_ir_ingest(self, obj):
        logger = self.logger
        ir_ingest_dir = '/mnt/islandora/ToIngest/ceacs/citation'  #Hack-tastic...
        endnote = etree.fromstring(obj['ENDNOTE'].getContent().read())
        mods = etree.fromstring(obj['MODS'].getContent().read())
        DSs = dict() #FIXME:  Should probably load the entire list...
        namespaces = {
          'mods': 'http://www.loc.gov/mods/v3'
        }
        removing_url = False
        for related_url in endnote.findall('records/record/urls/related-urls/url/style'):
            #If the url doesn't seem to contain a scheme specifier, assume it's relative to the 'ir_ingest_dir'
            related_text = related_url.text
            if '://' not in related_text:
                logger.debug('Found apparent relative %s' % related_url.text)
                dsid = related_text.rpartition('.')[2].strip().upper()
                logging
                obj._dsids = None
                if dsid not in obj:
                    DSs[dsid] = 1
                else:
                    dsid = dsid + DSs[dsid]
                    DSs[dsid] += 1

                pdf_path = path.join(ir_ingest_dir, related_text)
                if path.exists(pdf_path):
                    FL.update_hashed_datastream_without_dup(obj, dsid, pdf_path, mimeType="application/pdf", checksumType='SHA-1')
                else:
                    logger.warn('PDF does not exist where we expect it...  Let\'s keep on chugging.')
                
                #Get rid of the URL...
                style = related_url
                url = style.getparent()
                related_urls = url.getparent()
                related_urls.remove(url)
                urls = related_urls.getparent()
                if len(related_urls) == 0 and len(urls) == 1:
                    urls.getparent().remove(urls)
                
                for url in mods.findall('{%(mods)s}location/{%(mods)s}url' % namespaces):
                    if url.text == related_text:
                        parent = url.getparent()
                        parent.remove(url)
                        if len(parent) == 0:
                            parent.getparent().remove(parent)
                        removing_url = True
                        break
                        
        found = False
        lastGenre = None
        for genre in mods.findall('{%(mods)s}genre' % namespaces):
          type = genre.get('authority')
          lastGenre = genre
          if type == 'endnote':
            found = True
            break

        if not found:
            rt = endnote.find('records/record/ref-type')
            reftype = rt.get('name')
            
            #XXX: Hack to deal with type not recognized by Bibutils... (Assuming that if already in MODS, it is correct...)
            if reftype == 'Book':
                wt = endnote.findtext('records/record/work-type/style').strip()
                if wt == 'Working Paper':
                    reftype = wt

            #4.1.2 and add it to the MODS in the genre (just as child of /mods:mods)
            if reftype is not None:
              reftype_el = etree.Element('genre')
              reftype_el.text = reftype
              reftype_el.set('authority', 'endnote')
              if lastGenre != None:
                mods.insert(mods.index(lastGenre), reftype_el)
              else:
                mods.append(reftype_el)
            
        if removing_url or not found:
            obj['MODS'].setContent(etree.tounicode(mods, pretty_print=True))
