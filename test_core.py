import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.security import extract_video_id_safe
from backend.chat_monitor import ChatSpikeDetector, normalize_message

class SecurityTests(unittest.TestCase):
    def test_watch_url(self): self.assertEqual(extract_video_id_safe('https://www.youtube.com/watch?v=abcdefghijk'),'abcdefghijk')
    def test_short_url(self): self.assertEqual(extract_video_id_safe('https://youtu.be/abcdefghijk'),'abcdefghijk')
    def test_reject_non_youtube(self):
        with self.assertRaises(ValueError): extract_video_id_safe('https://evil.example/watch?v=abcdefghijk')
    def test_reject_bad_id(self):
        with self.assertRaises(ValueError): extract_video_id_safe('https://youtube.com/watch?v=bad')

class DetectorTests(unittest.TestCase):
    def test_normalization(self): self.assertEqual(normalize_message('  HELLO   WORLD '),'hello world')
    def test_distinct_messages_same_author_not_all_suppressed(self):
        d=ChatSpikeDetector(author_spam_window=2.5)
        self.assertTrue(d.ingest_message('a','hello',timestamp=100)['accepted'])
        self.assertTrue(d.ingest_message('a','different message',timestamp=101)['accepted'])
    def test_exact_duplicate_filtered(self):
        d=ChatSpikeDetector()
        self.assertTrue(d.ingest_message('a','hello',timestamp=100)['accepted'])
        self.assertFalse(d.ingest_message('a','hello',timestamp=102)['accepted'])

if __name__=='__main__': unittest.main()
