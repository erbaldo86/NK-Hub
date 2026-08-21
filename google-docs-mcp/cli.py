import sys
import argparse
from server import get_docs_service

def read_doc(doc_id):
    service = get_docs_service()
    doc = service.documents().get(documentId=doc_id).execute()
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
    sys.stdout.buffer.write(text.encode('utf-8'))

def write_doc(doc_id, text_to_append):
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
    service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
    print(f"Testo aggiunto con successo! ({len(text_to_append)} caratteri)")

def overwrite_doc(doc_id, text_to_insert):
    service = get_docs_service()
    doc = service.documents().get(documentId=doc_id).execute()
    body_content = doc.get('body').get('content')
    end_index = body_content[-1].get('endIndex') - 1 if body_content else 1
    
    requests = []
    if end_index > 1:
        requests.append({
            'deleteContentRange': {
                'range': {
                    'startIndex': 1,
                    'endIndex': end_index
                }
            }
        })
    requests.append({
        'insertText': {
            'location': {
                'index': 1,
            },
            'text': text_to_insert + "\n"
        }
    })
    service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
    print(f"Documento sovrascritto con successo! ({len(text_to_insert)} caratteri)")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['read', 'write', 'overwrite'])
    parser.add_argument('doc_id')
    parser.add_argument('--text', default='')
    parser.add_argument('--file', default=None, help='Path al file da cui leggere il testo')
    args = parser.parse_args()
    
    try:
        if args.file:
            with open(args.file, 'r', encoding='utf-8') as f:
                input_text = f.read()
        else:
            input_text = args.text

        if args.action == 'read':
            read_doc(args.doc_id)
        elif args.action == 'write':
            write_doc(args.doc_id, input_text)
        elif args.action == 'overwrite':
            overwrite_doc(args.doc_id, input_text)
    except Exception as e:
        print(f"ERRORE: {str(e)}", file=sys.stderr)
        sys.exit(1)
