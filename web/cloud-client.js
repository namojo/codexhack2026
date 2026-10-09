/* Same-origin service transport. Offline access is an explicit operator action. */
(function(root,factory){const exported=factory();if(typeof module==='object'&&module.exports)module.exports=exported;if(root&&root.document)root.RescueCloud=exported.createClient({fetch:root.fetch.bind(root),storage:()=>root.localStorage,cloudDeployment:root.document.documentElement?.dataset.serviceMode==='cloud'});})(typeof window==='object'?window:null,function(){
 'use strict';
 class ServiceError extends Error{constructor(status,message,code){super(message);this.status=status;this.code=code;}}
 function createClient({fetch:fetcher,storage=()=>null,setTimer=setTimeout,clearTimer=clearTimeout,cloudDeployment=false}={}){
  let config=null,mode='connecting',pollCancel=null,settings=null;
  async function request(path,{method='GET',body,signal,headers={}}={}){
   if(typeof path!=='string'||!/^\/api\/[a-zA-Z0-9_\-/]+$/.test(path)||path.split('/').includes('..'))throw new ServiceError(400,'허용되지 않은 API 경로입니다.');
   const response=await fetcher(path,{method,cache:'no-store',credentials:'same-origin',headers:{...(body?{'Content-Type':'application/json'}:{}),...headers},...(body?{body:JSON.stringify(body)}:{}),...(signal?{signal}:{})});
   let value;try{value=await response.json();}catch(_){throw new ServiceError(response.status,'서버 응답을 읽지 못했습니다. 연결 상태를 확인하세요.');}
   if(!response.ok)throw new ServiceError(response.status,value.error||'요청을 처리하지 못했습니다.',value.code);return value;
  }
  async function boot(){try{config=await request('/api/config');mode=config.storage==='supabase'?'cloud':'unconfigured';}catch(e){if(e.status===404&&!cloudDeployment){mode='local';config={storage:'local',ai:{configured:false},synthetic:true};}else{mode='unavailable';config={storage:'unconfigured',ai:{configured:false},error:e.message};}}return {mode,config};}
  async function getSettings(){settings=await request('/api/settings');return settings;}
  async function setProvider(provider){if(!['codex_cli','openai','disabled'].includes(provider))throw new ServiceError(400,'지원하지 않는 분석 제공자입니다.');if(!settings?.local_demo||!settings?.mutable||!settings?.csrf_token)throw new ServiceError(403,'분석 제공자 변경은 로컬 시연 서버에서만 가능합니다.');const value=await request('/api/settings',{method:'POST',body:{provider},headers:{'X-CSRF-Token':settings.csrf_token}});await boot();settings=value;return value;}
  function remember(id){try{const s=storage();if(id)s?.setItem('rescue-ai-draft-v1',id);else s?.removeItem('rescue-ai-draft-v1');}catch(_){}}
  function remembered(){try{return storage()?.getItem('rescue-ai-draft-v1')||null;}catch(_){return null;}}
  const analysisPath=id=>'/api/ai/analyses/'+encodeURIComponent(id);
  async function createAnalysis(body){if(!(config?.ai?.enabled??config?.ai?.configured)||mode!=='cloud')throw new ServiceError(503,'이 연결에서는 AI 분석을 사용할 수 없습니다. 담당자 직접 입력을 사용하세요.');const result=await request('/api/ai/analyses',{method:'POST',body});remember(result.id);return result;}
  function getAnalysis(id,options){return request(analysisPath(id),options);}
  async function confirm(id,body){const result=await request(analysisPath(id)+'/confirm',{method:'POST',body});remember(null);return result;}
  function startPolling(id,{onUpdate,onError,interval=1800}={}){
   if(pollCancel)pollCancel();let stopped=false,timer=null,controller=null;
   const stop=()=>{stopped=true;if(timer!==null)clearTimer(timer);controller?.abort();};pollCancel=stop;
   async function tick(){if(stopped)return;controller=new AbortController();try{const value=await getAnalysis(id,{signal:controller.signal});if(stopped)return;onUpdate?.(value);if(!['queued','running'].includes(value.status)){stop();return;}timer=setTimer(tick,interval);}catch(error){if(stopped)return;stop();onError?.(error);}}tick();return stop;
  }
  return {boot,request,getSettings,setProvider,createAnalysis,getAnalysis,confirm,startPolling,remember,remembered,get mode(){return mode;},get config(){return config;}};
 }
 return {createClient,ServiceError};
});
