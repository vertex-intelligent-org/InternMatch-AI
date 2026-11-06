import { ProfileView, CVView, MatchesView } from '@/features/workspace/WorkspaceViews';
import { notFound } from 'next/navigation';
import { uuid } from '@/lib/student/contracts';
import { OpportunityList, OpportunityView, SavedList, ApplicationsList, ApplicationView } from '@/features/student/StudentViews';
export const dynamic='force-dynamic';
export default async function StudentSection({params}:{params:Promise<{section:string[]}>}){const {section}=await params;const [area,id]=section;if(section.length>2 || (id&&!uuid(id)))notFound();if(area==='profile'&&!id)return <ProfileView/>;if(area==='cv'&&!id)return <CVView/>;if(area==='matches')return <MatchesView key={id||'list'} id={id}/>;if(area==='opportunities')return id?<OpportunityView key={id} id={id}/>:<OpportunityList/>;if(area==='saved'&&!id)return <SavedList/>;if(area==='applications')return id?<ApplicationView key={id} id={id}/>:<ApplicationsList/>;notFound();}
