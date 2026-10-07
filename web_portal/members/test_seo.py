import importlib.util
import json
import threading
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.conf import settings
from django.test import SimpleTestCase


PUBLIC_ROOT = settings.BASE_DIR.parent / 'lifebox-landing'
ORIGIN = 'https://lifeboxgym.com'
PUBLIC_PATHS = ('/', '/bodybuilding', '/calisthenics', '/functional', '/coaches')


class PageMetadata(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.links = []
        self.metas = []
        self.images = []
        self.videos = []
        self.title = ''
        self.schemas = []
        self.in_title = False
        self.in_schema = False
        self.schema_text = ''
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        collections = {'link': self.links, 'meta': self.metas, 'img': self.images, 'video': self.videos}
        if tag in collections:
            collections[tag].append(attrs)
        if tag == 'title':
            self.in_title = True
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.in_schema = True
            self.schema_text = ''

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'script' and self.in_schema:
            self.schemas.append(json.loads(self.schema_text))
            self.in_schema = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_schema:
            self.schema_text += data


class PublicSearchTests(SimpleTestCase):
    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return PageMetadata(response.content.decode('utf-8'))

    def test_sitemap_lists_only_public_canonical_pages(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml; charset=utf-8')
        xml = ElementTree.fromstring(b''.join(response.streaming_content))
        urls = [node.text for node in xml.findall('{*}url/{*}loc')]
        self.assertCountEqual(urls, [ORIGIN + path for path in PUBLIC_PATHS])
        titles = []
        for url in urls:
            with self.subTest(url=url):
                # Tracking parameters must not change the canonical URL.
                page = self.page(urlparse(url).path + '?utm_source=audit')
                canonical = [link['href'] for link in page.links if link.get('rel') == 'canonical']
                self.assertEqual(canonical, [url])
                self.assertIn('اکباتان', page.title)
                titles.append(page.title)
                description = next(meta['content'] for meta in page.metas if meta.get('name') == 'description')
                self.assertIn('اکباتان', description)
                self.assertFalse(any('noindex' in meta.get('content', '') for meta in page.metas if meta.get('name') == 'robots'))
                self.assertEqual(next(meta['content'] for meta in page.metas if meta.get('property') == 'og:url'), url)
        self.assertEqual(len(set(titles)), len(PUBLIC_PATHS))

    def test_robots_points_to_sitemap_without_blocking_noindex_pages(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        body = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn('User-agent: *', body)
        self.assertIn('Sitemap: ' + ORIGIN + '/sitemap.xml', body)
        self.assertNotIn('Disallow:', body)
        for path in ('/dashboard', '/pending'):
            page = self.page(path)
            self.assertTrue(any('noindex' in meta.get('content', '') for meta in page.metas if meta.get('name') == 'robots'))
        self.assertEqual(self.client.get('/coach-panel').status_code, 302)

    def test_club_schema_uses_visible_business_details_and_real_images(self):
        response = self.client.get('/')
        content = response.content.decode('utf-8')
        page = PageMetadata(content)
        self.assertEqual(len(page.schemas), 1)
        club = page.schemas[0]
        self.assertEqual(club['@type'], 'HealthClub')
        self.assertEqual(club['url'], ORIGIN + '/')
        self.assertEqual(club['telephone'], '+982144656198')
        self.assertIn('tel:02144656198', content)
        self.assertIn(club['address']['streetAddress'], content)
        self.assertEqual(club['address']['addressCountry'], 'IR')
        hours = club['openingHoursSpecification'][0]
        self.assertEqual(hours['dayOfWeek'], ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'])
        self.assertEqual((hours['opens'], hours['closes']), ('06:30', '23:00'))
        self.assertNotIn('review', club)
        self.assertNotIn('aggregateRating', club)
        for image in club['image'] + [club['logo']]:
            self.assertTrue((PUBLIC_ROOT / urlparse(image).path.lstrip('/')).is_file())

    def test_responsive_images_exist_and_preloads_match_hero_images(self):
        for path in PUBLIC_PATHS:
            with self.subTest(path=path):
                page = self.page(path)
                for image in page.images:
                    self.assertTrue((PUBLIC_ROOT / image['src']).is_file())
                    if image['src'].endswith('.webp'):
                        self.assertIn('width', image)
                        self.assertIn('height', image)
                        variants = [candidate.strip().split()[0] for candidate in image.get('srcset', '').split(',') if candidate.strip()]
                        if variants:
                            self.assertEqual(len(set(variants)), len(variants))
                            for variant in variants:
                                self.assertTrue((PUBLIC_ROOT / variant).is_file())
                for preload in page.links:
                    if preload.get('as') == 'image':
                        hero = next(image for image in page.images if image.get('fetchpriority') == 'high')
                        self.assertEqual(preload['href'], hero['src'])
                        self.assertEqual(preload.get('imagesrcset'), hero.get('srcset'))
                        self.assertEqual(preload.get('imagesizes'), hero.get('sizes'))
        home = self.page('/')
        for video in home.videos:
            self.assertEqual(video['preload'], 'none')
            if 'poster' in video:
                self.assertTrue((PUBLIC_ROOT / video['poster']).is_file())

    def test_crawler_files_support_head_and_missing_assets_return_404(self):
        for path in ('/robots.txt', '/sitemap.xml', '/assets/optimized/image5-640.webp'):
            self.assertEqual(self.client.head(path).status_code, 200)
        response = self.client.get('/assets/optimized/image5-640.webp')
        self.assertEqual(response['Content-Type'], 'image/webp')
        response.close()
        self.assertEqual(self.client.get('/assets/optimized/missing.webp').status_code, 404)

    def test_standalone_server_serves_crawler_files_and_webp(self):
        spec = importlib.util.spec_from_file_location('lifebox_seo_server', PUBLIC_ROOT / 'server.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        server = module.LifeBoxHTTPServer(('127.0.0.1', 0), module.LifeBoxHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f'http://127.0.0.1:{server.server_port}'
            for path, expected_type in (('/robots.txt', 'text/plain'), ('/sitemap.xml', 'application/xml'), ('/assets/optimized/image5-640.webp', 'image/webp')):
                with self.subTest(path=path), urlopen(origin + path, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), expected_type)
                    self.assertTrue(response.read())
            with urlopen(Request(origin + '/sitemap.xml', method='HEAD'), timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b'')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
