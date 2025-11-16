import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def download_pdfs_from_page(page_url, match_text, download_folder="pdf_downloads"):
    """
    Downloads PDFs from a webpage whose link text matches a given string.

    Args:
        page_url (str): The URL of the webpage to scan.
        match_text (str): Substring to match in the link text.
        download_folder (str): Folder to save downloaded PDFs (default: "pdf_downloads").
    """
    # Create folder if it doesn't exist
    os.makedirs(download_folder, exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://science.osti.gov/",
    }

    # Get webpage content
    print(f"Fetching page: {page_url}")
    response = requests.get(page_url, headers=headers)
    response.raise_for_status()  # Ensure request succeeded

    # Parse HTML
    soup = BeautifulSoup(response.text, "html.parser")

    # Find all links
    links = soup.find_all("a", href=True)

    # Iterate over matching links
    for link in links:
        link_text = link.get_text(strip=True)
        href = link["href"]

        # Match link text to given string
        if re.search(match_text, link_text, re.IGNORECASE):
            pdf_url = urljoin(page_url, href)
            print(f"\nFound matching link:")
            print(f"Text: {link_text}")
            print(f"URL:  {pdf_url}")

            try:
                # Get the headers first to check content type
                print("Checking content type...")
                head_response = requests.head(pdf_url, allow_redirects=True, headers=headers)
                content_type = head_response.headers.get('content-type', '').lower()
                
                if 'pdf' in content_type:
                    # Create a base safe filename from the link text
                    safe_filename = "".join([c for c in link_text if c.isalpha() or c.isdigit() or c==' ']).rstrip()
                    safe_filename = safe_filename.replace(' ', '_')
                    
                    # Handle duplicate filenames
                    filename = os.path.join(download_folder, f"{safe_filename}.pdf")
                    counter = 1
                    while os.path.exists(filename):
                        filename = os.path.join(download_folder, f"{safe_filename}_{counter}.pdf")
                        counter += 1
                    
                    print(f"Downloading PDF to: {filename}")
                    pdf_data = requests.get(pdf_url, headers=headers)
                    pdf_data.raise_for_status()
                    
                    with open(filename, "wb") as f:
                        f.write(pdf_data.content)
                    print("✅ Download complete.")
                else:
                    print(f"Skipping - Not a PDF (Content-Type: {content_type})")
                    
            except Exception as e:
                print(f"❌ Error processing {pdf_url}: {str(e)}")

if __name__ == "__main__":
    # Example usage:
    # Replace with your page URL and text to match
    url = "https://science.osti.gov/wdts/nsb/Regional-Competitions/Resources/MS-Sample-Questions"
    match_pattern = "Round"   # Text to look for in the link (case-insensitive)
    download_pdfs_from_page(url, match_pattern)
