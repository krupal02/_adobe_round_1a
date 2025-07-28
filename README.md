PDF Outline Extractor
This Python tool efficiently extracts the main title and a hierarchical outline (H1, H2, H3 headings) from PDF documents, outputting the structured data as JSON files. It dynamically analyzes font sizes and uses smart heuristics to accurately identify headings across various PDF layouts.

Getting Started
To use this tool, first, ensure you have Python 3.8+ installed. Begin by cloning the repository and navigating into its directory. Create and activate a virtual environment, then install the necessary dependency, PyMuPDF, using pip install PyMuPDF. Next, place all your PDF files into an input/ folder located at the project root. Finally, run the script with python main.py. The extracted outlines, in JSON format, will then be available in the newly created output/ folder within the same directory
