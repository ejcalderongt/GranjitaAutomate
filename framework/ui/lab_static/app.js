const $=id=>document.getElementById(id);
const labels={idle:'Listo',running:'En curso',completed:'Completado',cancelled:'Cancelado',failed:'Con fallo'};
const reasons={idle:'Puedes iniciar una verificacion sintetica.',running:'Verificando solo con datos sinteticos.',completed:'Verificacion sintetica completada.',cancelled:'Verificacion detenida.',failed:'No se pudo completar la verificacion.'};
async function api(path,method='GET'){const r=await fetch(path,{method,headers:method==='POST'?{'X-Lab-Action':'synthetic'}:{}});if(!r.ok)throw Error('Solicitud no disponible ('+r.status+')');return r.json();}
async function refresh(){try{const s=await api('/api/status');$('status').textContent=labels[s.status]||s.status;$('reason').textContent=reasons[s.status]||s.reason;$('verify').disabled=s.status==='running';$('stop').disabled=s.status!=='running';const files=await api('/api/evidence');$('files').replaceChildren();for(const f of files){const b=document.createElement('button');b.textContent=(f.synthetic?'SINTETICO / ':'REAL / ')+f.id;b.onclick=async()=>{try{$('detail').textContent=JSON.stringify(await api('/api/evidence/'+encodeURIComponent(f.id)),null,2);}catch(e){$('error').textContent=e.message;}};$('files').appendChild(b);}if(!files.length)$('files').textContent='Aun no hay evidencia permitida.';}catch(e){$('error').textContent=e.message;}}
for(const action of ['verify','stop'])$(action).onclick=async()=>{try{await api('/api/actions/'+action,'POST');await refresh();}catch(e){$('error').textContent=e.message;}};
refresh();setInterval(refresh,2000);

