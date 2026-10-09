"""Recorded synthetic walkthrough: provenance, continuity, and media delivery."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import shutil
import unittest

from scripts.serve import make_service_handler

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'web/spatial/assets'


class SpatialWalkthroughQA(unittest.TestCase):
    def test_video_manifest_and_source_hashes(self):
        manifest = json.loads((ASSETS / 'walkthrough.json').read_text())
        self.assertTrue(manifest['synthetic'])
        self.assertTrue(manifest['generated_locally'])
        self.assertEqual(manifest['live_model_calls'], 0)
        self.assertFalse(manifest['actual_browser'])
        for file, sha in manifest['files_sha256'].items():
            self.assertEqual(hashlib.sha256((ASSETS / file).read_bytes()).hexdigest(), sha)
        self.assertEqual(hashlib.sha256((ROOT / manifest['geometry_source']).read_bytes()).hexdigest(), manifest['geometry_source_sha256'])
        self.assertEqual(hashlib.sha256((ROOT / 'scripts/build_spatial_walkthrough.cjs').read_bytes()).hexdigest(), manifest['generator_sha256'])
        self.assertEqual(manifest['route'][-1]['t'], manifest['duration_seconds'])
        self.assertGreaterEqual(manifest['validation']['room_continuation_seconds'], 10)

    def test_path_uses_current_model_and_reaches_candidate_without_wall_crossing(self):
        p = subprocess.run(['node', 'scripts/build_spatial_walkthrough.cjs', '--test'], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)
        report = json.loads(p.stdout)
        self.assertEqual(report['validation']['eye_level_wall_crossings'], 0)
        self.assertTrue(report['validation']['ends_inside_candidate'])
        self.assertGreater(report['validation']['sampled_positions'], 600)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools required for media decode check')
    def test_h264_duration_and_full_decode(self):
        p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_name,width,height,pix_fmt', '-of', 'json', str(ASSETS / 'walkthrough.mp4')], capture_output=True, text=True, timeout=15)
        self.assertEqual(p.returncode, 0, p.stderr)
        info = json.loads(p.stdout)
        self.assertEqual(float(info['format']['duration']), 28)
        self.assertEqual(len(info['streams']), 1)
        stream = info['streams'][0]
        self.assertEqual((stream['codec_name'], stream['width'], stream['height'], stream['pix_fmt']), ('h264', 960, 540, 'yuv420p'))
        p = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(ASSETS / 'walkthrough.mp4'), '-f', 'null', '-'], capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_video_has_manual_playback_captions_and_all_chapters(self):
        class Tags(HTMLParser):
            def __init__(self):
                super().__init__(); self.tags = []
            def handle_starttag(self, tag, attrs):
                self.tags.append((tag, dict(attrs)))
        parser = Tags(); parser.feed((ROOT / 'web/spatial/index.html').read_text())
        video = [a for tag, a in parser.tags if tag == 'video'][0]
        self.assertIn('controls', video)
        self.assertIn('playsinline', video)
        self.assertNotIn('autoplay', video)
        self.assertEqual(video['preload'], 'none')
        self.assertTrue(any(tag == 'track' and a.get('srclang') == 'ko' for tag, a in parser.tags))
        captions = (ASSETS / 'walkthrough.ko.vtt').read_text()
        self.assertEqual(captions.count(' --> '), 5)
        for text in ('계단', '복도', '현관', '주방', '창가', '원문 진술', '미확인'):
            self.assertIn(text, captions)

    def test_media_range_head_and_invalid_ranges_without_opening_server(self):
        # Invoke the actual handler with a capture response, no loopback port/browser.
        handler_type = make_service_handler(None)
        handler = handler_type.__new__(handler_type)
        handler.path = '/spatial/assets/walkthrough.mp4'
        replies = []
        handler.respond = lambda code, data, mime, extra=None, head=False: replies.append((code, data, mime, extra, head))
        original = (ASSETS / 'walkthrough.mp4').read_bytes()
        for requested, expected in [('bytes=0-63', original[:64]), ('bytes=-32', original[-32:]), ('bytes=128-', original[128:])]:
            handler.headers = {'Range': requested}; handler._get()
            code, data, mime, headers, _ = replies[-1]
            self.assertEqual(code, 206); self.assertEqual(data, expected); self.assertEqual(mime, 'video/mp4')
            self.assertEqual(headers['Accept-Ranges'], 'bytes')
        for requested in ('bytes=999999999-', 'bytes=-0', 'bytes=5-1', 'bytes=0-5,8-9', 'bytes=-', 'bytes=999999999999999999999-'):
            handler.headers = {'Range': requested}; handler._get()
            self.assertEqual(replies[-1][0], 416)
        handler.headers = {}; handler._get(head=True)
        self.assertEqual(replies[-1][0], 200); self.assertTrue(replies[-1][4])
        for name, mime in [('walkthrough.ko.vtt', 'text/vtt'), ('walkthrough-poster.png', 'image/png'), ('walkthrough.json', 'application/json')]:
            handler.path = '/spatial/assets/' + name; handler._get()
            self.assertEqual(replies[-1][0], 200); self.assertTrue(replies[-1][2].startswith(mime))


if __name__ == '__main__':
    unittest.main()
