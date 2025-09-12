from fpdf import FPDF
import os

# Ensure the directory exists
os.makedirs("downloads", exist_ok=True)

class PDF(FPDF):
    def header(self):
        # Use a built-in font for the header as it's simple ASCII
        self.set_font('helvetica', 'B', 15)
        self.cell(0, 10, 'Mock PDF Document', 1, 0, 'C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

pdf = PDF()

# Add the CJK font. 'uni' is a common alias for Unicode fonts in FPDF.
# The 'TTCFFile' parameter is used to specify which font in the collection to use (0-based index)
# NotoSansCJK-Regular.ttc typically has 'Noto Sans CJK TC Regular' at index 3
# Let's try index 0 first, which is often a generic one.
try:
    pdf.add_font('NotoSansCJK', '', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
except RuntimeError as e:
    # If the default index fails, try the specific index for TC
    if "does not contain any GPOS table" in str(e):
        pdf.add_font('NotoSansCJK', '', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', uni=True)
    else:
        # Re-raise other errors
        raise

pdf.set_font('NotoSansCJK', '', 12)

# Add pages and content
pdf.add_page()
pdf.multi_cell(0, 10, 'This is a mock PDF file created for testing purposes. It contains some text to simulate a real document.')

pdf.add_page()
pdf.multi_cell(0, 10, '這是用於測試的模擬 PDF 檔案。它包含一些文字來模擬真實文件。')

pdf.output('downloads/mock_file_3.pdf')

print("Mock PDF file created successfully at downloads/mock_file_3.pdf")
