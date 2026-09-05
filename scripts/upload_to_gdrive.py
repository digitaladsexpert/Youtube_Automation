import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDS_PATH = 'secrets/credentials.json'
TOKEN_PATH = 'secrets/token.pickle'

def get_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)
    return build('drive', 'v3', credentials=creds)

def find_or_create_folder(service, name, parent_id=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    else:
        meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_id:
            meta['parents'] = [parent_id]
        folder = service.files().create(body=meta, fields='id').execute()
        return folder.get('id')

def upload_job_to_gdrive(job_id, local_path):
    service = get_service()
    main_folder_id = find_or_create_folder(service, "YouTube_Production_Outputs")
    job_folder_id = find_or_create_folder(service, job_id, main_folder_id)
    for file in os.listdir(local_path):
        file_path = os.path.join(local_path, file)
        if os.path.isfile(file_path):
            media = MediaFileUpload(file_path, resumable=True)
            meta = {'name': file, 'parents': [job_folder_id]}
            service.files().create(body=meta, media_body=media, fields='id').execute()
    return {
        "gdrive_folder": f"https://drive.google.com/drive/folders/{job_folder_id}",
        "status": "UPLOADED"
    }