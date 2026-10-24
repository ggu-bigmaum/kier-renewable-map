// Local preview: node web/server.mjs. Only public assets and read-only map APIs are served.
// Env: MAP_PORT(5057), MAP_HOST(127.0.0.1), API_UPSTREAM(http://127.0.0.1:5056, 서버측 /api/* 프록시 대상),
//      KIER_API_BASE(미설정 시 index.html 의 meta 기본값 http://127.0.0.1:5056/api/ 유지; 브라우저가 호출할 API 주소)
import http from 'node:http';
import {readFile} from 'node:fs/promises';
const files = new Map([['/','index.html'],['/index.html','index.html'],['/app.js','app.js'],['/regions.js','regions.js'],['/region-geometry.js','region-geometry.js'],['/styles.css','styles.css']]);
const MAP_PORT=Number(process.env.MAP_PORT||5057), MAP_HOST=process.env.MAP_HOST||'127.0.0.1', API_UPSTREAM=(process.env.API_UPSTREAM||'http://127.0.0.1:5056').replace(/\/+$/,''), API_BASE=process.env.KIER_API_BASE||'';
const mime={html:'text/html; charset=utf-8',js:'text/javascript; charset=utf-8',css:'text/css; charset=utf-8',json:'application/json; charset=utf-8',geojson:'application/geo+json; charset=utf-8',txt:'text/plain; charset=utf-8'};
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(req.method!=='GET') {res.writeHead(405);res.end();return;}
  if(['/api/datasets','/api/point','/api/summary'].includes(url.pathname)) {
    try {
      const upstream=await fetch(`${API_UPSTREAM}${url.pathname}${url.search}`,{signal:AbortSignal.timeout(12000),redirect:'error',headers:{Accept:'application/json'}});
      if(!upstream.ok||!upstream.headers.get('content-type')?.includes('application/json')) {res.writeHead(503,{'Content-Type':'application/json'});res.end(JSON.stringify({status:'not_started'}));return;}
      res.writeHead(200,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(await upstream.text());
    } catch {res.writeHead(503,{'Content-Type':'application/json'});res.end(JSON.stringify({status:'not_started'}));}
    return;
  }
  const boundaryFile=/^\/data\/boundaries\/(index\.json|provinces\.geojson|districts\.geojson|LICENSE-DATA\.txt|districts\/[0-9]{5}\.geojson)$/.test(url.pathname);
  const file=files.get(url.pathname)||(boundaryFile?url.pathname.slice(1):null);
  if(!file){res.writeHead(404);res.end('Not found');return;}
  try {let body=await readFile(new URL(file,import.meta.url));if(file==='index.html'&&API_BASE)body=Buffer.from(body.toString('utf8').replace(/(<meta name="kier-api-base" content=")[^"]*(")/,(m,a,b)=>a+API_BASE.replace(/["<>&]/g,'')+b));res.writeHead(200,{'Content-Type':mime[file.split('.').at(-1)],'X-Content-Type-Options':'nosniff'});res.end(body);}
  catch(error) {res.writeHead(error.code==='ENOENT'?404:500);res.end('Unable to load asset');}
});
server.on('error',e=>{console.error(`지도 서버 시작 실패: ${e.code}`);process.exitCode=1;});
server.listen(MAP_PORT,MAP_HOST,()=>console.log(`KIER 지도 화면: http://${MAP_HOST}:${MAP_PORT}`));
