import unittest
from pathlib import Path
from sys import path
path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline import extract_candidates
from server import ROOT
class PipelineTests(unittest.TestCase):
 def test_candidate_fields(self):
  result=extract_candidates('Tuition fee is shown here. Eligibility requirements. Average package. Scholarships available.')
  self.assertTrue({'fees','eligibility','placements','scholarships'}.issubset(result))
 def test_no_invented_data(self):
  self.assertEqual(extract_candidates('Welcome to our campus.'),{})
 def test_frontend_exists(self):
  self.assertTrue((ROOT/'index.html').exists())
if __name__=='__main__': unittest.main()
