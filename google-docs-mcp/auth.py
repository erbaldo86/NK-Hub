import os
import sys
import shutil
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Usiamo lo scope generale per i documenti in modo da poter leggere e scrivere
SCOPES = ['https://www.googleapis.com/auth/documents']

def authenticate(force=False):
    token_path = os.path.join(os.path.dirname(__file__), 'token.json')
    credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')

    if not force and os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if creds and creds.valid:
                print("Un token valido esiste già ed è attivo! Sei già autenticato. Puoi avviare il server MCP.")
                return
        except Exception:
            pass

    if not os.path.exists(credentials_path):
        print(f"ERRORE: Il file {credentials_path} non esiste.")
        print("Aggiungi il tuo file credentials.json (Client ID OAuth 2.0) in questa cartella.")
        print("Se hai usato un Service Account per il tuo programma, fammelo sapere e adattero' il server per usarlo senza bisogno di questa autenticazione interattiva.")
        return

    print("Avvio il processo di autenticazione. Controlla il tuo browser...")
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open(token_path, 'w') as token:
        token.write(creds.to_json())
    
    # Sincronizza token tra C: e G: per coerenza
    alt_dirs = [
        r"G:\Il mio Drive\Antigravity\google-docs-mcp",
        r"C:\Users\erbal\.gemini\antigravity\servers\google-docs-mcp"
    ]
    for alt_dir in alt_dirs:
        if os.path.exists(alt_dir):
            alt_token = os.path.join(alt_dir, 'token.json')
            if os.path.abspath(alt_token) != os.path.abspath(token_path):
                try:
                    shutil.copy2(token_path, alt_token)
                except Exception:
                    pass

    print("Autenticazione completata con successo! È stato creato/aggiornato il file token.json.")
    print("Ora puoi utilizzare il server MCP per Google Docs.")

if __name__ == '__main__':
    force_mode = '--force' in sys.argv or '-f' in sys.argv
    authenticate(force=force_mode)
