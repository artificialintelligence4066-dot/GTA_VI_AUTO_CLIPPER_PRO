import asyncio, json, time, uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import config, database
from .security import extract_video_id_safe
from .chat_monitor import LiveChatMonitor
from .video_processor import download_segment, render_vertical_short
from .transcriber import transcribe_clip
from .ai_metadata import generate_viral_metadata
from .youtube_uploader import is_authenticated, authenticate_youtube, upload_short_to_youtube

app=FastAPI(title='GTA VI Auto-Clipper Pro',version='2.1.0')
app.add_middleware(CORSMiddleware,allow_origins=config.CORS_ORIGINS,allow_credentials=False,allow_methods=['GET','POST','PATCH','OPTIONS'],allow_headers=['Content-Type','X-API-Key'])
app.mount('/clips',StaticFiles(directory=str(config.CLIPS_DIR)),name='clips')
ws_clients:set[WebSocket]=set(); request_windows=defaultdict(deque); active_monitor:Optional[LiveChatMonitor]=None; monitor_task=None
active_config={}; job_queue:asyncio.Queue=asyncio.Queue(); worker_tasks=[]; semaphore=None

class StartRequest(BaseModel):
    video_url:str
    streamer_credit:str='@Streamer'
    auto_upload:bool=False
    privacy_status:str='unlisted'
    spike_multiplier:float=Field(default=2.5,ge=1.1,le=20)
    min_mpm:int=Field(default=40,ge=1,le=100000)
    layout_mode:str='blur_zoom'
class ClipRequest(BaseModel):
    video_url:str
    streamer_credit:str='@Streamer'
    start_sec:int=Field(default=0,ge=0)
    duration:int=Field(default=30,ge=5,le=180)
    auto_upload:bool=False
    privacy_status:str='unlisted'
    layout_mode:str='blur_zoom'

async def broadcast(data):
    dead=[]
    for ws in list(ws_clients):
        try: await ws.send_json(data)
        except Exception: dead.append(ws)
    for ws in dead: ws_clients.discard(ws)

async def enqueue_job(payload):
    job_id='job_'+uuid.uuid4().hex[:12]
    database.create_job(job_id,payload); database.add_event('job_created',{'id':job_id,'source':payload.get('source','manual')})
    await job_queue.put((job_id,payload)); await broadcast({'type':'job_update','job':{'id':job_id,'status':'pending','created_at':time.time()}})
    return job_id

async def process_pipeline(job_id,event):
    clip_id='clip_'+uuid.uuid4().hex[:12]; raw=config.TEMP_DIR/f'{clip_id}_raw.mp4'; final=config.CLIPS_DIR/f'{clip_id}.mp4'
    database.update_job(job_id,'processing'); await broadcast({'type':'job_update','job':{'id':job_id,'status':'processing'}})
    try:
        await broadcast({'type':'log','level':'info','message':f'[{clip_id}] Downloading source segment'})
        await asyncio.to_thread(download_segment,event['video_url'],raw,event.get('duration',config.CLIP_DURATION_SECONDS),event.get('is_live',False),event.get('start_sec'))
        transcript,ass=await asyncio.to_thread(transcribe_clip,raw,clip_id)
        await asyncio.to_thread(render_vertical_short,raw,final,event.get('streamer_credit','@Streamer'),ass,event.get('layout_mode','blur_zoom'))
        metadata=await asyncio.to_thread(generate_viral_metadata,transcript,event.get('top_chat',[]),event.get('streamer_credit','@Streamer'))
        clip={'id':clip_id,'created_at':time.time(),'video_url':f'/clips/{clip_id}.mp4','source_url':event['video_url'],'streamer_credit':event.get('streamer_credit','@Streamer'),'title':metadata['selected_title'],'description':metadata['description'],'tags':metadata['tags'],'hashtags':metadata.get('hashtags',[]),'viral_score':metadata['viral_score'],'hook_reason':metadata.get('score_reason',''),'transcript':transcript,'mpm':event.get('mpm',0),'spike_ratio':event.get('spike_ratio',0),'upload_status':'ready','youtube_url':None,'ai_fallback':metadata.get('ai_fallback',False)}
        if event.get('auto_upload'):
            try:
                result=await asyncio.to_thread(upload_short_to_youtube,final,clip['title'],clip['description'],clip['tags'],event.get('privacy_status','unlisted'))
                clip['upload_status']='uploaded'; clip['youtube_url']=result['youtube_url']
            except Exception as exc: clip['upload_status']='upload_failed'; clip['upload_error']=str(exc)[:400]
        database.save_clip(clip); database.update_job(job_id,'completed'); database.add_event('clip_completed',{'clip_id':clip_id,'job_id':job_id})
        await broadcast({'type':'clip_ready','clip':clip}); await broadcast({'type':'log','level':'success','message':f'Clip ready: {clip_id}'})
    except Exception as exc:
        database.update_job(job_id,'failed',str(exc)[:1000]); database.add_event('job_failed',{'job_id':job_id,'error':str(exc)[:300]})
        await broadcast({'type':'job_update','job':{'id':job_id,'status':'failed','error':str(exc)[:300]}}); await broadcast({'type':'log','level':'error','message':f'Job failed: {str(exc)[:300]}'})
    finally:
        for p in (raw,config.TEMP_DIR/f'{clip_id}.wav',config.TEMP_DIR/f'{clip_id}.ass'):
            try: p.unlink(missing_ok=True)
            except OSError: pass

