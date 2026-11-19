import sys,unittest,tempfile,csv,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import batch,server
class Tests(unittest.TestCase):
 def test_batch_skips_existing_and_writes_report(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'institutions.csv').write_text('name,website\nExample,https://example.edu\n');out=root/'output';out.mkdir();(out/'example.json').write_text('{}')
   result=batch.run(str(root/'institutions.csv'),str(out),workers=2)
   self.assertEqual(result['skipped'],1);self.assertTrue((out/'batch_report.json').exists())
 def test_review_requires_value(self):
  with self.assertRaises(ValueError):server.set_review('unused',1,'verified','')
  with self.assertRaises(ValueError):server.set_review('unused',1,'pending','x')
 def test_api_has_comparison(self):
  self.assertTrue(callable(server.fetch_comparison))
if __name__=='__main__':unittest.main()
