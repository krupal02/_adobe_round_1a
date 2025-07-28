import fitz  # PyMuPDF
import json
import os
import re
from collections import Counter

def analyze_document_fonts(document):
    """
    Analyzes the entire PDF document to identify common font sizes and their usage.
    This helps in dynamically determining heading font size thresholds.
    Returns a list of font sizes sorted by their prevalence (total text length).
    """
    font_size_usage = Counter()
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font_size = round(span.get("size", 0))
                        text_content = span.get("text", "").strip()
                        if font_size > 0 and text_content:
                            font_size_usage[font_size] += len(text_content) # Summing length gives weight to more used sizes
    
    # Filter out very small font sizes (likely body text, footers, etc.)
    # and sort by usage (desc) then by font size (desc)
    filtered_sizes = {fs: usage for fs, usage in font_size_usage.items() if fs > 9} # Assuming 9pt is min for body text
    sorted_unique_font_sizes = sorted(filtered_sizes.keys(), key=lambda fs: (filtered_sizes[fs], fs), reverse=True)
    
    return sorted_unique_font_sizes

def determine_heading_thresholds(sorted_font_sizes):
    """
    Determines H1, H2, H3 font size thresholds based on the analyzed font sizes.
    """
    H1_threshold = 24 # Default large value
    H2_threshold = 18 # Default medium value
    H3_threshold = 14 # Default small value
    BODY_TEXT_MAX_SIZE = 12 # Common body text size
    
    # Try to find distinct large font sizes
    large_sizes = [fs for fs in sorted_font_sizes if fs > BODY_TEXT_MAX_SIZE]

    if len(large_sizes) >= 3:
        H1_threshold = large_sizes[0]
        H2_threshold = large_sizes[1]
        H3_threshold = large_sizes[2]
    elif len(large_sizes) == 2:
        H1_threshold = large_sizes[0]
        H2_threshold = large_sizes[1]
        H3_threshold = large_sizes[1] # H3 same as H2
    elif len(large_sizes) == 1:
        H1_threshold = large_sizes[0]
        H2_threshold = large_sizes[0]
        H3_threshold = large_sizes[0] # All same if only one distinct large size
    
    # Ensure thresholds are descending or equal
    H2_threshold = min(H2_threshold, H1_threshold)
    H3_threshold = min(H3_threshold, H2_threshold)

    # If dynamic detection yields very small values, ensure they are at least somewhat distinct from body text
    H1_threshold = max(H1_threshold, BODY_TEXT_MAX_SIZE + 2)
    H2_threshold = max(H2_threshold, BODY_TEXT_MAX_SIZE + 1)
    H3_threshold = max(H3_threshold, BODY_TEXT_MAX_SIZE) # H3 can be body text size if bold
    
    return H1_threshold, H2_threshold, H3_threshold, BODY_TEXT_MAX_SIZE

def extract_title_from_document(document, h1_threshold):
    """
    Attempts to extract the main title from the first few pages of the PDF.
    It looks for the largest and most prominent text block.
    """
    potential_titles = []
    max_font_size_found = 0

    # Check the first two pages for the title
    for page_num in range(min(len(document), 2)):
        page = document.load_page(page_num)
        blocks = page.get_text("dict").get("blocks", [])
        
        # Sort blocks top-to-bottom, then left-to-right for consistency
        blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        for block in blocks:
            if block.get("type") == 0: # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text_content = span.get("text", "").strip()
                        font_size = round(span.get("size", 0))
                        is_bold = "bold" in span.get("font", "").lower() or "black" in span.get("font", "").lower()

                        if text_content and font_size > 0:
                            if font_size > max_font_size_found:
                                max_font_size_found = font_size
                                potential_titles = [(text_content, font_size, page_num, is_bold)]
                            elif font_size == max_font_size_found:
                                potential_titles.append((text_content, font_size, page_num, is_bold))

    if not potential_titles:
        return None

    # Sort potential titles: largest font, then earliest page, then bold preferred, then longest text
    potential_titles.sort(key=lambda x: (-x[1], x[2], -x[3], -len(x[0])))

    # Select the most likely candidate based on heuristics
    for text, size, page_num, is_bold in potential_titles:
        # A good title is usually on the first page, reasonably long, and often very large/bold
        if page_num == 0 and len(text.split()) > 2 and size >= h1_threshold * 0.8: # Must be near H1 size
            # Filter out common headers/footers if they got picked up as max_font_size
            if not re.match(r"^\d+$", text) and \
               "contents" not in text.lower() and \
               "page" not in text.lower():
                return text.split('\n')[0].strip() # Return only the first line

    # Fallback: If no strong candidate, take the absolute largest font on first page
    if potential_titles and potential_titles[0][2] == 0: # Check if the very first candidate is on page 0
        return potential_titles[0][0].split('\n')[0].strip()

    return None

