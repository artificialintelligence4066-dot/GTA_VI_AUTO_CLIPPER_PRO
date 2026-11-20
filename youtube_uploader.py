from . import config

def _service():
    if not config.YOUTUBE_CLIENT_SECRETS.exists():
        raise RuntimeError('YouTube OAuth is not configured. Add client_secrets.json to backend/.')
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    scopes=['https://www.googleapis.com/auth/youtube.upload']
    creds=None
    if config.YOUTUBE_TOKEN_FILE.exists(): creds=Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_FILE),scopes)
    if creds and creds.expired and creds.refresh_token: creds.refresh(Request())
    if not creds or not creds.valid:
        flow=InstalledAppFlow.from_client_secrets_file(str(config.YOUTUBE_CLIENT_SECRETS),scopes)
        creds=flow.run_local_server(port=0)
        config.YOUTUBE_TOKEN_FILE.write_text(creds.to_json(),encoding='utf-8')
    return build('youtube','v3',credentials=creds)

def is_authenticated():
    return config.YOUTUBE_TOKEN_FILE.exists()

def authenticate_youtube():
    _service(); return True

def upload_short_to_youtube(video_path,title,description,tags,privacy_status='unlisted'):
    from googleapiclient.http import MediaFileUpload
    if privacy_status not in {'private','unlisted','public'}: raise ValueError('Invalid privacy status')
    body={'snippet':{'title':title[:100],'description':description[:5000],'tags':tags[:30],'categoryId':'20'},'status':{'privacyStatus':privacy_status,'selfDeclaredMadeForKids':False}}
    response=_service().videos().insert(part='snippet,status',body=body,media_body=MediaFileUpload(str(video_path),chunksize=-1,resumable=True)).execute()
    vid=response['id']
    return {'youtube_url':f'https://www.youtube.com/watch?v={vid}','video_id':vid}
