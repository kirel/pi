"""Run inside Home Assistant; JSON stdin holds token, route and unique test name.

Starts at intent (no microphone/STT), consumes TTS bytes without playing a speaker.
"""
import asyncio,aiohttp,json,sys,time
async def main():
 cfg=json.load(sys.stdin);route=cfg['route'];name=cfg['name'];start=time.monotonic()
 text=[];timings={};audio_task=None
 route_instruction=('Nutze den Einkaufsliste-Skill und ausschließlich shopping_snapshot und shopping_apply.' if route=='n8n' else 'Nutze den Einkaufsliste-Skill, seine Referenz official-todoist.md und ausschließlich die offiziellen todoist-Tools, nicht shopping_snapshot oder shopping_apply.')
 prompt=(f'Kontrollierter Einkaufsliste-Test: Füge genau einen Artikel mit dem unveränderten vollständigen Namen "{name}" '
         f'und der Beschreibung "temporärer Sprachbenchmark" zur Sektion Woanders hinzu. {route_instruction} '
         'Erst nach verifiziertem Erfolg sage nur: Testartikel eingetragen. Falls nicht möglich, melde den Fehler. Keine anderen Artikel verändern.')
 async with aiohttp.ClientSession(headers={'Authorization':'Bearer '+cfg['token']}) as s:
  async def audio(url):
   async with s.get('http://127.0.0.1:8123'+url) as r:
    r.raise_for_status();count=0
    async for chunk in r.content.iter_chunked(2048):
     if chunk and 'first_audio_s' not in timings:timings['first_audio_s']=time.monotonic()-start
     count+=len(chunk)
    timings['audio_complete_s']=time.monotonic()-start;timings['audio_bytes']=count
  async with s.ws_connect('http://127.0.0.1:8123/api/websocket') as w:
   await w.receive_json();await w.send_json({'type':'auth','access_token':cfg['token']});assert (await w.receive_json())['type']=='auth_ok'
   start=time.monotonic();timings['started_unix']=time.time()
   await w.send_json({'id':1,'type':'assist_pipeline/run','pipeline':'01kvrqersdf1m8pen8635te58q','start_stage':'intent','end_stage':'tts','input':{'text':prompt}})
   while True:
    m=await asyncio.wait_for(w.receive_json(),240)
    if m.get('type')=='result':assert m.get('success');continue
    event=m.get('event',{});typ=event.get('type');d=event.get('data') or {}
    if typ=='error':raise RuntimeError(d.get('code','pipeline_error'))
    if typ=='run-start' and d.get('tts_output',{}).get('url'):audio_task=asyncio.create_task(audio(d['tts_output']['url']))
    if typ=='intent-progress':
     chunk=d.get('chat_log_delta',{}).get('content')
     if chunk:
      if not text:timings['first_text_s']=time.monotonic()-start
      text.append(chunk)
    if typ=='intent-end':timings['intent_complete_s']=time.monotonic()-start
    if typ=='tts-end' and not audio_task:
     out=d.get('tts_output',{});url=out.get('url')
     if url:audio_task=asyncio.create_task(audio(url))
    if typ=='run-end':break
   if audio_task:await asyncio.wait_for(audio_task,240)
   print(json.dumps({'route':route,'name':name,'timings':timings,'text':''.join(text)}),flush=True)
asyncio.run(main())