def is_heading_candidate(text, font_size, font_name, h1_th, h2_th, h3_th, body_max_size):
    """
    Checks if a text span is a strong candidate for a heading.
    """
    if not text or len(text) < 2: # Ignore empty or very short strings
        return False

    # Common non-heading text patterns (page numbers, dates, URLs, single symbols, etc.)
    if re.match(r"^\s*\d+(\.\d+)*\s*$", text) or \
       re.match(r"^(page|pg\.)\s+\d+(\s+of\s+\d+)?$", text.lower()) or \
       re.match(r"^\d{1,2}\s+[a-zA-Z]{3,}\s+\d{4}$", text) or \
       "copyright" in text.lower() or \
       "www." in text.lower() or \
       re.match(r"^\(continued\)$", text.lower()) or \
       re.match(r"^\s*[\W_]+\s*$", text) or \
       re.match(r"^[ivxlcdm]+\.?$", text.lower()) : # Roman numerals
        return False

    # Check for bold attribute
    is_bold = "bold" in font_name.lower() or "black" in font_name.lower() or "heavy" in font_name.lower() or "demi" in font_name.lower()

    # Heuristic: Text that is not very bold and is small is likely not a heading
    if not is_bold and font_size <= body_max_size:
        return False
    
    # Text must be sufficiently large
    if font_size < h3_th * 0.9: # Allow a small margin
        return False

    return True

def get_heading_level(font_size, is_bold, h1_th, h2_th, h3_th):
    """
    Assigns a heading level (H1, H2, H3) based on font size and boldness.
    """
    if font_size >= h1_th and is_bold:
        return "H1"
    elif font_size >= h2_th and is_bold:
        return "H2"
    elif font_size >= h3_th and is_bold:
        return "H3"
    # Specific common sections that are often H1 even if not perfectly matching dynamic thresholds
    # if ("table of contents" in text.lower() or "revision history" in text.lower() or
    #     "references" in text.lower() or "appendix" in text.lower()) and font_size >= h2_th:
    #     return "H1"
    
    return None

