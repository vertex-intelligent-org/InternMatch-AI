const ids={internship:'11111111-1111-4111-8111-111111111111',draft:'22222222-2222-4222-8222-222222222222',submitted:'33333333-3333-4333-8333-333333333333',foreign:'44444444-4444-4444-8444-444444444444'};
const now='2026-11-01T12:00:00Z';
export function createStudentFixture(){
 let bookmarks,records,events,empty,failStudent,slowStudent,malformed,closed,uncertain;
 const listing={id:ids.internship,title:'Research Intern · Araştırma · تدريب',company:'Example Company',location:'İstanbul',work_type:'remote',required_skills:['Python','İletişim'],preferred_skills:['Research'],publication_status:'published',is_active:true,posted_at:now};
 function reset(){bookmarks=new Map();records=new Map();events=[];empty=false;failStudent=false;slowStudent=0;malformed=false;closed=false;uncertain=false;}
 reset();
 function application(id,user){const key=user.id+id;if(!records.has(key))records.set(key,{id,internship_id:ids.internship,company_name:'Example Company',job_title:'Research Intern',status:id===ids.draft?'saved':'interviewing',generated_cover_letter:'Dear team,\nÇağrı الطالب',applied_date:id===ids.draft?null:'2026-11-01',notes:'Private note',created_at:now,updated_at:now,interview_scheduled_at:id===ids.draft?null:'2026-11-05T10:00:00Z',interview_mode:id===ids.draft?null:'online',interview_location:id===ids.draft?null:'https://example.test/meeting',interview_message:null,timeline:[{status:'saved',occurred_at:now}]});return records.get(key);}
 function handle({path,url,req,body,user,send}){
  if(!path.startsWith('/internships')&&!path.startsWith('/saved-internships')&&!path.startsWith('/applications'))return false;
  events.push({path,method:req.method,user:user.email,body});
  const reply=(data,status=200)=>{if(slowStudent)setTimeout(()=>send(data,status),slowStudent);else send(data,status);};
  if(user.canonicalRole!=='intern'){reply({detail:'forbidden'},403);return true;}
  if(failStudent){reply({detail:'fixture outage'},503);return true;}
  if(malformed){reply({items:[{...listing,id:'invalid'}],total:1,limit:12,offset:0});return true;}
  const offset=Number(url.searchParams.get('offset')||0),limit=Number(url.searchParams.get('limit')||12);
  const page=items=>({items:items.slice(offset,offset+limit),total:items.length,offset,limit});
  if(path==='/internships'&&req.method==='GET'){
   const all=Array.from({length:14},(_,i)=>({...listing,id:i===0?ids.internship:'11111111-1111-4111-8111-'+String(i+1).padStart(12,'0'),title:listing.title+(i?' '+i:'')}));
   const items=empty?[]:all.filter(i=>(!url.searchParams.get('location')||i.location.toLowerCase().includes(url.searchParams.get('location').toLowerCase()))&&(!url.searchParams.get('skill')||i.required_skills.join(' ').toLowerCase().includes(url.searchParams.get('skill').toLowerCase()))&&(!url.searchParams.get('work_type')||i.work_type===url.searchParams.get('work_type')));
   reply(page(items));return true;
  }
  if(path.startsWith('/internships/')&&req.method==='GET'){
   if(!path.endsWith(ids.internship)||closed){reply({detail:'missing'},404);return true;}
   reply({...listing,description:'Learn with our team.\n<script>window.fixtureXss=true</script>',languages:['English','Türkçe'],min_education:'University student',experience_requirements:null});return true;
  }
  if(path==='/saved-internships'&&req.method==='GET'){reply(page([...(bookmarks.get(user.id)||[])].map(id=>({id:'55555555-5555-4555-8555-555555555555',internship_id:id,saved_at:now,internship:{...listing,id,is_active:!closed,publication_status:closed?'closed':'published'}}))));return true;}
  if(path.startsWith('/saved-internships/')){
   const id=path.split('/').at(-1);if(id!==ids.internship){reply({detail:'missing'},404);return true;}
   const saved=bookmarks.get(user.id)||new Set();if(req.method==='POST')saved.add(id);else saved.delete(id);bookmarks.set(user.id,saved);reply({internship_id:id,is_saved:req.method==='POST'});return true;
  }
  if(path==='/applications'&&req.method==='GET'){reply({applications:empty?[]:[application(ids.draft,user),application(ids.submitted,user)]});return true;}
  if(path.startsWith('/applications/')){
   const id=path.split('/')[2];if(![ids.draft,ids.submitted].includes(id)){reply({detail:'not owned'},404);return true;}
   const record=application(id,user);
   if(req.method==='GET'){reply(record);return true;}
   if(req.method==='POST'&&path.endsWith('/submit')){
    if(record.status!=='saved'||closed){reply({detail:'not available'},409);return true;}
    record.status='applied';record.generated_cover_letter=body.cover_letter??record.generated_cover_letter;record.notes=body.notes??record.notes;record.applied_date='2026-11-04';record.timeline.push({status:'applied',occurred_at:now});
    if(uncertain){reply({detail:'response lost after commit'},503);return true;}
    reply(record);return true;
   }
  }
  reply({detail:'not found'},404);return true;
 }
 return {reset,handle,control(data){empty=data.empty??empty;failStudent=data.failStudent??failStudent;slowStudent=data.slowStudent??slowStudent;malformed=data.malformed??malformed;closed=data.closed??closed;uncertain=data.uncertain??uncertain;},state:()=>({ids,events})};
}