async def worker():
    while True:
        job_id,payload=await job_queue.get()
        try: await process_pipeline(job_id,payload)
        finally: job_queue.task_done()

async def spike_callback(event):
    # The monitor only enqueues; clip work runs in separate worker(s).
    event.update(active_config); event['source']='live_spike'; event.setdefault('duration',config.CLIP_DURATION_SECONDS)
    await enqueue_job(event)

@app.on_event('startup')
async def startup():
    database.init_db()
    global worker_tasks
    # Recover interrupted jobs into pending state after process restart.
    for job in database.list_jobs():
        if job['status'] in ('pending','processing'):
            database.update_job(job['id'],'pending'); await job_queue.put((job['id'],job['payload']))
    worker_tasks=[asyncio.create_task(worker()) for _ in range(config.MAX_CONCURRENT_JOBS)]

@app.on_event('shutdown')
async def shutdown():
    for task in worker_tasks: task.cancel()
    if active_monitor: active_monitor.stop()

def require_key(x_api_key):
    if config.API_AUTH_KEY and x_api_key != config.API_AUTH_KEY: raise HTTPException(status_code=401,detail='Missing or invalid API key')

@app.middleware('http')
async def auth_middleware(request:Request,call_next):
    from starlette.responses import JSONResponse
    if config.API_AUTH_KEY and request.url.path.startswith('/api/') and request.url.path != '/api/health':
        if request.headers.get('x-api-key') != config.API_AUTH_KEY:
            return JSONResponse({'detail':'Missing or invalid API key'},status_code=401)
    if request.url.path.startswith('/api/'):
        now=time.time(); bucket=request_windows[request.client.host if request.client else 'local']
        while bucket and now-bucket[0] > 60: bucket.popleft()
        if len(bucket) >= config.RATE_LIMIT_PER_MINUTE:
            return JSONResponse({'detail':'Rate limit exceeded; retry in a minute.'},status_code=429)
        bucket.append(now)
    return await call_next(request)

