from connectors.pdf_connector import run as run_pdf
from connectors.scanned_pdf_connector import run as run_scanned_pdf
from connectors.json_connector import run as run_json

if __name__ == "__main__":
    print("Running PDF connector...")
    run_pdf()
    print("Running Scanned PDF connector...")
    run_scanned_pdf()
    print("Running JSON connector...")
    run_json()
    print("Pipeline completed successfully.")