def extract_outline_from_pdf(pdf_path):
    """
    Extracts the title and a hierarchical outline (H1, H2, H3) from a PDF.
    """
    try:
        document = fitz.open(pdf_path)
    except Exception as e:
        raise IOError(f"Could not open PDF {pdf_path}: {e}")

    # Step 1: Analyze fonts to determine dynamic thresholds
    sorted_font_sizes = analyze_document_fonts(document)
    h1_th, h2_th, h3_th, body_max_size = determine_heading_thresholds(sorted_font_sizes)
    
    # Step 2: Extract main title
    extracted_title = extract_title_from_document(document, h1_th)
    if not extracted_title:
        # Fallback to filename if no good title is found
        extracted_title = os.path.basename(pdf_path).replace(".pdf", "").replace("_", " ").title()

    outline = []
    last_added_heading = {"text": "", "level": "", "page": -1} # To prevent immediate duplicates

    # Step 3: Iterate through pages and extract headings
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        blocks = page.get_text("dict").get("blocks", [])

        # Sort blocks by their top coordinate, then by left coordinate
        blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        for block in blocks:
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    # Group spans within a line to reconstruct full text of a potential heading
                    full_line_text = " ".join([span.get("text", "") for span in line.get("spans", [])]).strip()
                    
                    if not full_line_text:
                        continue

                    # Use the properties of the first span as representative for the line's style
                    first_span = line.get("spans", [{}])[0]
                    span_font_size = round(first_span.get("size", 0))
                    span_font_name = first_span.get("font", "").lower()
                    
                    is_bold = "bold" in span_font_name or "black" in span_font_name or "heavy" in span_font_name or "demi" in span_font_name

                    if not is_heading_candidate(full_line_text, span_font_size, span_font_name, h1_th, h2_th, h3_th, body_max_size):
                        continue

                    level = get_heading_level(span_font_size, is_bold, h1_th, h2_th, h3_th)
                    
                    # Special check for known sections that might be H1 regardless of strict size/boldness
                    if not level:
                        lower_text = full_line_text.lower()
                        if "table of contents" in lower_text or \
                           "list of figures" in lower_text or \
                           "list of tables" in lower_text or \
                           "acknowledgements" in lower_text or \
                           "foreword" in lower_text or \
                           "preface" in lower_text or \
                           "introduction" in lower_text and span_font_size >= h2_th * 0.9: # Allow for slight variation
                            level = "H1"
                        elif "references" in lower_text or \
                             "bibliography" in lower_text or \
                             "appendix" in lower_text or \
                             "glossary" in lower_text or \
                             "index" in lower_text:
                            level = "H1"

                    if level:
                        # Prevent immediate duplicate headings (e.g., if a heading repeats on the same line due to formatting)
                        if not outline or \
                           (full_line_text != last_added_heading["text"] or \
                            level != last_added_heading["level"] or \
                            page_num + 1 != last_added_heading["page"]):
                            
                            new_entry = {"level": level, "text": full_line_text, "page": page_num + 1}
                            outline.append(new_entry)
                            last_added_heading = new_entry.copy()
    
    document.close()
    return {"title": extracted_title, "outline": outline}

def process_pdfs_in_directory(input_dir, output_dir):
    """
    Processes all PDF files in the input directory and saves JSON outlines
    to the output directory.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    processed_count = 0
    error_count = 0

    for filename in os.listdir(input_dir):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(input_dir, filename)
            output_filename = os.path.splitext(filename)[0] + ".json"
            output_path = os.path.join(output_dir, output_filename)

            print(f"Processing '{filename}'...")
            try:
                outline_data = extract_outline_from_pdf(pdf_path)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(outline_data, f, indent=2, ensure_ascii=False)
                print(f"  -> Successfully processed to '{output_filename}'")
                processed_count += 1
            except Exception as e:
                print(f"  -> ERROR processing '{filename}': {e}")
                error_count += 1
            print("-" * 60) # Separator for readability
    
    print(f"\n--- Processing Summary ---")
    print(f"Total PDFs found: {len([f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')])}")
    print(f"Successfully processed: {processed_count}")
    print(f"Failed to process: {error_count}")
    print("--------------------------")

if __name__ == "__main__":
    # Define input and output directories
    # These paths are relative to where you run the script.
    # For example, if your script is in /my_project/, then:
    #   - PDFs should be in /my_project/input_pdfs/
    #   - JSON outputs will be in /my_project/output_json/
    INPUT_DIR = "input_pdfs"
    OUTPUT_DIR = "output_json"

    print("--- PDF Outline Extractor ---")
    print(f"Input PDFs expected in: '{os.path.abspath(INPUT_DIR)}'")
    print(f"Output JSONs will be saved to: '{os.path.abspath(OUTPUT_DIR)}'")
    print("-----------------------------\n")

    # Create directories if they don't exist
    for directory in [INPUT_DIR, OUTPUT_DIR]:
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
                print(f"Created directory: '{directory}'")
            except OSError as e:
                print(f"Error creating directory '{directory}': {e}")
                print("Please ensure you have write permissions to the location, or manually create the directory.")
                exit(1) # Exit if critical directories cannot be created

    process_pdfs_in_directory(INPUT_DIR, OUTPUT_DIR)