@app.get('/api/health')
def health(): return {'status':'ok','monitoring':bool(active_monitor and active_monitor.running),'youtube_connected':is_authenticated(),'gemini_configured':bool(config.GEMINI_API_KEY),'groq_configured':bool(config.GROQ_API_KEY),'queue_size':job_queue.qsize(),'version':'2.2.0','storage_path':str(config.DATA_DIR),'render_quality':{'preset':config.FFMPEG_PRESET,'crf':config.FFMPEG_CRF}}
@app.get('/api/settings')
def settings(): return {'settings':{'clip_duration':config.CLIP_DURATION_SECONDS,'spike_multiplier':config.SPIKE_MULTIPLIER,'min_mpm':config.MIN_MPM_THRESHOLD,'max_concurrent_jobs':config.MAX_CONCURRENT_JOBS,'layout_mode':'blur_zoom','auth_enabled':bool(config.API_AUTH_KEY)}}
@app.patch('/api/settings')
def update_settings(payload:dict): return {'settings':settings()['settings'],'message':'Runtime settings are environment-configured; edit backend/.env and restart to change them.'}
@app.get('/api/presets')
def presets(): return {'layouts':['blur_zoom','center_crop'],'privacy':['private','unlisted','public'],'durations':[15,30,45,60]}
@app.get('/api/clips')
def clips(): return {'clips':database.list_clips()}
@app.get('/api/jobs')
def jobs(): return {'jobs':database.list_jobs()}
@app.get('/api/events')
def events(): return {'events':database.list_events()}
@app.get('/api/analytics')
def analytics():
    cs=database.list_clips(); js=database.list_jobs()
    return {'total_clips':len(cs),'completed_jobs':sum(j['status']=='completed' for j in js),'failed_jobs':sum(j['status']=='failed' for j in js),'pending_jobs':sum(j['status']=='pending' for j in js),'uploaded_clips':sum(c.get('upload_status')=='uploaded' for c in cs)}
@app.post('/api/start')
async def start(req:StartRequest):
    global active_monitor,monitor_task,active_config
    try: extract_video_id_safe(req.video_url)
    except ValueError as e: raise HTTPException(400,str(e))
    if active_monitor: active_monitor.stop()
    active_config={'streamer_credit':req.streamer_credit,'auto_upload':req.auto_upload,'privacy_status':req.privacy_status,'layout_mode':req.layout_mode}
    active_monitor=LiveChatMonitor(req.video_url,broadcast,spike_callback,req.spike_multiplier,req.min_mpm,config.MIN_UNIQUE_AUTHORS,config.CLIP_COOLDOWN_SECONDS)
    monitor_task=asyncio.create_task(active_monitor.start())
    return {'status':'started','video_id':active_monitor.video_id}
@app.post('/api/stop')
async def stop():
    global active_monitor
    if active_monitor: active_monitor.stop(); active_monitor=None
    return {'status':'stopped'}
@app.post('/api/clip-now')
async def clip_now(req:ClipRequest):
    try: extract_video_id_safe(req.video_url)
    except ValueError as e: raise HTTPException(400,str(e))
    payload=req.model_dump(); payload.update({'is_live':False,'source':'manual','top_chat':[]})
    job_id=await enqueue_job(payload)
    return {'status':'queued','job_id':job_id,'message':'Clip job added to the persistent queue'}
@app.post('/api/upload/{clip_id}')
async def upload(clip_id:str,privacy_status:str='unlisted'):
    clip=next((c for c in database.list_clips() if c['id']==clip_id),None)
    if not clip: raise HTTPException(404,'Clip not found')
    path=config.CLIPS_DIR/f'{clip_id}.mp4'
    if not path.is_file(): raise HTTPException(404,'Clip file missing')
    try:
        result=await asyncio.to_thread(upload_short_to_youtube,path,clip['title'],clip['description'],clip['tags'],privacy_status)
        clip.update({'upload_status':'uploaded','youtube_url':result['youtube_url']}); database.save_clip(clip); await broadcast({'type':'clip_updated','clip':clip}); return result
    except Exception as e: raise HTTPException(400,str(e))
@app.post('/api/auth/youtube')
async def youtube_auth():
    try: await asyncio.to_thread(authenticate_youtube); return {'connected':True}
    except Exception as e: raise HTTPException(400,str(e))
@app.websocket('/ws')
async def websocket_endpoint(ws:WebSocket):
    if config.API_AUTH_KEY and ws.query_params.get('key') != config.API_AUTH_KEY:
        await ws.close(code=1008); return
    await ws.accept(); ws_clients.add(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: ws_clients.discard(ws)


# Serve the built mobile dashboard from the same origin in cloud deployments.
# API routes and /clips are registered above and keep precedence.
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="dashboard")
