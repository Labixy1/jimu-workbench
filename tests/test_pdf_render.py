import subprocess,tempfile,unittest
from pathlib import Path
from asset_files import runtime
class PDFRenderTests(unittest.TestCase):
 def test_bundled_renderer(self):
  with tempfile.TemporaryDirectory() as folder:
   pdf=Path(folder)/'test.pdf';png=Path(folder)/'page.png'
   code="from reportlab.pdfgen import canvas;import sys;c=canvas.Canvas(sys.argv[1]);c.drawString(72,700,'Fixture PDF preview');c.save()"
   subprocess.run([runtime('python'),'-c',code,str(pdf)],check=True,timeout=15)
   code="import sys,pypdfium2 as p;d=p.PdfDocument(sys.argv[1]);d[0].render(scale=1).to_pil().save(sys.argv[2])"
   subprocess.run([runtime('python'),'-c',code,str(pdf),str(png)],check=True,timeout=15)
   self.assertTrue(png.read_bytes().startswith(b'\x89PNG'))
