import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Usiamo lo scope generale per i documenti in modo da poter leggere e scrivere
SCOPES = ['https://www.googleapis.com/auth/documents']

def authenticate():
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), 'token.json')
    credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')

    if os.path.exists(token_path):
        print("Un token valido esiste già! Sei già autenticato. Puoi avviare il server MCP.")
        return

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
    
    print("Autenticazione completata con successo! È stato creato il file token.json.")
    print("Ora puoi configurare questo server nel tuo ambiente Antigravity.")

if __name__ == '__main__':
    authenticate()
