import os
from mcp.server.fastmcp import FastMCP
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import httplib2
import urllib3
import requests
import logging

class IgnoreValidationErrors(logging.Filter):
    def filter(self, record):
        if "Failed to validate request:" in record.getMessage() and "server/discover" in record.getMessage():
            return False
        return True

logging.getLogger().addFilter(IgnoreValidationErrors())

# Disabilita gli avvisi per le richieste HTTPS senza verifica del certificato
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCOPES = ['https://www.googleapis.com/auth/documents']

# Inizializza il server MCP
mcp = FastMCP("Google Docs MCP Server")

def get_docs_service():
    """Autentica e restituisce il servizio Google Docs usando i token preesistenti."""
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), 'token.json')
    
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Creiamo una Request che non verifica SSL per il refresh del token
            session = requests.Session()
            session.verify = False
            unverified_request = Request(session=session)
            creds.refresh(unverified_request)
            # Salva le nuove credenziali
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        else:
            raise Exception("Nessun token valido trovato. Esegui prima 'python auth.py' per autenticarti dal tuo terminale.")

    # Creiamo un trasporto HTTP httplib2 che non verifica SSL per le chiamate API
    http = httplib2.Http(disable_ssl_certificate_validation=True)
    authorized_http = creds.authorize(http)
    return build('docs', 'v1', http=authorized_http)

@mcp.tool()
def read_google_doc(document_id: str) -> str:
    """Legge e restituisce tutto il contenuto testuale di un Google Doc.
    
    Args:
        document_id: L'ID del documento Google (la stringa lunga nell'URL del documento).
    """
    try:
        service = get_docs_service()
        doc = service.documents().get(documentId=document_id).execute()
        
        text = ""
        content = doc.get('body', {}).get('content', [])
        for element in content:
            if 'paragraph' in element:
                elements = element.get('paragraph').get('elements', [])
                for elem in elements:
                    text_run = elem.get('textRun')
                    if text_run:
                        text += text_run.get('content')
            elif 'table' in element:
                for row in element.get('table').get('tableRows', []):
                    for cell in row.get('tableCells', []):
                        for cell_content in cell.get('content', []):
                            if 'paragraph' in cell_content:
                                elements = cell_content.get('paragraph').get('elements', [])
                                for elem in elements:
                                    text_run = elem.get('textRun')
                                    if text_run:
                                        text += text_run.get('content')
                    text += "\n"
        return text
    except Exception as e:
        return f"Errore durante la lettura del documento: {str(e)}"

@mcp.tool()
def append_to_google_doc(document_id: str, text_to_append: str) -> str:
    """Aggiunge del testo alla fine di un Google Doc esistente.
    
    Args:
        document_id: L'ID del documento Google (la stringa lunga nell'URL del documento).
        text_to_append: Il testo da inserire.
    """
    try:
        service = get_docs_service()
        
        requests = [
            {
                'insertText': {
                    'endOfSegmentLocation': {
                        'segmentId': ''
                    },
                    'text': text_to_append + "\n"
                }
            }
        ]
        
        service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()
        return f"Testo aggiunto con successo! ({len(text_to_append)} caratteri)"
    except Exception as e:
        return f"Errore durante l'aggiunta al documento: {str(e)}"

if __name__ == "__main__":
    # Avvia il server MCP su stdio
    mcp.run()
