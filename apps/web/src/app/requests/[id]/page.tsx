import { NotamWorkbench } from "@/components/notam-workbench";
import { getRequest } from "@/lib/api";
export const dynamic = "force-dynamic";
export default async function RequestPage({params}:{params:Promise<{id:string}>}){const {id}=await params;const request=await getRequest(id);return <NotamWorkbench request={request}/>}
