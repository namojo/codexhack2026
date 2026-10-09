#!/usr/bin/env node
// Append only the named synthetic cases; never reset a live workspace. Secrets via stdin.
import {readFile,writeFile} from 'node:fs/promises';
import {database} from '../netlify/functions/supabase.mjs';
let raw='';for await(const chunk of process.stdin)raw+=chunk;const env=JSON.parse(raw),db=database(env);
const seed=JSON.parse(await readFile(new URL('../data/seed.json',import.meta.url),'utf8'));
const ids=['INC-20261009-100','INC-20261009-101'];
for(let n=0;n<3;n++){
 const ws=await db.workspace(),doc=structuredClone(ws.document),preserved=JSON.stringify(doc.incidents.filter(i=>!ids.includes(i.id)));
 const added=[];for(const id of ids){if(!doc.incidents.some(i=>i.id===id)){const i=seed.incidents.find(i=>i.id===id);if(!i||i.synthetic!==true)throw Error('synthetic case missing');doc.incidents.push(i);added.push(id);}}
 if(!doc.resources.some(r=>r.id==='TEAM-DEMO01'))doc.resources.push(seed.resources.find(r=>r.id==='TEAM-DEMO01'));
 if(!added.length){console.log(JSON.stringify({status:'already_present',ids,revision:ws.revision}));break;}
 try{await db.rpc('rescue_cas',{p_revision:ws.revision,p_document:doc});}catch(e){if(e.status===409&&n<2)continue;throw Error('showcase append failed');}
 const actual=await db.workspace();if(JSON.stringify(actual.document.incidents.filter(i=>!ids.includes(i.id)))!==preserved)throw Error('existing incidents changed');
 const result={synthetic:true,status:'passed',added,workspace_revision:actual.revision,existing_incidents_preserved:true,incident_count:actual.document.incidents.length,team_added:'TEAM-DEMO01'};
 await writeFile(new URL('../docs/verification/showcase-import.json',import.meta.url),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));break;
}
