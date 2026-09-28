/* Pure planning/verification shared by n8n Code nodes and the runnable self-check. */
const PROJECT = '6Jhc7FCRmrMQPgW7';
const norm = s => s.normalize('NFKC').trim().toLocaleLowerCase('de').replace(/\s+/g, ' ');
const shape = t => ({id:t.id,content:t.content,description:t.description || '',sectionId:t.sectionId || null});
const same = (a,b) => JSON.stringify(shape(a)) === JSON.stringify(shape(b));
const fail = message => {throw new Error(message);};
function snapshot(s) {
  if (!s || s.complete !== true || s.projectId !== PROJECT || !Array.isArray(s.tasks) || !Array.isArray(s.sections)) fail('incomplete_snapshot');
  if (s.tasks.some(t => t.projectId !== PROJECT || typeof t.content !== 'string' || typeof t.id !== 'string')) fail('invalid_snapshot');
  return s;
}
function plan(input, state) {
  snapshot(state);
  if (!input || !/^[a-zA-Z0-9_-]{12,80}$/.test(input.request_id || '') || !Array.isArray(input.operations) || !input.operations.length || input.operations.length > 25) fail('invalid_request');
  const tasks = new Map(state.tasks.map(t => [t.id,t]));
  const used = new Set();
  const claim = id => {if (used.has(id)) fail('overlapping_operations'); used.add(id);};
  const get = (id, expected) => {
    const t = tasks.get(id);
    if (!t || !expected || expected.id !== id || !same(t,expected)) fail('stale_or_missing_task');
    if (t.parentId || t.recurring || t.uncompletable || state.tasks.some(c => c.parentId === id)) fail('complex_task_requires_official_tools');
    claim(id); return t;
  };
  const section = name => {
    const matches = state.sections.filter(s => norm(s.name) === norm(name || ''));
    if(matches.length !== 1) fail('unknown_or_ambiguous_section');
    return matches[0].id;
  };
  const text = (s,max=500) => {if(typeof s !== 'string' || !s.trim() || s.length>max) fail('invalid_text');return s.trim();};
  const entries=[],commands=[];
  input.operations.forEach((op,i) => {
    if (!op || !['add','update','move','complete','merge'].includes(op.action)) fail('invalid_action');
    const uuid = `${input.request_id}-${i}`;
    const e = {index:i,action:op.action,uuid};
    if (op.action === 'add') {
      if(op.description!==undefined && typeof op.description!=='string') fail('invalid_description');
      const content=text(op.content),description=op.description === undefined?'':op.description;
      if(description.length>5000) fail('description_too_long');
      const sectionId=section(op.section);
      const candidates=state.tasks.filter(t=>norm(t.content)===norm(content));
      if(!Array.isArray(op.expected_candidates)) fail('expected_candidates_required');
      const sorted = ts => ts.map(shape).sort((a,b)=>a.id.localeCompare(b.id));
      if(JSON.stringify(sorted(candidates))!==JSON.stringify(sorted(op.expected_candidates))) fail('stale_add_candidates');
      const exact=candidates.filter(t=>norm(t.description||'')===norm(description));
      if(exact.length>1) fail('ambiguous_duplicate');
      if(exact.length===1) {
        if(exact[0].sectionId!==sectionId) fail('existing_item_requires_move');
        e.id=exact[0].id;e.desired=shape(exact[0]);e.already_present=true;
      } else {
        if(entries.some(x=>x.action==='add' && norm(x.desired.content)===norm(content) && norm(x.desired.description)===norm(description))) fail('duplicate_in_batch');
        e.temp_id=uuid+'-new';e.desired={content,description,sectionId};
        commands.push({type:'item_add',uuid,temp_id:e.temp_id,args:{content,description,project_id:PROJECT,section_id:sectionId,auto_parse_labels:false}});
      }
    } else {
      const t=get(op.id,op.expected);e.id=t.id;e.desired=shape(t);
      if(op.action==='complete') commands.push({type:'item_close',uuid,args:{id:t.id}});
      if(op.action==='move') {
        e.desired.sectionId=section(op.section);
        commands.push({type:'item_move',uuid,args:{id:t.id,section_id:e.desired.sectionId}});
      }
      if(op.action==='update') {
        const args={id:t.id};
        if(op.content!==undefined) args.content=e.desired.content=text(op.content);
        if(op.description!==undefined) {
          if(typeof op.description!=='string'||op.description.length>5000) fail('invalid_description');
          args.description=e.desired.description=op.description;
        }
        if(Object.keys(args).length===1) fail('empty_update');
        commands.push({type:'item_update',uuid,args});
      }
      if(op.action==='merge') {
        if(!Array.isArray(op.duplicates)||!op.duplicates.length||op.duplicates.length>24) fail('invalid_merge');
        const others=op.duplicates.map(d=>get(d.id,d.expected));
        // Semantic duplicate selection belongs to Hermes; never discard descriptions here.
        e.duplicates=others.map(shape);
        e.desired.description=[...new Set([t,...others].map(x=>x.description||'').filter(Boolean))].join('\n');
        if(e.desired.description.length>5000) fail('merged_description_too_long');
        commands.push({type:'item_update',uuid,args:{id:t.id,description:e.desired.description}});
      }
    }
    entries.push(e);
  });
  if(used.size + entries.filter(e=>e.action==='add').length > 25) fail('too_many_affected_tasks');
  return {request_id:input.request_id,entries,commands};
}
function verify(p, raw, state, final=false) {
  snapshot(state);
  const tasks=new Map(state.tasks.map(t=>[t.id,t])),commands=[],results=[];
  const status=raw?.sync_status || {},mapping=raw?.temp_id_mapping || {};
  for(const e of p.entries) {
    const id=e.id||mapping[e.temp_id];
    const task=tasks.get(id);
    const good=e.action==='complete' ? Boolean(id)&&!task : Boolean(task)&&same(task,{...e.desired,id});
    let outcome='uncertain';
    if(good) outcome=e.already_present?'already_present':'verified';
    else if(status[e.uuid] && status[e.uuid]!=='ok') outcome='failed';
    const result={index:e.index,action:e.action,id:id||null,status:outcome};
    if(task) result.task=shape(task);
    if(e.action==='merge' && good) {
      const duplicates=e.duplicates.map(d=>tasks.get(d.id));
      if(final) result.status=duplicates.every(d=>!d)?'verified':'partial';
      else {
        // Readback of the survivor MUST succeed before any duplicate is completed.
        const unchanged=duplicates.every((d,i)=>d&&same(d,e.duplicates[i]));
        if(!unchanged) result.status='conflict';
        else {
          e.duplicates.forEach((d,i)=>commands.push({type:'item_close',uuid:`${e.uuid}-merge-${i}`,args:{id:d.id}}));
          result.status='pending_merge';
        }
      }
    }
    results.push(result);
  }
  return {request_id:p.request_id,results,commands,verified:results.every(r=>['verified','already_present'].includes(r.status))};
}
function combineResponses(a,b) {return {sync_status:{...a?.sync_status,...b?.sync_status},temp_id_mapping:{...a?.temp_id_mapping,...b?.temp_id_mapping}};}
if(typeof module!=='undefined') module.exports={plan,verify,shape,snapshot,combineResponses,PROJECT};
