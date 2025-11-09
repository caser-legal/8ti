"""
govinfo_harvester.py - Extract rich metadata from govinfo.gov court filings

Processes govinfo RSS entries and extracts:
- MODS metadata (parties, case numbers, subjects, court details)
- PREMIS metadata (checksums, preservation events)
- Context page data (summary, citation)
- ZIP inventory (file listing, primary PDF path)
"""

import requests
from lxml import etree, html
import zipfile
from io import BytesIO
from functools import lru_cache
from urllib.parse import urljoin
import logging
import hashlib
import time

logger = logging.getLogger(__name__)


class GovinfoHarvester:
    BASE_URL = "https://www.govinfo.gov"
    
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; CaserBot/1.0)"
        })
    
    @lru_cache(maxsize=1000)
    def fetch(self, url, max_attempts=5, base_backoff=2):
        """Fetch URL with caching and retry/backoff for transient errors."""
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self.session.get(url, timeout=10)
                resp.raise_for_status()
                return resp.content
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < max_attempts:
                    backoff = base_backoff * attempt
                    logger.warning("Fetch failed for %s (attempt %d/%d), retrying in %ds: %s", url, attempt, max_attempts, backoff, e)
                    time.sleep(backoff)
                    continue
                logger.error("Failed to fetch %s: %s", url, e)
                raise
    
    def process_entry(self, rss_entry, feed_metadata=None):
        """Process a single RSS entry and extract all metadata"""
        package_id = rss_entry.get('guid', '')
        
        doc = {
            'objectID': self.hash(package_id),
            'guid': package_id,
            'title': rss_entry.get('title', ''),
            'description': rss_entry.get('description', ''),
            'link': rss_entry.get('link', ''),
            'pubDate': rss_entry.get('pubDate', 0),
            'category': rss_entry.get('category', []) if isinstance(rss_entry.get('category'), list) else [rss_entry.get('category', '')],
            'creator': rss_entry.get('creator', ''),
            'source': rss_entry.get('source', 'govinfo')
        }
        
        # Extract all URLs from description HTML
        doc.update(self.extract_urls(rss_entry.get('description', ''), package_id))
        
        # Scrape context page
        if doc.get('link'):
            try:
                doc.update(self.scrape_context(doc['link']))
            except (requests.exceptions.RequestException, ValueError, etree.XMLSyntaxError) as e:
                logger.warning("Context scrape failed for %s: %s", package_id, e)
        
        # Parse MODS
        if doc.get('govinfoModsUrl'):
            try:
                mods = self.fetch(doc['govinfoModsUrl'])
                doc.update(self.parse_mods(mods))
            except (requests.exceptions.RequestException, etree.XMLSyntaxError) as e:
                logger.warning("MODS parse failed for %s: %s", package_id, e)
        
        # Parse PREMIS
        if doc.get('govinfoPremisUrl'):
            try:
                premis = self.fetch(doc['govinfoPremisUrl'])
                doc.update(self.parse_premis(premis))
            except (requests.exceptions.RequestException, etree.XMLSyntaxError) as e:
                logger.warning("PREMIS parse failed for %s: %s", package_id, e)
        
        # Skip ZIP inventory - we have the link, don't need to download massive files
        # if doc.get('govinfoZipUrl'):
        #     try:
        #         zip_data = self.fetch(doc['govinfoZipUrl'])
        #         doc.update(self.inventory_zip(zip_data))
        #     except Exception as e:
        #         logger.warning(f"ZIP inventory failed for {package_id}: {e}")
        
        # Set documentLink to best PUBLIC download (not ZIP internal path)
        doc['documentLink'] = (
            (doc.get('modsPdfUrls') or [None])[0] or  # MODS PDF first
            doc.get('govinfoPdfUrl') or                # Direct PDF
            doc.get('govinfoZipUrl') or                # ZIP as fallback
            ''
        )
        
        # Legacy fields for iOS app (map from MODS or feed metadata)
        doc['courtId'] = self._extract_court_id(doc, feed_metadata)
        doc['courtName'] = doc.get('modsTitle') or (feed_metadata or {}).get('name', '')
        doc['state'] = doc.get('modsCourtState') or (feed_metadata or {}).get('state', '')
        doc['parties'] = "; ".join(doc.get('modsParties', []))
        doc['type'] = (feed_metadata or {}).get('type', '')
        doc['timezone'] = (feed_metadata or {}).get('timezone', '')
        doc['courtSlug'] = self._slugify(doc['courtName'])
        doc['feedId'] = (feed_metadata or {}).get('feedId', 'govinfo')
        
        return doc
    
    def extract_urls(self, description_html, package_id):
        """Extract all govinfo URLs from RSS description HTML"""
        if not description_html:
            return {}
        
        urls = {}
        try:
            tree = html.fromstring(description_html)
            
            # Parse actual anchors first
            for a in tree.xpath('//a[@href]'):
                href = a.get('href')
                if 'mods.xml' in href:
                    urls['govinfoModsUrl'] = self.resolve_url(href)
                elif 'premis.xml' in href:
                    urls['govinfoPremisUrl'] = self.resolve_url(href)
                elif 'summary.xml' in href:
                    urls['govinfoSummaryXmlUrl'] = self.resolve_url(href)
                elif '.zip' in href and 'pkg' in href:
                    urls['govinfoZipUrl'] = self.resolve_url(href)
                elif '.pdf' in href and 'pkg' in href:
                    urls['govinfoPdfUrl'] = self.resolve_url(href)
                elif '/html' in href:
                    urls['govinfoHtmlUrl'] = self.resolve_url(href)
        except (etree.XMLSyntaxError, ValueError) as e:
            logger.warning("Failed to parse description HTML: %s", e)
        
        # Fallback to synthetic URLs if anchors missing
        if not urls.get('govinfoModsUrl'):
            urls['govinfoModsUrl'] = f"{self.BASE_URL}/metadata/pkg/{package_id}/mods.xml"
        if not urls.get('govinfoPremisUrl'):
            urls['govinfoPremisUrl'] = f"{self.BASE_URL}/metadata/pkg/{package_id}/premis.xml"
        if not urls.get('govinfoZipUrl'):
            urls['govinfoZipUrl'] = f"{self.BASE_URL}/content/pkg/{package_id}.zip"
        if not urls.get('govinfoPdfUrl'):
            urls['govinfoPdfUrl'] = f"{self.BASE_URL}/content/pkg/{package_id}.pdf"
        if not urls.get('govinfoHtmlUrl'):
            urls['govinfoHtmlUrl'] = f"{self.BASE_URL}/content/pkg/{package_id}/html"
        if not urls.get('govinfoSummaryXmlUrl'):
            urls['govinfoSummaryXmlUrl'] = f"{self.BASE_URL}/metadata/pkg/{package_id}/summary.xml"
        
        return urls
    
    def scrape_context(self, url):
        """Scrape govinfo context page for summary and citation"""
        page = self.fetch(url)
        tree = html.fromstring(page)
        
        # Try multiple selectors for summary
        summary_selectors = [
            '//div[@class="summary"]//text()',
            '//div[@class="more-info"]//text()',
            '//div[@class="metadata-table"]//text()',
            '//div[contains(@class, "description")]//text()'
        ]
        summary = []
        for selector in summary_selectors:
            summary = tree.xpath(selector)
            if summary:
                break
        
        # Try multiple selectors for context HTML
        context_selectors = [
            '//div[@class="context"]',
            '//div[@class="more-info"]',
            '//div[@class="metadata-table"]'
        ]
        context_html = None
        for selector in context_selectors:
            context = tree.xpath(selector)
            if context:
                context_html = html.tostring(context[0]).decode()
                break
        
        # Extract citation
        citation_selectors = [
            '//div[@id="citation"]//text()',
            '//div[@class="citation"]//text()',
            '//span[@class="citation"]//text()'
        ]
        citation = []
        for selector in citation_selectors:
            citation = tree.xpath(selector)
            if citation:
                break
        
        return {
            'govinfoSummary': ' '.join(summary).strip() if summary else '',
            'govinfoContextHtml': context_html or '',
            'govinfoCitation': ' '.join(citation).strip() if citation else ''
        }
    
    def parse_mods(self, mods_xml):
        """Parse MODS XML for parties, case numbers, subjects, etc."""
        ns = {'mods': 'http://www.loc.gov/mods/v3'}
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(mods_xml, parser=parser)
        
        # Parties
        parties = [
            p.get('fullName')
            for p in root.xpath('.//mods:extension/party[@fullName]', namespaces=ns)
        ]
        
        # Subjects
        subjects = [
            s.text
            for s in root.xpath('.//mods:subject//mods:topic', namespaces=ns)
            if s.text
        ]
        
        # Identifiers as list of objects - SKIP (needs nested fields)
        # identifiers = [
        #     {'type': i.get('type'), 'value': i.text}
        #     for i in root.xpath('.//mods:identifier[@type]', namespaces=ns)
        #     if i.text
        # ]
        
        # PDF URLs from relatedItem
        pdf_urls = [
            url.text
            for url in root.xpath('.//mods:relatedItem[@type="otherFormat"]//mods:url[@access="raw object"]', namespaces=ns)
            if url.text and url.text.endswith('.pdf')
        ]
        
        # Case details
        case_number = root.xpath('.//mods:extension/caseNumber/text()', namespaces=ns)
        court_type = root.xpath('.//mods:extension/courtType/text()', namespaces=ns)
        court_state = root.xpath('.//mods:extension/courtState/text()', namespaces=ns)
        title = root.xpath('.//mods:titleInfo/mods:title/text()', namespaces=ns)
        
        return {
            'modsTitle': title[0] if title else '',
            'modsParties': parties,
            'modsCaseNumber': case_number[0] if case_number else '',
            'modsSubjects': subjects,
            'modsPdfUrls': pdf_urls,
            'modsCourtType': court_type[0] if court_type else '',
            'modsCourtState': court_state[0] if court_state else ''
        }
    
    def parse_premis(self, premis_xml):
        """Parse PREMIS XML for checksums and preservation events"""
        ns = {'premis': 'http://www.loc.gov/premis/v3'}
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(premis_xml, parser=parser)
        
        object_id = root.xpath('.//premis:objectIdentifierValue/text()', namespaces=ns)
        
        # Fixity and Events as objects - SKIP (needs nested fields)
        
        return {
            'premisObjectId': object_id[0] if object_id else ''
        }
    
    def inventory_zip(self, zip_data):
        """Inventory ZIP contents and find primary PDF"""
        z = zipfile.ZipFile(BytesIO(zip_data))
        primary_pdf_path = None
        
        for info in z.filelist:
            # Find primary PDF (usually ends with -0.pdf)
            if info.filename.endswith('.pdf'):
                if '-0.pdf' in info.filename:
                    primary_pdf_path = info.filename
                elif not primary_pdf_path:
                    primary_pdf_path = info.filename
        
        return {
            'zipPrimaryPdfPath': primary_pdf_path or ''  # Path inside ZIP (reference only)
        }
    
    def get_file_type(self, filename):
        """Get file type from extension"""
        ext = filename.split('.')[-1].lower()
        return ext if ext in ['pdf', 'xml', 'html', 'txt'] else 'other'
    
    def resolve_url(self, url):
        """Resolve relative URLs to fully qualified"""
        if not url:
            return ''
        if url.startswith('http'):
            return url
        return urljoin(self.BASE_URL, url)
    
    def hash(self, s):
        """Generate SHA1 hash for document ID"""
        return hashlib.sha1(s.encode()).hexdigest()
    
    def _extract_court_id(self, doc, feed_metadata):
        """Extract court ID from case number or feed metadata"""
        case_number = doc.get('modsCaseNumber', '')
        if case_number and ':' in case_number:
            return case_number.split(':')[0]
        return (feed_metadata or {}).get('courtId', '')
    
    def _slugify(self, text):
        """Convert text to slug"""
        import re
        return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')


# Usage example
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    harvester = GovinfoHarvester()
    
    # Sample RSS entry
    rss_entry = {
        'guid': 'USCOURTS-okeb-7_13-mp-10001',
        'title': 'General Orders for Oklahoma Eastern Bankruptcy Court',
        'description': '<h2>Metadata download</h2><a href="/metadata/pkg/USCOURTS-okeb-7_13-mp-10001/mods.xml">MODS</a>...',
        'link': 'https://www.govinfo.gov/app/details/USCOURTS-okeb-7_13-mp-10001/context',
        'pubDate': 1730774400
    }
    
    feed_metadata = {
        'name': 'Oklahoma Eastern Bankruptcy Court',
        'state': 'Oklahoma',
        'type': 'bankruptcy',
        'timezone': 'America/Chicago',
        'courtId': 'okeb',
        'feedId': 'govinfo-okeb'
    }
    
    doc = harvester.process_entry(rss_entry, feed_metadata)
    
    print("Extracted document:")
    import json
    print(json.dumps(doc, indent=2))
